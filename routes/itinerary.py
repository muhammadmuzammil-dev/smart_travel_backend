from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path
import csv
import json
import os
from fastapi import APIRouter, HTTPException
from typing import List, Dict, Any, Optional
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from schemas import ItineraryRequest, DayPlan, ItineraryResponse, SpotLocation
from retrieval import search_spots_for_preferences, search_hotels_for_city
from llm_itinerary import generate_itinerary_llm
from utils.transport_calculator import calculate_itinerary_transport_costs
from utils.cost_optimizer import (
    generate_comprehensive_cost_breakdown,
    generate_scenario_comparison
)
from utils.weather_service import get_weather_for_destination


router = APIRouter(prefix="/itinerary", tags=["Itinerary"])


def _parse_start_date(date_str: Optional[str]):
    if not date_str:
        return None

    normalized = date_str.strip()
    date_formats = [
        "%Y-%m-%d",
        "%d-%m-%Y",
        "%d/%m/%Y",
        "%B %d, %Y",
        "%b %d, %Y",
    ]

    try:
        return datetime.fromisoformat(normalized).date()
    except ValueError:
        pass

    for fmt in date_formats:
        try:
            return datetime.strptime(normalized, fmt).date()
        except ValueError:
            continue

    return None


def _build_budget_breakdown(total_cost: float) -> Dict[str, float]:
    if total_cost <= 0:
        return {}

    allocations = {
        "accommodation": 0.4,
        "food": 0.25,
        "transport": 0.2,
        "activities": 0.15,
    }
    breakdown: Dict[str, float] = {}
    allocated = 0.0
    for key, pct in allocations.items():
        value = round(total_cost * pct, 2)
        breakdown[key] = value
        allocated += value

    remainder = round(total_cost - allocated, 2)
    if remainder:
        breakdown["miscellaneous"] = round(breakdown.get("miscellaneous", 0) + remainder, 2)

    return breakdown


HOTEL_KEYWORDS = ["hotel", "resort", "guest", "lodge", "inn", "suite", "motel"]
HOTELS_DIR = Path(__file__).resolve().parents[1] / "data" / "hotels"


CITY_HOTEL_HINTS: Dict[str, List[str]] = {
    "naran": [
        "Pine Park Shogran Resort",
        "Arcadian Sprucewoods Luxury Resort",
        "Fairy Meadows Cottage Naran",
    ],
    "hunza": [
        "Serena Hunza Inn",
        "Luxus Hunza Attabad Lake Resort",
        "Darbar Hotel Hunza",
    ],
    "skardu": [
        "Shangrila Resort Skardu",
        "Serena Shigar Fort",
        "Hotel One Skardu",
    ],
    "lahore": [
        "Pearl Continental Hotel Lahore",
        "Avari Lahore",
        "Faletti's Hotel Lahore",
    ],
    "karachi": [
        "Mövenpick Hotel Karachi",
        "Pearl Continental Karachi",
        "Beach Luxury Hotel",
    ],
    "islamabad": [
        "Serena Hotel Islamabad",
        "Islamabad Marriott Hotel",
        "Roomy Signature Hotel",
    ],
    "murree": [
        "Lockwood Hotel Murree",
        "Hotel One Mall Road Murree",
        "Shangrila Resort Murree",
    ],
}


def _append_unique(hotels: List[str], candidates: List[str]) -> None:
    for hotel in candidates:
        clean = (hotel or "").strip()
        if not clean:
            continue
        if clean not in hotels:
            hotels.append(clean)
        if len(hotels) >= 3:
            break


def _normalize_city_name(city: str) -> str:
    return (
        city.lower()
        .replace("-", " ")
        .replace("&", " and ")
        .strip()
    )


@lru_cache(maxsize=128)
def _load_hotels_from_csv(city: str) -> List[str]:
    if not city:
        return []

    normalized = _normalize_city_name(city).replace(" ", "_")
    candidate_names = [
        f"{normalized}.csv",
        f"{normalized.replace('_city', '')}.csv",
    ]

    for filename in candidate_names:
        path = HOTELS_DIR / filename
        if not path.exists():
            continue
        try:
            with path.open("r", encoding="utf-8", newline="") as fp:
                reader = csv.DictReader(fp)
                names = [
                    (row.get("Name") or row.get("name") or "").strip()
                    for row in reader
                ]
                return [name for name in names if name]
        except Exception:
            continue

    return []


