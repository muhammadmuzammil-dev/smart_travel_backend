"""
Comprehensive budget calculator.
Uses real hotel data from structured_cities.json + dynamic pricing.
Endpoint: POST /budget/calculate
"""

import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

from utils.transport_calculator import haversine_distance

router = APIRouter()

# ── City coordinates ─────────────────────────────────────────────────────────
CITY_COORDS: Dict[str, tuple] = {
    "Karachi": (24.8607, 67.0011), "Lahore": (31.5204, 74.3587),
    "Islamabad": (33.6844, 73.0479), "Rawalpindi": (33.5651, 73.0169),
    "Faisalabad": (31.4504, 73.1350), "Multan": (30.1798, 71.4214),
    "Peshawar": (34.0151, 71.5249), "Quetta": (30.1798, 66.9750),
    "Sialkot": (32.4945, 74.5229), "Gujranwala": (32.1877, 74.1945),
    "Hyderabad": (25.3960, 68.3578), "Sargodha": (32.0740, 72.6861),
    "Bahawalpur": (29.3956, 71.6836), "Sukkur": (27.7052, 68.8574),
    "Sheikhupura": (31.7167, 73.9850), "Rahim Yar Khan": (28.4202, 70.2952),
    "Mardan": (34.2010, 72.0490), "Mingora": (34.7717, 72.3600),
    "Swat": (34.7717, 72.3600), "Naran": (34.9051, 73.6517),
    "Hunza": (36.3167, 74.6500), "Skardu": (35.2971, 75.6333),
    "Murree": (33.9042, 73.3940), "Gilgit": (35.9219, 74.3083),
    "Chitral": (35.8510, 71.7889), "Abbottabad": (34.1491, 73.2117),
    "Mansehra": (34.3298, 73.1972), "Haripur": (33.9944, 72.9355),
    "Chakwal": (32.9302, 72.8508), "Dera Ghazi Khan": (30.0489, 70.6338),
    "Larkana": (27.5570, 68.2137), "Nawabshah": (26.2442, 68.4100),
    "Gujrat": (32.5736, 74.0790), "Khanewal": (30.3019, 71.9323),
    "Muzaffargarh": (30.0701, 71.1934), "Kasur": (31.1200, 74.4500),
}

MOUNTAIN_CITIES = {
    "Naran", "Hunza", "Skardu", "Gilgit", "Chitral", "Murree",
    "Swat", "Mingora", "Mansehra", "Abbottabad", "Haripur", "Chakwal",
    "Kaghan", "Kalam", "Shogran", "Nathia Gali", "Arang Kel",
}

PEAK_MONTHS = {5, 6, 7, 8, 12}   # May–Aug (summer), Dec (winter hols)

# ── Pricing tables ────────────────────────────────────────────────────────────
FOOD_RATES = {
    "low":    {"breakfast": 150, "lunch": 300,  "dinner": 500,  "snacks": 100, "label": "Budget meals / dhabas"},
    "medium": {"breakfast": 450, "lunch": 900,  "dinner": 1500, "snacks": 250, "label": "Mid-range restaurants"},
    "high":   {"breakfast": 900, "lunch": 2000, "dinner": 3500, "snacks": 500, "label": "Fine dining / hotel restaurants"},
}

ACTIVITY_RATES = {
    "low":    {"sightseeing": 200, "entrance_fees": 100, "guided_tour": 0,    "adventure": 0,    "label": "Free sightseeing + basic entry"},
    "medium": {"sightseeing": 500, "entrance_fees": 300, "guided_tour": 1000, "adventure": 1500, "label": "Mix of guided and self-guided tours"},
    "high":   {"sightseeing": 1000,"entrance_fees": 600, "guided_tour": 2500, "adventure": 4000, "label": "Premium experiences & adventure sports"},
}

# Ride service rates (PKR base + per km)
RIDE_RATES = {
    "Uber Go":        {"base": 150, "per_km": 32, "peak_mult": 1.5},
    "UberMini":       {"base": 120, "per_km": 28, "peak_mult": 1.5},
    "Careem Go":      {"base": 140, "per_km": 30, "peak_mult": 1.4},
    "InDrive":        {"base": 100, "per_km": 25, "peak_mult": 1.0},
    "Bykea Bike":     {"base": 60,  "per_km": 15, "peak_mult": 1.2, "max_km": 80},
}