@lru_cache(maxsize=128)
def _load_hotels_with_prices(city: str) -> Dict[str, List[Dict[str, Any]]]:
    """Load hotels with price information from structured_cities.json"""
    if not city:
        return {"low": [], "mid": [], "high": []}
    
    BASE_DIR = Path(__file__).resolve().parents[1]
    structured_cities_path = BASE_DIR / "data" / "structured_cities.json"
    
    if not structured_cities_path.exists():
        return {"low": [], "mid": [], "high": []}
    
    try:
        with open(structured_cities_path, "r", encoding="utf-8") as f:
            cities_data = json.load(f)
        
        city_normalized = _normalize_city_name(city)
        
        for city_data in cities_data:
            city_name = city_data.get("city", "").lower()
            if city_normalized in city_name or city_name in city_normalized:
                hotels = city_data.get("hotels", {})
                if isinstance(hotels, dict):
                    return {
                        "low": hotels.get("low", []),
                        "mid": hotels.get("mid", []),
                        "high": hotels.get("high", [])
                    }
    except Exception as e:
        print(f"Error loading hotels for {city}: {e}")
    
    return {"low": [], "mid": [], "high": []}


def _determine_hotel_tier(budget_per_person_per_day: float) -> str:
    """Determine hotel tier based on budget per person per day"""
    # Budget tiers:
    # Low: < 2000 PKR per person per day
    # Mid: 2000-5000 PKR per person per day  
    # High: > 5000 PKR per person per day
    if budget_per_person_per_day < 2000:
        return "low"
    elif budget_per_person_per_day <= 5000:
        return "mid"
    else:
        return "high"


def _extract_hotels(spots: List[Dict], destination: Optional[str], region: Optional[str] = None, budget_amount: Optional[float] = None, num_days: int = 1, num_people: int = 1) -> List[str]:
    """Extract hotels based on budget, using vector search first, then fallback methods"""
    hotels: List[str] = []
    
    # Calculate budget per person per day to determine hotel category
    budget_per_person_per_day = None
    hotel_tier = "mid"  # Default tier
    if budget_amount and num_days > 0 and num_people > 0:
        budget_per_person_per_day = budget_amount / (num_days * num_people)
        hotel_tier = _determine_hotel_tier(budget_per_person_per_day)
    
    # First, try vector search for hotels
    if destination:
        try:
            vector_hotels = search_hotels_for_city(
                city=destination,
                budget_level=hotel_tier,
                top_k=5
            )
            
            # Extract hotel names from vector search results
            for hotel in vector_hotels[:3]:
                name = hotel.get("name", "").strip()
                if name and name not in hotels:
                    hotels.append(name)
        except Exception as e:
            print(f"[Hotels] Vector search failed: {e}, falling back to other methods")
    
    # Fallback: try to load hotels with prices from structured data
    if len(hotels) < 3 and destination:
        hotels_with_prices = _load_hotels_with_prices(destination)
        tier_hotels = hotels_with_prices.get(hotel_tier, [])
        
        # Filter hotels that fit within budget (if budget specified)
        if budget_per_person_per_day:
            # For low budget, show hotels under budget
            # For mid/high, show hotels within reasonable range
            if hotel_tier == "low":
                # Show hotels priced under budget_per_person_per_day
                filtered = [h for h in tier_hotels if h.get("price", float('inf')) <= budget_per_person_per_day]
                if filtered:
                    hotels = [h["name"] for h in filtered[:3]]
            elif hotel_tier == "mid":
                # Show mid-range hotels (2000-5000 range)
                filtered = [h for h in tier_hotels if 2000 <= h.get("price", 0) <= 5000]
                if filtered:
                    hotels = [h["name"] for h in filtered[:3]]
            else:  # high
                # Show high-end hotels (5000+)
                filtered = [h for h in tier_hotels if h.get("price", 0) >= 5000]
                if filtered:
                    hotels = [h["name"] for h in filtered[:3]]
        
        # If no filtered hotels, just take top 3 from tier
        if not hotels and tier_hotels:
            hotels = [h["name"] for h in tier_hotels[:3]]
    
    # Fallback: Load hotels from spots
    if len(hotels) < 3:
        for spot in spots:
            name = (spot.get("name") or spot.get("spot_name") or "").strip()
            if not name:
                continue

            lowered_name = name.lower()
            if any(keyword in lowered_name for keyword in HOTEL_KEYWORDS):
                if name not in hotels:
                    hotels.append(name)
                    if len(hotels) >= 3:
                        break

    destination_key = destination.lower() if destination else None
    region_key = region.lower() if region else None

    # Fallback: Load hotels from hints
    if len(hotels) < 3 and destination_key and destination_key in CITY_HOTEL_HINTS:
        _append_unique(hotels, CITY_HOTEL_HINTS[destination_key])

    if len(hotels) < 3 and region_key and region_key in CITY_HOTEL_HINTS:
        _append_unique(hotels, CITY_HOTEL_HINTS[region_key])

    # Fallback: Load from CSV (without price info)
    if len(hotels) < 3 and destination:
        csv_hotels = _load_hotels_from_csv(destination)
        # Filter CSV hotels based on tier keywords if budget specified
        if budget_per_person_per_day:
            if hotel_tier == "low":
                filtered = [h for h in csv_hotels if any(word in h.lower() for word in ["guest", "lodge", "inn", "hostel", "motel"])]
                if filtered:
                    _append_unique(hotels, filtered)
                else:
                    _append_unique(hotels, csv_hotels[:2])
            elif hotel_tier == "high":
                filtered = [h for h in csv_hotels if any(word in h.lower() for word in ["resort", "serena", "marriott", "luxury", "premium", "suite", "hotel"])]
                if filtered:
                    _append_unique(hotels, filtered)
                else:
                    _append_unique(hotels, csv_hotels[-2:] if len(csv_hotels) >= 2 else csv_hotels)
            else:
                _append_unique(hotels, csv_hotels)
        else:
            _append_unique(hotels, csv_hotels)

    if len(hotels) < 3 and region:
        csv_hotels = _load_hotels_from_csv(region)
        _append_unique(hotels, csv_hotels)

    # Limit to 3 hotels
    hotels = hotels[:3]

    # Final fallback: generic hotel suggestion
    if not hotels and destination:
        if budget_per_person_per_day:
            if hotel_tier == "low":
                hotels.append(f"Budget-friendly guesthouse near {destination} city center")
            elif hotel_tier == "high":
                hotels.append(f"Luxury resort near {destination} city center")
            else:
                hotels.append(f"Comfortable hotel near {destination} city center")
        else:
            hotels.append(f"Comfortable hotel near {destination} city center")

    return hotels


def _clean_spot_name(raw: Optional[str]) -> Optional[str]:
    """Clean and validate spot names, filtering out invalid metadata fields."""
    if not raw:
        return None
    cleaned = raw.strip()
    if not cleaned:
        return None
    
    # Filter out invalid names that are metadata fields
    invalid_names = {
        "province", "division", "divisions", "district", "districts",
        "city", "region", "unknown", "null", "none", ""
    }
    if cleaned.lower() in invalid_names:
        return None
    if cleaned.lower().startswith("unknown"):
        return None
    
    # Filter out names that are too generic or look like metadata
    if len(cleaned) < 3:  # Too short to be a real place name
        return None
    
    return cleaned


def _filter_spots_for_destination(spots: List[Dict], destination: Optional[str], region: Optional[str]) -> List[Dict]:
    if not spots:
        return []

    dest_key = _normalize_city_name(destination) if destination else None
    region_key = _normalize_city_name(region) if region else None

    # Three tiers: exact match, region match, others
    exact_matches: List[Dict] = []
    region_matches: List[Dict] = []
    extras: List[Dict] = []

    for spot in spots:
        name = _clean_spot_name(spot.get("name") or spot.get("spot_name"))
        if not name:
            continue

        spot_city = _normalize_city_name(str(spot.get("city", ""))) if spot.get("city") else ""
        spot_region = _normalize_city_name(str(spot.get("region", ""))) if spot.get("region") else ""
        spot_province = _normalize_city_name(str(spot.get("province", ""))) if spot.get("province") else ""
        spot_district = _normalize_city_name(str(spot.get("district", ""))) if spot.get("district") else ""

        # STRICT city matching - only exact matches when destination is specified
        if dest_key:
            # Exact match: city or district must match destination exactly
            city_matches = (
                dest_key == spot_city or 
                dest_key == spot_district or
                spot_city == dest_key or
                spot_district == dest_key
            )
            
            # Also allow if destination is contained in city/district (for cases like "Multan" in "Multan District")
            # But be strict - don't match if city contains destination but is different (e.g., "Multan" shouldn't match "Lahore")
            contains_match = (
                (dest_key in spot_city and len(spot_city) - len(dest_key) < 5) or  # Allow small suffixes like "Multan District"
                (dest_key in spot_district and len(spot_district) - len(dest_key) < 5)
            )
            
            if city_matches or contains_match:
                exact_matches.append({**spot, "name": name})
                continue
        
        # Region/province match (medium priority) - only if no destination specified or as fallback
        if region_key and not dest_key:  # Only use region match if no specific city requested
            if (region_key in spot_region or 
                region_key in spot_province or
                spot_region in region_key or
                spot_province in region_key):
                region_matches.append({**spot, "name": name})
                continue
        
        # Only add extras if no destination specified
        if not dest_key:
            extras.append({**spot, "name": name})

    # If destination specified, ONLY return exact matches (strict filtering)
    if dest_key:
        return exact_matches
    
    # If no destination, return in priority order
    return exact_matches + region_matches + extras


def _format_place_entry(spot: Dict[str, Any]) -> str:
    name = spot.get("name") or ""
    city = spot.get("city") or ""
    if city and city.lower() not in name.lower():
        return f"{name} ({city})"
    return name