# Fallback hotel pricing when city data missing
FALLBACK_HOTELS = {
    "low":    [{"name": "Economy Guesthouse", "price_per_night": 2000}, {"name": "Budget Inn", "price_per_night": 2500}],
    "medium": [{"name": "Standard Hotel 3★",  "price_per_night": 8000}, {"name": "Mid-Range Resort", "price_per_night": 9500}],
    "high":   [{"name": "Luxury Hotel 5★",    "price_per_night": 28000}, {"name": "Premium Resort", "price_per_night": 35000}],
}

# ── Load hotel data ───────────────────────────────────────────────────────────
_hotel_cache: Dict[str, Any] = {}

def _load_hotels() -> Dict[str, Any]:
    global _hotel_cache
    if _hotel_cache:
        return _hotel_cache
    path = Path(__file__).parent.parent / "data" / "structured_cities.json"
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            for city in data:
                name = (city.get("city") or city.get("name") or "").lower()
                if name:
                    _hotel_cache[name] = city
        elif isinstance(data, dict):
            for k, v in data.items():
                _hotel_cache[k.lower()] = v
    except Exception:
        pass
    return _hotel_cache


def _get_hotels_for_city(city: str, budget_level: str) -> List[Dict]:
    data  = _load_hotels()
    entry = data.get(city.lower())
    if not entry:
        return FALLBACK_HOTELS.get(budget_level, FALLBACK_HOTELS["medium"])

    # Structured format: {"hotels": {"low": [...], "mid": [...], "high": [...]}}
    hotels_obj = entry.get("hotels", {})
    key_map    = {"low": ["low"], "medium": ["mid", "medium"], "high": ["high"]}
    candidates = []
    for k in key_map.get(budget_level, ["mid"]):
        candidates.extend(hotels_obj.get(k, []))

    if not candidates:
        # Try all tiers flattened
        for v in hotels_obj.values():
            if isinstance(v, list):
                candidates.extend(v)

    if not candidates:
        return FALLBACK_HOTELS.get(budget_level, FALLBACK_HOTELS["medium"])

    # Normalise to {name, price_per_night}
    result = []
    for h in candidates[:6]:
        if isinstance(h, dict):
            name  = h.get("name") or h.get("hotel_name") or "Hotel"
            price = h.get("price") or h.get("price_per_night") or h.get("price_pkr")
            if isinstance(price, str):
                digits = "".join(c for c in price if c.isdigit())
                price  = float(digits) if digits else 0.0
            result.append({"name": name, "price_per_night": float(price or 0)})
        elif isinstance(h, str):
            result.append({"name": h, "price_per_night": 0.0})

    return result if result else FALLBACK_HOTELS.get(budget_level, FALLBACK_HOTELS["medium"])


# ── Dynamic pricing helpers ───────────────────────────────────────────────────

def _is_peak(travel_date: Optional[str]) -> bool:
    month = datetime.now().month
    if travel_date:
        try:
            month = datetime.fromisoformat(travel_date).month
        except Exception:
            pass
    return month in PEAK_MONTHS


def _terrain_mult(city: str) -> float:
    return 1.3 if city in MOUNTAIN_CITIES else 1.0


def _season_mult(is_peak: bool) -> float:
    return 1.25 if is_peak else 1.0


def _occupancy_mult() -> float:
    """Simulate demand: weekends ~10% more expensive."""
    return 1.1 if datetime.now().weekday() >= 4 else 1.0


# ── Schemas ───────────────────────────────────────────────────────────────────

class BudgetRequest(BaseModel):
    destination_city:  str
    origin_city:       Optional[str] = None
    budget_level:      str           = Field("medium", pattern="^(low|medium|high)$")
    num_days:          int           = Field(3, ge=1, le=30)
    num_people:        int           = Field(1, ge=1, le=20)
    transport_mode:    str           = Field("ride_sharing")
    travel_date:       Optional[str] = None


class HotelOption(BaseModel):
    name:            str
    price_per_night: float
    price_total:     float
    price_per_person: float
    currency:        str = "PKR"
    tier:            str
    is_peak_priced:  bool


class TransportEstimate(BaseModel):
    service:         str
    fare_one_way:    float
    fare_return:     float
    fare_total:      float
    per_person:      float
    currency:        str = "PKR"
    distance_km:     float
    note:            str


class FoodBreakdown(BaseModel):
    breakfast:       float
    lunch:           float
    dinner:          float
    snacks:          float
    daily_per_person: float
    total:           float
    label:           str


class ActivityBreakdown(BaseModel):
    sightseeing:     float
    entrance_fees:   float
    guided_tour:     float
    adventure:       float
    daily_per_person: float
    total:           float
    label:           str


class BudgetTotals(BaseModel):
    accommodation:   float
    transport:       float
    food:            float
    activities:      float
    subtotal:        float
    contingency:     float
    grand_total:     float
    per_person:      float
    per_day:         float
    currency:        str = "PKR"


class BudgetResponse(BaseModel):
    destination_city:    str
    origin_city:         Optional[str]
    num_days:            int
    num_people:          int
    budget_level:        str
    is_peak_season:      bool
    hotels:              List[HotelOption]
    recommended_hotel:   HotelOption
    transport_options:   List[TransportEstimate]
    food:                FoodBreakdown
    activities:          ActivityBreakdown
    totals:              BudgetTotals
    savings_tips:        List[str]
    calculated_at:       str


# ── Calculation functions ─────────────────────────────────────────────────────