def _describe_day(day_number: int, spots: List[Dict[str, Any]], destination: Optional[str]) -> str:
    """Generate detailed day plan using rich spot data from structured_spots.json"""
    if not spots:
        location = destination or "the area"
        return f"Keep day {day_number} flexible for spontaneous discoveries around {location}, enjoying local cuisine and scenic stops."

    parts = []
    location = destination or spots[0].get("city") or "the region"
    
    # Morning activity (first spot)
    if len(spots) >= 1:
        spot1 = spots[0]
        name1 = spot1.get("name", "")
        desc1 = spot1.get("description", "")
        highlights1 = spot1.get("highlights", [])
        category1 = spot1.get("category", "")
        
        morning_text = f"Morning: Start your day at {name1}"
        if category1:
            morning_text += f" ({category1})"
        if desc1:
            # Use first sentence of description
            desc_snippet = desc1.split('.')[0] if '.' in desc1 else desc1[:120]
            morning_text += f". {desc_snippet}."
        clean_h1 = [h for h in highlights1 if h and not str(h).strip().startswith('[')]
        if clean_h1:
            morning_text += f" {clean_h1[0]}"
        parts.append(morning_text)

    # Afternoon activity (second spot if available)
    if len(spots) >= 2:
        spot2 = spots[1]
        name2 = spot2.get("name", "")
        desc2 = spot2.get("description", "")
        highlights2 = spot2.get("highlights", [])

        afternoon_text = f"Afternoon: Visit {name2}"
        if desc2:
            desc_snippet = desc2.split('.')[0] if '.' in desc2 else desc2[:120]
            afternoon_text += f". {desc_snippet}."
        clean_h2 = [h for h in highlights2 if h and not str(h).strip().startswith('[')]
        if clean_h2:
            afternoon_text += f" {clean_h2[0]}"
        parts.append(afternoon_text)

    # Evening activity (third spot if available, or wrap-up)
    if len(spots) >= 3:
        spot3 = spots[2]
        name3 = spot3.get("name", "")
        desc3 = spot3.get("description", "")
        highlights3 = spot3.get("highlights", [])

        evening_text = f"Evening: Explore {name3}"
        if desc3:
            desc_snippet = desc3.split('.')[0] if '.' in desc3 else desc3[:120]
            evening_text += f". {desc_snippet}."
        clean_h3 = [h for h in highlights3 if h and not str(h).strip().startswith('[')]
        if clean_h3:
            evening_text += f" {clean_h3[0]}"
        evening_text += " End the day with dinner at a local restaurant and a relaxing evening."
        parts.append(evening_text)
    elif len(spots) == 2:
        parts.append("Evening: Enjoy dinner at a local restaurant and take a leisurely evening stroll.")
    else:
        # Single spot - add more detail
        spot1 = spots[0]
        best_time = spot1.get("best_time_to_visit", "")
        if best_time:
            parts.append(f"Best time to visit: {best_time}")
        parts.append("Evening: Return to your accommodation for a restful evening.")
    
    return " | ".join(parts)


def _weather_note(city: Optional[str], start_date, num_days: int, provided_window: Optional[str]) -> str:
    location = city or "your destination"
    if start_date:
        end_date = start_date + timedelta(days=max(0, num_days - 1))
        window = f"{start_date.strftime('%b %d, %Y')} - {end_date.strftime('%b %d, %Y')}"
    elif provided_window:
        window = provided_window
    else:
        window = "your travel dates"

    return (
        f"Expect variable conditions in {location} around {window}. "
        "Check the latest PMD forecast 24 hours before departure and pack layers plus rain protection."
    )