def _calc_hotels(
    city: str, budget_level: str, num_nights: int, num_people: int,
    is_peak: bool
) -> tuple[List[HotelOption], HotelOption]:

    raw_hotels  = _get_hotels_for_city(city, budget_level)
    terrain     = _terrain_mult(city)
    season      = _season_mult(is_peak)
    occupancy   = _occupancy_mult()
    num_rooms   = max(1, math.ceil(num_people / 2))
    options: List[HotelOption] = []

    for h in raw_hotels:
        base   = h["price_per_night"]
        if base <= 0:
            # Use fallback pricing if missing
            fallback_prices = {"low": 2500, "medium": 9000, "high": 28000}
            base = fallback_prices.get(budget_level, 9000)

        nightly = base * terrain * season * occupancy
        total   = nightly * num_nights * num_rooms
        options.append(HotelOption(
            name            = h["name"],
            price_per_night = round(nightly, 0),
            price_total     = round(total, 0),
            price_per_person= round(total / max(num_people, 1), 0),
            tier            = budget_level,
            is_peak_priced  = is_peak,
        ))

    if not options:
        # Absolute fallback
        base  = {"low": 2500, "medium": 9000, "high": 28000}[budget_level]
        total = base * num_nights * math.ceil(num_people / 2)
        opt   = HotelOption(
            name="Standard Hotel", price_per_night=base,
            price_total=total, price_per_person=total // max(num_people, 1),
            tier=budget_level, is_peak_priced=is_peak,
        )
        options = [opt]

    # Recommended = median price option
    options.sort(key=lambda x: x.price_per_night)
    recommended = options[len(options) // 2]
    return options, recommended


def _calc_transport(
    origin: Optional[str], destination: str,
    num_people: int, transport_mode: str
) -> List[TransportEstimate]:

    if not origin or origin.lower() == destination.lower():
        return []

    o_coords = CITY_COORDS.get(origin)
    d_coords = CITY_COORDS.get(destination)
    if not o_coords or not d_coords:
        return []

    dist_km  = round(haversine_distance(*o_coords, *d_coords), 1)
    terrain  = _terrain_mult(destination)
    estimates: List[TransportEstimate] = []

    for name, rate in RIDE_RATES.items():
        max_km = rate.get("max_km")
        if max_km and dist_km > max_km:
            continue
        rides     = max(1, math.ceil(num_people / 4)) if "Bike" not in name else num_people
        one_way   = (rate["base"] + rate["per_km"] * dist_km) * rides * terrain
        total_fare = one_way * 2  # return trip
        estimates.append(TransportEstimate(
            service     = name,
            fare_one_way= round(one_way, 0),
            fare_return = round(one_way, 0),
            fare_total  = round(total_fare, 0),
            per_person  = round(total_fare / max(num_people, 1), 0),
            distance_km = dist_km,
            note        = f"{dist_km:.0f} km · {name}" + (" · Negotiable" if "InDrive" in name else ""),
        ))

    return sorted(estimates, key=lambda x: x.fare_total)


def _calc_food(num_days: int, num_people: int, budget_level: str) -> FoodBreakdown:
    rates = FOOD_RATES[budget_level]
    daily = rates["breakfast"] + rates["lunch"] + rates["dinner"] + rates["snacks"]
    total = daily * num_days * num_people
    return FoodBreakdown(
        breakfast        = rates["breakfast"],
        lunch            = rates["lunch"],
        dinner           = rates["dinner"],
        snacks           = rates["snacks"],
        daily_per_person = daily,
        total            = round(total, 0),
        label            = rates["label"],
    )


def _calc_activities(num_days: int, num_people: int, budget_level: str) -> ActivityBreakdown:
    rates = ACTIVITY_RATES[budget_level]
    daily = sum(v for k, v in rates.items() if k != "label")
    total = daily * num_days * num_people
    return ActivityBreakdown(
        sightseeing      = rates["sightseeing"],
        entrance_fees    = rates["entrance_fees"],
        guided_tour      = rates["guided_tour"],
        adventure        = rates["adventure"],
        daily_per_person = daily,
        total            = round(total, 0),
        label            = rates["label"],
    )


def _savings_tips(budget_level: str, destination: str, is_peak: bool) -> List[str]:
    tips = []
    if is_peak:
        tips.append("Travelling in off-peak months (Sep–Nov, Jan–Apr) can save 20–30% on hotels.")
    if destination in MOUNTAIN_CITIES:
        tips.append("Book accommodation at least 2 weeks in advance for mountain destinations.")
    if budget_level == "high":
        tips.append("Book hotel packages for meals to save up to 15% on food costs.")
    if budget_level == "low":
        tips.append("Local dhabas and hostels significantly reduce costs without sacrificing safety.")
    tips.append("Use InDrive for long-distance travel — negotiate fares 10–20% below market rate.")
    tips.append("Group bookings (4+ people) unlock discounts at most hotels and tour operators.")
    return tips


# ── Route ────────────────────────────────────────────────────────────────────

@router.post("/calculate", response_model=BudgetResponse, summary="Comprehensive budget estimate")
async def calculate_budget(req: BudgetRequest):
    is_peak   = _is_peak(req.travel_date)
    num_nights = req.num_days   # same number of nights as days

    hotels, recommended = _calc_hotels(
        req.destination_city, req.budget_level,
        num_nights, req.num_people, is_peak,
    )
    transport = _calc_transport(
        req.origin_city, req.destination_city,
        req.num_people, req.transport_mode,
    )
    food       = _calc_food(req.num_days, req.num_people, req.budget_level)
    activities = _calc_activities(req.num_days, req.num_people, req.budget_level)

    # Use cheapest transport for totals
    transport_cost = transport[0].fare_total if transport else 0.0
    subtotal       = recommended.price_total + transport_cost + food.total + activities.total
    contingency    = round(subtotal * 0.10, 0)
    grand_total    = round(subtotal + contingency, 0)

    totals = BudgetTotals(
        accommodation = recommended.price_total,
        transport     = round(transport_cost, 0),
        food          = food.total,
        activities    = activities.total,
        subtotal      = round(subtotal, 0),
        contingency   = contingency,
        grand_total   = grand_total,
        per_person    = round(grand_total / max(req.num_people, 1), 0),
        per_day       = round(grand_total / max(req.num_days, 1), 0),
    )

    return BudgetResponse(
        destination_city  = req.destination_city,
        origin_city       = req.origin_city,
        num_days          = req.num_days,
        num_people        = req.num_people,
        budget_level      = req.budget_level,
        is_peak_season    = is_peak,
        hotels            = hotels,
        recommended_hotel = recommended,
        transport_options = transport,
        food              = food,
        activities        = activities,
        totals            = totals,
        savings_tips      = _savings_tips(req.budget_level, req.destination_city, is_peak),
        calculated_at     = datetime.now(timezone.utc).isoformat(),
    )