# ---------------------------------------------------------
# SIMPLE STRUCTURED ITINERARY (RULE-BASED)
# ---------------------------------------------------------
def _simple_itinerary_from_spots(req: ItineraryRequest, spots: List[Dict]) -> ItineraryResponse:
    num_days = req.num_days
    if num_days <= 0:
        num_days = 1

    days: List[DayPlan] = []
    num_people = req.num_of_people or 1

    # Use budget_amount if provided, otherwise calculate dynamically
    if req.budget_amount:
        total_cost = req.budget_amount
    else:
        # Rates aligned with Budget Planner (per person per day)
        _FOOD     = {"low": 1050,  "medium": 3100,  "high": 6900}
        _ACTIVITY = {"low": 300,   "medium": 3300,  "high": 8100}
        _HOTEL    = {"low": 2250,  "medium": 8750,  "high": 31500}  # per room/night

        budget = (req.budget_level or "medium").lower()
        if budget not in _FOOD:
            budget = "medium"

        hotel_rooms    = (num_people + 1) // 2  # ceil(people / 2)
        food_total     = _FOOD[budget]     * num_days * num_people
        activity_total = _ACTIVITY[budget] * num_days * num_people
        hotel_total    = _HOTEL[budget]    * num_days * hotel_rooms
        subtotal       = food_total + activity_total + hotel_total
        total_cost     = round(subtotal * 1.10)  # +10% contingency
    start_date = _parse_start_date(req.travel_date)
    provided_window = req.travel_date

    curated_spots = _filter_spots_for_destination(spots, req.destination_city, req.region)
    
    # Debug: Print filtering results
    print(f"[DEBUG] After filtering: {len(curated_spots)} spots (from {len(spots)} total)")
    if curated_spots:
        print(f"[DEBUG] First few spots: {[s.get('name') + ' (' + s.get('city', '') + ')' for s in curated_spots[:5]]}")
    
    # Initialize min_spots_needed before the if/else block to avoid UnboundLocalError
    min_spots_needed = max(3 * num_days, 8)  # At least 8 spots, or 3 per day
    
    # If destination city is specified, ONLY use spots from that city (strict filtering)
    if req.destination_city:
        # Don't add spots from other cities - only use what we found for this city
        if not curated_spots:
            print(f"[DEBUG] WARNING: No spots found for {req.destination_city}. Consider checking data availability.")
    else:
        # Only if no specific destination, we can add more spots
        if len(curated_spots) < min_spots_needed:
            print(f"[DEBUG] Need {min_spots_needed} spots but only have {len(curated_spots)}, fetching more...")
            # Get more spots from the same region/province only
            region_spots = []
            
            dest_region = req.region or ""
            for spot in spots:
                spot_name = _clean_spot_name(spot.get("name") or spot.get("spot_name"))
                if not spot_name:
                    continue
                # Avoid duplicates
                existing_names = {_clean_spot_name(s.get("name") or s.get("spot_name")) for s in curated_spots}
                if spot_name in existing_names:
                    continue
                
                spot_region = str(spot.get("region", "")).lower()
                if dest_region and dest_region.lower() in spot_region:
                    region_spots.append(spot)
            
            # Add region spots only
            for spot in region_spots:
                if len(curated_spots) >= min_spots_needed:
                    break
                curated_spots.append(spot)
    
    # Don't limit too aggressively - keep more spots for better variety
    max_spots = min_spots_needed * 2  # Allow up to 2x needed for better distribution
    curated_spots = curated_spots[:max_spots]

    # Distribute spots across days intelligently - ensure variety
    # Try to give each day at least 2-3 unique spots
    spots_per_day = max(2, len(curated_spots) // num_days) if num_days > 0 else len(curated_spots)
    if spots_per_day < 2:
        spots_per_day = 2
    # Cap at 4 spots per day to avoid overcrowding
    if spots_per_day > 4:
        spots_per_day = 4
    
    # Track used spots to avoid repetition
    used_spot_names = set()
    index = 0
    
    for day in range(1, num_days + 1):
        # Calculate how many spots for this day
        todays_spots = []
        
        # Try to get unique spots first
        spots_added = 0
        while spots_added < spots_per_day and index < len(curated_spots):
            spot = curated_spots[index]
            spot_name = _clean_spot_name(spot.get("name") or spot.get("spot_name"))
            
            # Only add if we haven't used this spot yet
            if spot_name and spot_name not in used_spot_names:
                todays_spots.append(spot)
                used_spot_names.add(spot_name)
                spots_added += 1
            index += 1
        
        # If we still need more spots and haven't used all unique ones, continue
        if spots_added < spots_per_day:
            # Try to find more unique spots from remaining list
            for spot in curated_spots[index:]:
                if spots_added >= spots_per_day:
                    break
                spot_name = _clean_spot_name(spot.get("name") or spot.get("spot_name"))
                if spot_name and spot_name not in used_spot_names:
                    todays_spots.append(spot)
                    used_spot_names.add(spot_name)
                    spots_added += 1
        
        # Only reuse spots as last resort if we have very few unique spots
        if not todays_spots and curated_spots:
            # Use different spots than previous days
            available_indices = [i for i in range(len(curated_spots)) 
                               if _clean_spot_name(curated_spots[i].get("name")) not in used_spot_names]
            if available_indices:
                for idx in available_indices[:spots_per_day]:
                    todays_spots.append(curated_spots[idx])
                    spot_name = _clean_spot_name(curated_spots[idx].get("name"))
                    if spot_name:
                        used_spot_names.add(spot_name)
            else:
                # Last resort: use any spot
                reuse_index = (day - 1) % len(curated_spots)
                todays_spots = [curated_spots[reuse_index]]

        place_entries = [_format_place_entry(spot) for spot in todays_spots]
        description = _describe_day(day, todays_spots, req.destination_city)

        # Extract images from spots for this day
        day_images = []
        for spot in todays_spots:
            # Try to get images from different possible fields
            images = spot.get("images")
            if images:
                # Handle JSON string or list
                if isinstance(images, str):
                    try:
                        images = json.loads(images)
                    except:
                        # If it's not JSON, treat as single URL
                        images = [images] if images else []
                elif isinstance(images, list):
                    images = [img for img in images if img]  # Filter out empty strings
                else:
                    images = []
            else:
                # Fallback to image_url if images field doesn't exist
                image_url = spot.get("image_url")
                if image_url:
                    images = [image_url]
                else:
                    images = []
            
            # Add images to day_images, avoiding duplicates
            for img in images:
                if img and img not in day_images:
                    day_images.append(img)
        
        # Limit to reasonable number of images per day (max 6)
        day_images = day_images[:6]

        date_str = None
        if start_date:
            day_date = start_date + timedelta(days=day - 1)
            date_str = day_date.strftime("%Y-%m-%d")

        spot_locs = [
            SpotLocation(
                name=s.get("name") or s.get("spot_name") or "Unknown",
                latitude=float(s["latitude"]),
                longitude=float(s["longitude"]),
                city=s.get("city"),
            )
            for s in todays_spots
            if s.get("latitude") and s.get("longitude")
        ]

        days.append(
            DayPlan(
                day=day,
                places=place_entries,
                description=description,
                date=date_str,
                images=day_images if day_images else None,
                spot_locations=spot_locs if spot_locs else None,
            )
        )

    travel_window = None
    if start_date:
        end_date = start_date + timedelta(days=max(0, num_days - 1))
        travel_window = f"{start_date.strftime('%b %d, %Y')} - {end_date.strftime('%b %d, %Y')}"
    elif req.travel_date:
        travel_window = req.travel_date

    # Calculate transport costs
    transport_mode = req.transport_mode or "public_transport"
    num_people = req.num_of_people or 1
    
    # Get departure city coordinates if provided
    departure_city = None
    if req.departure_city:
        # Try to find departure city in spots or use a default location
        departure_city = {"name": req.departure_city, "latitude": None, "longitude": None}
    
    # Calculate transport costs for all spots in itinerary (with detailed rides)
    all_spots_for_transport = curated_spots[:max(3 * num_days, 3)]
    transport_costs = calculate_itinerary_transport_costs(
        spots=all_spots_for_transport,
        mode=transport_mode,
        num_people=num_people,
        departure_city=departure_city,
        include_detailed_rides=True
    )
    
    # Generate comprehensive cost breakdown with detailed optimization
    origin_city = req.departure_city or "Origin"
    destination_city = req.destination_city or "Destination"
    travel_style = req.budget_level or "medium"
    
    # Detect peak season (summer months, holidays) - simplified check
    # In production, this could be based on actual travel dates
    is_peak_season = False  # Can be enhanced to check actual dates
    
    # Get detailed rides for cost breakdown
    detailed_rides = transport_costs.get("detailed_rides", [])
    if not detailed_rides:
        # Fallback: create basic ride info from cost breakdown
        detailed_rides = transport_costs.get("cost_breakdown", [])
    
    # Generate comprehensive cost breakdown
    comprehensive_cost_breakdown = None
    scenario_comparison = None
    try:
        comprehensive_cost_breakdown = generate_comprehensive_cost_breakdown(
            origin_city=origin_city,
            destination_city=destination_city,
            num_days=num_days,
            num_people=num_people,
            travel_style=travel_style,
            transport_rides=detailed_rides,
            currency="PKR",
            is_peak_season=is_peak_season
        )
        
        # Generate scenario comparison
        scenario_comparison = generate_scenario_comparison(
            origin_city=origin_city,
            destination_city=destination_city,
            num_days=num_days,
            num_people=num_people,
            transport_rides=detailed_rides,
            currency="PKR",
            is_peak_season=is_peak_season
        )
    except Exception as e:
        print(f"[Cost Optimizer] Failed to generate comprehensive breakdown: {e}")
        import traceback
        traceback.print_exc()
    
    # Update budget breakdown to include transport costs (legacy support)
    transport_cost_amount = transport_costs.get("total_cost", 0.0)
    budget_breakdown = _build_budget_breakdown(total_cost)
    
    # Adjust budget breakdown: subtract transport from total, then redistribute
    if transport_cost_amount > 0 and budget_breakdown:
        # Update transport in breakdown with actual calculated cost
        budget_breakdown["transport"] = transport_cost_amount
        # Recalculate other categories proportionally
        remaining_budget = total_cost - transport_cost_amount
        if remaining_budget > 0:
            other_allocations = {
                "accommodation": 0.5,  # Increased since transport is separate
                "food": 0.3,
                "activities": 0.2,
            }
            for key, pct in other_allocations.items():
                if key in budget_breakdown:
                    budget_breakdown[key] = round(remaining_budget * pct, 2)
    
    recommended_hotels = _extract_hotels(spots, req.destination_city, req.region, req.budget_amount, req.num_days, req.num_of_people or 1)
    
    # Get weather data for destination
    weather_data = None
    weather_considerations = ""
    
    if curated_spots:
        # Use coordinates from first spot or destination city
        first_spot = curated_spots[0]
        lat = first_spot.get("latitude")
        lon = first_spot.get("longitude")
        
        # Try to get coordinates from any spot if first spot doesn't have them
        if not lat or not lon:
            for spot in curated_spots[1:]:
                lat = spot.get("latitude")
                lon = spot.get("longitude")
                if lat and lon:
                    break
        
        if lat and lon:
            try:
                weather_data = get_weather_for_destination(
                    latitude=float(lat),
                    longitude=float(lon),
                    travel_dates=travel_window,
                    num_days=num_days
                )
                
                # Build detailed weather considerations from actual data
                if weather_data:
                    current = weather_data.get("current_weather")
                    forecast = weather_data.get("forecast", [])
                    warnings = weather_data.get("warnings", [])
                    
                    weather_parts = []
                    
                    # Current weather
                    if current:
                        temp = current.get("temperature")
                        desc = current.get("description", "")
                        humidity = current.get("humidity")
                        wind_speed = current.get("wind_speed")
                        precipitation = current.get("precipitation", 0)
                        
                        if temp is not None:
                            weather_parts.append(f"**Current Conditions:** {temp:.1f}°C, {desc}")
                            if humidity is not None:
                                weather_parts.append(f"{humidity:.0f}% humidity")
                            if wind_speed is not None:
                                weather_parts.append(f"Wind: {wind_speed:.1f} km/h")
                            if precipitation > 0:
                                weather_parts.append(f"Precipitation: {precipitation:.1f}mm")
                    
                    # Forecast summary
                    if forecast and len(forecast) > 0:
                        forecast_parts = []
                        for i, day_forecast in enumerate(forecast[:min(3, num_days)]):
                            date = day_forecast.get("date", "")
                            temp_max = day_forecast.get("temperature_max")
                            temp_min = day_forecast.get("temperature_min")
                            day_desc = day_forecast.get("description", "")
                            precip = day_forecast.get("precipitation", 0)
                            
                            if date:
                                # Format date nicely
                                try:
                                    date_obj = datetime.fromisoformat(date.split('T')[0])
                                    date_str = date_obj.strftime("%b %d")
                                except:
                                    date_str = f"Day {i+1}"
                            else:
                                date_str = f"Day {i+1}"
                            
                            forecast_text = f"{date_str}: {day_desc}"
                            if temp_max is not None and temp_min is not None:
                                forecast_text += f" ({temp_min:.0f}°C - {temp_max:.0f}°C)"
                            if precip > 0:
                                forecast_text += f", {precip:.1f}mm rain"
                            forecast_parts.append(forecast_text)
                        
                        if forecast_parts:
                            weather_parts.append(f"**Forecast:** {' | '.join(forecast_parts)}")
                    
                    # Warnings
                    if warnings:
                        weather_parts.append(f"**Warnings:** {' '.join(warnings)}")
                    
                    weather_considerations = " | ".join(weather_parts) if weather_parts else ""
                    
                    # Fallback if no data extracted
                    if not weather_considerations:
                        weather_considerations = _weather_note(req.destination_city, start_date, num_days, req.travel_date)
                    else:
                        # Add location context
                        location = req.destination_city or "your destination"
                        weather_considerations = f"Weather for {location}: {weather_considerations}"
                else:
                    weather_considerations = _weather_note(req.destination_city, start_date, num_days, req.travel_date)
            except Exception as e:
                print(f"[Weather] Failed to fetch weather data: {e}")
                import traceback
                traceback.print_exc()
                weather_considerations = _weather_note(req.destination_city, start_date, num_days, req.travel_date)
        else:
            print(f"[Weather] No coordinates found for spots. First spot: {curated_spots[0].get('name') if curated_spots else 'N/A'}")
            weather_considerations = _weather_note(req.destination_city, start_date, num_days, req.travel_date)
    else:
        weather_considerations = _weather_note(req.destination_city, start_date, num_days, req.travel_date)

    # Prepare transport costs with comprehensive breakdown
    enhanced_transport_costs = transport_costs.copy()
    if comprehensive_cost_breakdown:
        enhanced_transport_costs["comprehensive_breakdown"] = comprehensive_cost_breakdown
    if scenario_comparison:
        enhanced_transport_costs["scenario_comparison"] = scenario_comparison

    return ItineraryResponse(
        query_used="preferences-based-embedding-search",
        num_spots_considered=len(spots),
        days=days,
        total_estimated_cost=total_cost,
        currency="PKR",
        pretty_itinerary_text=None,
        budget_breakdown=budget_breakdown or None,
        recommended_hotels=recommended_hotels or None,
        weather_considerations=weather_considerations,
        travel_window=travel_window,
        transport_costs=enhanced_transport_costs,
        weather_data=weather_data,
    )


# ---------------------------------------------------------
# BUILD RETRIEVAL QUERY + GET SPOTS FROM VECTOR DB
# ---------------------------------------------------------
def _build_query_and_fetch_spots(req: ItineraryRequest) -> List[Dict[str, Any]]:
    preferences_dict = req.dict()

    results = search_spots_for_preferences(
        preferences=preferences_dict,
        top_k=50  # Get more spots to ensure we have enough for multi-day itineraries
    )
    
    # Debug: Print how many spots were retrieved
    print(f"[DEBUG] Retrieved {len(results)} spots from vector search")
    if req.destination_city:
        city_spots = [s for s in results if _normalize_city_name(str(s.get("city", ""))) == _normalize_city_name(req.destination_city)]
        print(f"[DEBUG] Found {len(city_spots)} spots matching city: {req.destination_city}")

    if not isinstance(results, list):
        raise HTTPException(status_code=500, detail="Vector search returned an invalid format.")

    return results


# ---------------------------------------------------------
# MAIN ENDPOINT — COMBINES EVERYTHING
# ---------------------------------------------------------
@router.post("/generate", response_model=ItineraryResponse)
def generate_itinerary(req: ItineraryRequest):
    """
    Steps:
    1. User fills form (ItineraryRequest) - validated by Pydantic
    2. Do vector search (embeddings + Chroma)
    3. Create structured itinerary (days + cost)
    4. Generate beautiful itinerary text using LLM (Groq → OpenAI fallback)
    """
    try:
        # Additional validation checks
        if req.budget_amount and req.budget_amount < 10000:
            raise HTTPException(
                status_code=400,
                detail="Budget amount must be at least 10,000 PKR"
            )
        
        if req.num_days > 30:
            raise HTTPException(
                status_code=400,
                detail="Number of days cannot exceed 30"
            )
        
        if req.num_of_people and req.num_of_people > 20:
            raise HTTPException(
                status_code=400,
                detail="Number of travelers cannot exceed 20"
            )
        
        # Validate budget per person per day
        if req.budget_amount and req.num_days and req.num_of_people:
            budget_per_person_per_day = req.budget_amount / (req.num_days * req.num_of_people)
            if budget_per_person_per_day < 500:
                raise HTTPException(
                    status_code=400,
                    detail=f"Budget too low: {budget_per_person_per_day:.0f} PKR per person per day. Minimum 500 PKR required"
                )
        # 1) RETRIEVAL
        spots = _build_query_and_fetch_spots(req)
        llm_ready_spots = _filter_spots_for_destination(spots, req.destination_city, req.region) or spots

        # 2) RULE-BASED (STRUCTURED ITINERARY)
        itinerary = _simple_itinerary_from_spots(req, spots)

        # 3) CLEAN SPOTS FOR LLM (include images)
        llm_spots = []
        all_itinerary_images = []  # Collect all images for the response
        
        for rec in llm_ready_spots:
            name = _clean_spot_name(rec.get("name") or rec.get("spot_name"))
            if not name:
                continue
            city = rec.get("city") or req.destination_city or ""
            region = rec.get("region") or (req.region or "")
            desc = rec.get("description") or rec.get("doc") or rec.get("desc") or ""
            
            # Extract images
            images = rec.get("images")
            if images:
                if isinstance(images, str):
                    try:
                        images = json.loads(images)
                    except:
                        images = [images] if images else []
                elif not isinstance(images, list):
                    images = []
            else:
                image_url = rec.get("image_url")
                images = [image_url] if image_url else []
            
            # Filter out empty images
            images = [img for img in images if img]
            
            # Add to all images collection
            for img in images:
                if img and img not in all_itinerary_images:
                    all_itinerary_images.append(img)

            llm_spots.append(
                {
                    "name": name,
                    "city": city,
                    "region": region,
                    "desc": desc,
                    "images": images[:3] if images else [],  # Limit to 3 images per spot for LLM
                }
            )

        # Limit to avoid massive prompt
        llm_spots = llm_spots[:15]

        # 4) LLM GENERATION
        req_payload = req.dict()
        req_payload["travel_window"] = itinerary.travel_window
        req_payload["recommended_hotels"] = itinerary.recommended_hotels

        # Get language preference from request (default to 'en')
        language = req.language if hasattr(req, 'language') and req.language else 'en'
        if language not in ['en', 'ur']:
            language = 'en'
        pretty_text = generate_itinerary_llm(req_payload, llm_spots, language)

        # 5) ADD TO RESPONSE
        itinerary.pretty_itinerary_text = pretty_text
        
        # Collect all images from all days
        all_day_images = []
        for day_plan in itinerary.days:
            if day_plan.images:
                for img in day_plan.images:
                    if img and img not in all_day_images:
                        all_day_images.append(img)
        
        # Also add images from all spots (up to 20 total)
        for img in all_itinerary_images:
            if img and img not in all_day_images and len(all_day_images) < 20:
                all_day_images.append(img)
        
        itinerary.all_images = all_day_images if all_day_images else None

        return itinerary

    except HTTPException:
        raise
    except Exception as e:
        print(" generate_itinerary crashed:", repr(e))
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {e}")
