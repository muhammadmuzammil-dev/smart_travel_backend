"""
Comprehensive Travel Cost Optimization Engine
Provides detailed, itemized cost breakdowns with ride logistics and scenario comparisons.
"""

import math
from typing import List, Dict, Any, Optional, Tuple
from urllib.parse import quote


# ============================================================================
# ASSUMPTIONS & PRICING DATA
# ============================================================================

# Fuel rates (PKR per liter, as of 2024)
FUEL_RATE_PKR_PER_LITER = 280.0  # Average petrol price
AVERAGE_FUEL_EFFICIENCY_KM_PER_LITER = 12.0  # Average car fuel efficiency (city driving)
MOUNTAIN_FUEL_EFFICIENCY_KM_PER_LITER = 8.0  # Reduced efficiency in mountain terrain

# InDrive pricing assumptions (PKR) - fuel-backed model
# Base fare covers driver time and vehicle overhead
INDRIVE_BASE_FARE = 200.0  # Increased to account for driver return time
INDRIVE_PER_KM = 35.0  # Increased from 30.0 to be more realistic
INDRIVE_SURGE_MULTIPLIER = 1.2  # 20% surge during peak hours
INDRIVE_PEAK_HOURS = ["07:00-10:00", "17:00-20:00"]

# Terrain multipliers for mountain routes (Kaghan, Naran, Batakundi, Sharan, etc.)
TERRAIN_MULTIPLIER_PLAINS = 1.0  # Normal city/plains driving
TERRAIN_MULTIPLIER_MOUNTAIN = 1.30  # 30% premium for mountain terrain (uphill load, road conditions)
RETURN_BUFFER_PERCENTAGE = 0.12  # 12% buffer for driver return deadhead

# Public transport rates (PKR)
BUS_FARE_PER_KM = 2.5
TRAIN_FARE_PER_KM = 1.5
MINIMUM_BUS_FARE = 50.0

# Accommodation rates per night (PKR) - base rates
ACCOMMODATION_RATES = {
    "budget": {
        "guesthouse": 2000,
        "hostel": 1500,
        "basic_hotel": 3000,
        "description": "Budget-friendly options"
    },
    "mid_range": {
        "hotel_3star": 8000,  # Low-end mid-range
        "airbnb": 6000,
        "resort_basic": 10000,
        "range_min": 8000,  # For location-based variance
        "range_max": 11000,  # Peak season in tourist areas
        "description": "Comfortable mid-range options (8,000-11,000 PKR/night)"
    },
    "premium": {
        "hotel_4star": 20000,
        "hotel_5star": 35000,
        "luxury_resort": 40000,
        "description": "Premium luxury options"
    }
}

# Location and season multipliers
PEAK_SEASON_MULTIPLIER = 1.25  # 25% increase during peak season (summer, holidays)
TOURIST_AREA_MULTIPLIER = 1.15  # 15% premium for tourist hotspots (Naran, Kaghan, etc.)

# Food costs per person per meal (PKR) - adjusted for tourist areas
# Tourist areas (Naran, Shogran, Kaghan) have 20% premium over city pricing
FOOD_COSTS = {
    "budget": {
        "breakfast": 200,
        "lunch": 300,
        "dinner": 400,
        "snacks": 100,
        "description": "Street food and local restaurants"
    },
    "mid_range": {
        "breakfast": 600,  # Increased from 500 (20% for tourist areas)
        "lunch": 1000,  # Increased from 800 (25% for tourist areas)
        "dinner": 1800,  # Increased from 1200 (50% - Naran/Shogran dinner: 1,500-2,000 PKR)
        "snacks": 250,  # Increased from 200
        "description": "Mix of street food and restaurants (tourist area pricing)"
    },
    "premium": {
        "breakfast": 1500,
        "lunch": 2500,
        "dinner": 4000,
        "snacks": 500,
        "description": "Restaurants and fine dining"
    }
}

# Tourist area food multiplier (applied on top of base rates)
TOURIST_AREA_FOOD_MULTIPLIER = 1.20  # 20% premium for tourist destinations

# Activity costs per person (PKR) - reduced to realistic levels
# Most activities in Kaghan/Naran region are free sightseeing
# Guided tours and adventure activities are occasional, not daily
ACTIVITY_COSTS = {
    "budget": {
        "sightseeing": 300,  # Reduced from 500 (mostly free)
        "entrance_fee": 200,
        "guided_tour": 500,  # Reduced from 1000 (occasional, not daily)
        "adventure": 1500,  # Reduced from 2000
        "description": "Basic activities and sightseeing (mostly free)"
    },
    "mid_range": {
        "sightseeing": 500,  # Reduced from 1000 (mostly free)
        "entrance_fee": 400,  # Reduced from 500
        "guided_tour": 1500,  # Reduced from 2500 (occasional jeep rides)
        "adventure": 3000,  # Reduced from 5000 (not daily)
        "description": "Standard activities with occasional guided tours"
    },
    "premium": {
        "sightseeing": 1000,  # Reduced from 2000
        "entrance_fee": 800,  # Reduced from 1000
        "guided_tour": 3000,  # Reduced from 5000
        "adventure": 6000,  # Reduced from 10000
        "description": "Premium activities and exclusive experiences"
    }
}

# Activity frequency assumptions (reduced from previous estimates)
ACTIVITIES_PER_DAY = 1.5  # Reduced from 2.0 (most days are free sightseeing)
GUIDED_TOUR_FREQUENCY = 0.2  # 20% of days (reduced from 30%)
ADVENTURE_FREQUENCY = 0.15  # 15% of days (reduced from 20%)

# Contingency buffer (% of total cost)
CONTINGENCY_BUFFER = 0.15  # 15% buffer for unexpected expenses


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def _generate_google_maps_link(origin: str, destination: str, origin_coords: Optional[Tuple[float, float]] = None, 
                                dest_coords: Optional[Tuple[float, float]] = None, 
                                waypoints: Optional[List[Tuple[float, float]]] = None) -> str:
    """
    Generate Google Maps route link with proper error handling.
    Falls back to destination-only if routing fails.
    """
    try:
        # Prefer coordinates for accuracy
        if origin_coords and dest_coords:
            lat1, lon1 = origin_coords
            lat2, lon2 = dest_coords
            
            # Validate coordinates
            if not (-90 <= lat1 <= 90 and -180 <= lon1 <= 180):
                raise ValueError(f"Invalid origin coordinates: {lat1}, {lon1}")
            if not (-90 <= lat2 <= 90 and -180 <= lon2 <= 180):
                raise ValueError(f"Invalid destination coordinates: {lat2}, {lon2}")
            
            # Build URL with waypoints if provided
            base_url = "https://www.google.com/maps/dir/?api=1"
            origin_param = f"origin={lat1},{lon1}"
            dest_param = f"destination={lat2},{lon2}"
            
            # Add waypoints if provided (for multi-stop routes)
            waypoint_params = ""
            if waypoints and len(waypoints) > 0:
                # Limit to 8 waypoints (Google Maps API limit)
                valid_waypoints = []
                for wp in waypoints[:8]:
                    if len(wp) == 2 and -90 <= wp[0] <= 90 and -180 <= wp[1] <= 180:
                        valid_waypoints.append(f"{wp[0]},{wp[1]}")
                
                if valid_waypoints:
                    waypoint_params = "&waypoints=" + "|".join(valid_waypoints)
            
            return f"{base_url}&{origin_param}&{dest_param}{waypoint_params}&travelmode=driving"
        
        # Fallback to place names if coordinates not available
        elif origin and destination:
            origin_encoded = quote(origin)
            dest_encoded = quote(destination)
            return f"https://www.google.com/maps/dir/?api=1&origin={origin_encoded}&destination={dest_encoded}&travelmode=driving"
        
        # Final fallback: destination only (if origin is missing or invalid)
        elif destination:
            if dest_coords:
                lat, lon = dest_coords
                return f"https://www.google.com/maps/search/?api=1&query={lat},{lon}"
            else:
                dest_encoded = quote(destination)
                return f"https://www.google.com/maps/search/?api=1&query={dest_encoded}"
        
        else:
            # Ultimate fallback
            return "https://www.google.com/maps"
            
    except Exception as e:
        # Error handling: fallback to destination search
        print(f"Error generating Google Maps link: {e}")
        if dest_coords:
            lat, lon = dest_coords
            return f"https://www.google.com/maps/search/?api=1&query={lat},{lon}"
        elif destination:
            dest_encoded = quote(destination)
            return f"https://www.google.com/maps/search/?api=1&query={dest_encoded}"
        else:
            return "https://www.google.com/maps"


def _generate_indrive_link(origin: str, destination: str) -> str:
    """Generate InDrive deep link for ride booking."""
    # InDrive uses a specific URL format
    origin_encoded = quote(origin)
    dest_encoded = quote(destination)
    # Note: Actual InDrive app uses custom URL scheme, this is a placeholder
    # In production, you'd use: indrive://ride?origin={origin}&destination={destination}
    return f"https://indrive.com/en/ride/?origin={origin_encoded}&destination={dest_encoded}"


def _estimate_travel_time(distance_km: float, mode: str) -> Tuple[float, str]:
    """
    Estimate travel time based on distance and mode.
    Returns (hours, formatted_string).
    """
    # Average speeds (km/h)
    speeds = {
        "own_car": 60.0,  # Average highway speed
        "public_transport": 50.0,  # Bus with stops
        "ride_sharing": 55.0,  # Similar to own car
        "mixed": 52.0  # Average
    }
    
    speed = speeds.get(mode.lower(), 50.0)
    hours = distance_km / speed if speed > 0 else 0
    
    # Format as hours and minutes
    hours_int = int(hours)
    minutes = int((hours - hours_int) * 60)
    
    if hours_int == 0:
        return hours, f"{minutes} minutes"
    elif minutes == 0:
        return hours, f"{hours_int} hour{'s' if hours_int > 1 else ''}"
    else:
        return hours, f"{hours_int}h {minutes}m"


def _calculate_indrive_cost(
    distance_km: float, 
    num_people: int, 
    is_peak: bool = False,
    is_mountain_terrain: bool = False
) -> Dict[str, Any]:
    """
    Calculate InDrive cost using fuel-backed model with terrain multipliers and return buffer.
    
    Formula: base_fare + (distance × per_km × terrain_multiplier) + return_buffer
    """
    base_fare = INDRIVE_BASE_FARE
    per_km = INDRIVE_PER_KM
    surge = INDRIVE_SURGE_MULTIPLIER if is_peak else 1.0
    
    # Determine terrain multiplier
    terrain_multiplier = TERRAIN_MULTIPLIER_MOUNTAIN if is_mountain_terrain else TERRAIN_MULTIPLIER_PLAINS
    
    # Fuel-backed calculation
    # Base fare covers driver time and vehicle overhead
    # Per-km cost accounts for fuel: (fuel_rate / efficiency) × terrain_multiplier
    fuel_cost_per_km = (FUEL_RATE_PKR_PER_LITER / AVERAGE_FUEL_EFFICIENCY_KM_PER_LITER)
    if is_mountain_terrain:
        # Use reduced efficiency for mountain terrain
        fuel_cost_per_km = (FUEL_RATE_PKR_PER_LITER / MOUNTAIN_FUEL_EFFICIENCY_KM_PER_LITER)
    
    # Base calculation with terrain multiplier
    distance_cost = distance_km * per_km * terrain_multiplier
    
    # Add return buffer for driver deadhead (12%)
    return_buffer = distance_cost * RETURN_BUFFER_PERCENTAGE
    
    # Expected cost: base + distance (with terrain) + return buffer
    expected_cost = (base_fare + distance_cost + return_buffer) * surge
    
    # Cost ranges (accounting for traffic, route variations, driver negotiations)
    low_cost = expected_cost * 0.90  # 10% lower (off-peak, optimal route, good negotiation)
    high_cost = expected_cost * 1.30  # 30% higher (peak, traffic, longer route, driver counter-offers)
    
    # For multiple people, cost is per ride (can share)
    if num_people > 1:
        # InDrive allows sharing, so cost per person decreases
        cost_per_person = expected_cost / min(num_people, 4)  # Max 4 people per ride
        total_cost = expected_cost if num_people <= 4 else expected_cost * math.ceil(num_people / 4)
    else:
        cost_per_person = expected_cost
        total_cost = expected_cost
    
    return {
        "low": round(low_cost, 2),
        "expected": round(expected_cost, 2),
        "high": round(high_cost, 2),
        "per_person": round(cost_per_person, 2),
        "total": round(total_cost, 2),
        "surge_applied": is_peak,
        "terrain_multiplier": terrain_multiplier,
        "return_buffer": round(return_buffer, 2),
        "assumptions": {
            "base_fare_pkr": base_fare,
            "per_km_pkr": per_km,
            "surge_multiplier": surge if is_peak else 1.0,
            "fuel_rate_pkr_per_liter": FUEL_RATE_PKR_PER_LITER,
            "fuel_efficiency_km_per_liter": MOUNTAIN_FUEL_EFFICIENCY_KM_PER_LITER if is_mountain_terrain else AVERAGE_FUEL_EFFICIENCY_KM_PER_LITER,
            "terrain_type": "mountain" if is_mountain_terrain else "plains",
            "return_buffer_percentage": RETURN_BUFFER_PERCENTAGE * 100
        }
    }


# ============================================================================
# MAIN COST OPTIMIZATION FUNCTIONS
# ============================================================================

def generate_ride_details(
    origin: str,
    destination: str,
    origin_coords: Optional[Tuple[float, float]] = None,
    dest_coords: Optional[Tuple[float, float]] = None,
    distance_km: Optional[float] = None,
    mode: str = "ride_sharing",
    num_people: int = 1,
    is_peak: bool = False
) -> Dict[str, Any]:
    """
    Generate detailed ride information with links and cost breakdown.
    """
    # Calculate distance if not provided
    if distance_km is None and origin_coords and dest_coords:
        try:
            from .transport_calculator import haversine_distance
            distance_km = haversine_distance(origin_coords[0], origin_coords[1], 
                                             dest_coords[0], dest_coords[1])
        except ImportError:
            # Fallback: simple distance calculation
            import math
            R = 6371.0  # Earth radius in km
            lat1_rad = math.radians(origin_coords[0])
            lon1_rad = math.radians(origin_coords[1])
            lat2_rad = math.radians(dest_coords[0])
            lon2_rad = math.radians(dest_coords[1])
            dlat = lat2_rad - lat1_rad
            dlon = lon2_rad - lon1_rad
            a = math.sin(dlat / 2)**2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon / 2)**2
            c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
            distance_km = R * c
    elif distance_km is None:
        distance_km = 0.0
    
    # Estimate travel time
    hours, time_str = _estimate_travel_time(distance_km, mode)
    
    # Generate links
    google_maps_link = _generate_google_maps_link(origin, destination, origin_coords, dest_coords)
    indrive_link = _generate_indrive_link(origin, destination) if mode == "ride_sharing" else None
    
    # Calculate costs
    ride_details = {
        "origin": origin,
        "destination": destination,
        "distance_km": round(distance_km, 2),
        "estimated_time": time_str,
        "estimated_time_hours": round(hours, 2),
        "mode": mode,
        "num_people": num_people,
        "google_maps_link": google_maps_link,
        "indrive_link": indrive_link,
    }
    
    # Detect mountain terrain based on destination name or coordinates
    is_mountain_terrain = _is_mountain_destination(origin, destination)
    
    # Add cost breakdown based on mode
    if mode == "ride_sharing":
        cost_breakdown = _calculate_indrive_cost(distance_km, num_people, is_peak, is_mountain_terrain)
        ride_details["cost_breakdown"] = cost_breakdown
        ride_details["terrain_type"] = "mountain" if is_mountain_terrain else "plains"
    elif mode == "own_car":
        fuel_cost = (distance_km / AVERAGE_FUEL_EFFICIENCY_KM_PER_LITER) * FUEL_RATE_PKR_PER_LITER
        ride_details["cost_breakdown"] = {
            "low": round(fuel_cost * 0.9, 2),
            "expected": round(fuel_cost, 2),
            "high": round(fuel_cost * 1.1, 2),
            "per_person": round(fuel_cost / num_people, 2),
            "total": round(fuel_cost, 2),
            "assumptions": {
                "fuel_rate_pkr_per_liter": FUEL_RATE_PKR_PER_LITER,
                "fuel_efficiency_km_per_liter": AVERAGE_FUEL_EFFICIENCY_KM_PER_LITER
            }
        }
    elif mode == "public_transport":
        cost_per_person = max(distance_km * BUS_FARE_PER_KM, MINIMUM_BUS_FARE)
        total_cost = cost_per_person * num_people
        ride_details["cost_breakdown"] = {
            "low": round(total_cost * 0.95, 2),
            "expected": round(total_cost, 2),
            "high": round(total_cost * 1.05, 2),
            "per_person": round(cost_per_person, 2),
            "total": round(total_cost, 2),
            "assumptions": {
                "bus_fare_per_km_pkr": BUS_FARE_PER_KM,
                "minimum_fare_pkr": MINIMUM_BUS_FARE
            }
        }
    else:
        # Mixed mode - average of own_car and public_transport
        car_cost = (distance_km / AVERAGE_FUEL_EFFICIENCY_KM_PER_LITER) * FUEL_RATE_PKR_PER_LITER
        bus_cost = max(distance_km * BUS_FARE_PER_KM, MINIMUM_BUS_FARE) * num_people
        mixed_cost = (car_cost * 0.4) + (bus_cost * 0.6)
        ride_details["cost_breakdown"] = {
            "low": round(mixed_cost * 0.9, 2),
            "expected": round(mixed_cost, 2),
            "high": round(mixed_cost * 1.1, 2),
            "per_person": round(mixed_cost / num_people, 2),
            "total": round(mixed_cost, 2),
            "assumptions": {
                "mix": "40% own car, 60% public transport"
            }
        }
    
    return ride_details


def _is_mountain_destination(origin: str, destination: str) -> bool:
    """Detect if destination is in mountain terrain (Kaghan, Naran, etc.)"""
    mountain_keywords = [
        "naran", "kaghan", "shogran", "batakundi", "sharan", 
        "hunza", "skardu", "gilgit", "chitral", "swat", "kalam",
        "malam jabba", "murree", "nathia gali", "ayubia"
    ]
    dest_lower = destination.lower()
    origin_lower = origin.lower()
    return any(keyword in dest_lower or keyword in origin_lower for keyword in mountain_keywords)


def _is_tourist_area(destination_city: str) -> bool:
    """Detect if destination is a tourist hotspot"""
    tourist_areas = [
        "naran", "kaghan", "shogran", "hunza", "skardu", "gilgit",
        "swat", "kalam", "chitral", "murree", "nathia gali"
    ]
    dest_lower = destination_city.lower()
    return any(area in dest_lower for area in tourist_areas)


def calculate_accommodation_costs(
    num_nights: int,
    num_people: int,
    travel_style: str = "mid_range",
    destination_city: Optional[str] = None,
    is_peak_season: bool = False
) -> Dict[str, Any]:
    """
    Calculate accommodation costs with location and season multipliers.
    """
    travel_style = travel_style.lower()
    if travel_style not in ["budget", "mid_range", "premium"]:
        travel_style = "mid_range"
    
    rates = ACCOMMODATION_RATES[travel_style]
    
    # Use average of available options
    if travel_style == "budget":
        cost_per_night = (rates["guesthouse"] + rates["hostel"] + rates["basic_hotel"]) / 3
    elif travel_style == "mid_range":
        # Use range for mid-range (8,000-11,000 PKR)
        if "range_min" in rates and "range_max" in rates:
            # Use midpoint, will be adjusted by multipliers
            cost_per_night = (rates["range_min"] + rates["range_max"]) / 2
        else:
            cost_per_night = (rates["hotel_3star"] + rates["airbnb"] + rates["resort_basic"]) / 3
    else:  # premium
        cost_per_night = (rates["hotel_4star"] + rates["hotel_5star"] + rates["luxury_resort"]) / 3
    
    # Apply location multiplier (tourist areas)
    if destination_city and _is_tourist_area(destination_city):
        cost_per_night *= TOURIST_AREA_MULTIPLIER
    
    # Apply peak season multiplier
    if is_peak_season:
        cost_per_night *= PEAK_SEASON_MULTIPLIER
    
    # Accommodation is typically per room, not per person
    # Assume 2 people per room
    num_rooms = math.ceil(num_people / 2)
    total_cost = cost_per_night * num_nights * num_rooms
    cost_per_person = total_cost / num_people
    
    return {
        "cost_per_night": round(cost_per_night, 2),
        "num_nights": num_nights,
        "num_rooms": num_rooms,
        "total_cost": round(total_cost, 2),
        "cost_per_person": round(cost_per_person, 2),
        "travel_style": travel_style,
        "description": rates["description"],
        "multipliers_applied": {
            "tourist_area": TOURIST_AREA_MULTIPLIER if (destination_city and _is_tourist_area(destination_city)) else 1.0,
            "peak_season": PEAK_SEASON_MULTIPLIER if is_peak_season else 1.0
        },
        "assumptions": {
            "people_per_room": 2,
            "options_available": list(rates.keys())[:-1] if "range_min" not in rates else [k for k in rates.keys() if k not in ["description", "range_min", "range_max"]]
        }
    }


def calculate_food_costs(
    num_days: int,
    num_people: int,
    travel_style: str = "mid_range",
    destination_city: Optional[str] = None
) -> Dict[str, Any]:
    """
    Calculate food costs with tourist area multiplier (20% premium).
    """
    travel_style = travel_style.lower()
    if travel_style not in ["budget", "mid_range", "premium"]:
        travel_style = "mid_range"
    
    costs = FOOD_COSTS[travel_style]
    
    # Apply tourist area multiplier if applicable
    is_tourist_area = destination_city and _is_tourist_area(destination_city)
    multiplier = TOURIST_AREA_FOOD_MULTIPLIER if is_tourist_area else 1.0
    
    # Per day: breakfast + lunch + dinner + snacks (already adjusted for tourist areas in base rates)
    cost_per_person_per_day = costs["breakfast"] + costs["lunch"] + costs["dinner"] + costs["snacks"]
    total_cost = cost_per_person_per_day * num_days * num_people
    
    return {
        "cost_per_person_per_day": round(cost_per_person_per_day, 2),
        "num_days": num_days,
        "total_cost": round(total_cost, 2),
        "cost_per_person": round(total_cost / num_people, 2),
        "breakdown": {
            "breakfast": round(costs["breakfast"] * num_days * num_people, 2),
            "lunch": round(costs["lunch"] * num_days * num_people, 2),
            "dinner": round(costs["dinner"] * num_days * num_people, 2),
            "snacks": round(costs["snacks"] * num_days * num_people, 2)
        },
        "travel_style": travel_style,
        "description": costs["description"],
        "tourist_area_pricing": is_tourist_area,
        "note": "Prices already include tourist area premium (20% increase)" if is_tourist_area else "City pricing"
    }


def calculate_activity_costs(
    num_days: int,
    num_people: int,
    travel_style: str = "mid_range"
) -> Dict[str, Any]:
    """
    Calculate activity and sightseeing costs with realistic frequencies.
    Most activities in mountain regions are free sightseeing.
    """
    travel_style = travel_style.lower()
    if travel_style not in ["budget", "mid_range", "premium"]:
        travel_style = "mid_range"
    
    costs = ACTIVITY_COSTS[travel_style]
    
    # Use reduced activity frequency (1.5 activities per day, mostly free sightseeing)
    activities_per_day = ACTIVITIES_PER_DAY
    cost_per_person_per_day = (costs["sightseeing"] + costs["entrance_fee"]) * activities_per_day
    base_total = cost_per_person_per_day * num_days * num_people
    
    # Add occasional guided tours (20% of days, not 30%)
    guided_tour_days = int(num_days * GUIDED_TOUR_FREQUENCY)
    guided_tour_cost = costs["guided_tour"] * guided_tour_days * num_people
    
    # Add occasional adventure activities (15% of days, not 20%)
    adventure_days = int(num_days * ADVENTURE_FREQUENCY)
    adventure_cost = costs["adventure"] * adventure_days * num_people
    
    total_cost = base_total + guided_tour_cost + adventure_cost
    
    return {
        "cost_per_person_per_day": round(total_cost / (num_days * num_people), 2),
        "num_days": num_days,
        "total_cost": round(total_cost, 2),
        "cost_per_person": round(total_cost / num_people, 2),
        "breakdown": {
            "sightseeing": round(costs["sightseeing"] * activities_per_day * num_days * num_people, 2),
            "entrance_fees": round(costs["entrance_fee"] * activities_per_day * num_days * num_people, 2),
            "guided_tours": round(guided_tour_cost, 2),
            "adventure": round(adventure_cost, 2)
        },
        "travel_style": travel_style,
        "description": costs["description"],
        "assumptions": {
            "activities_per_day": activities_per_day,
            "guided_tour_frequency": f"{GUIDED_TOUR_FREQUENCY * 100}% of days ({guided_tour_days} days)",
            "adventure_frequency": f"{ADVENTURE_FREQUENCY * 100}% of days ({adventure_days} days)",
            "note": "Most activities are free sightseeing. Guided tours and adventure activities are occasional."
        }
    }


def generate_comprehensive_cost_breakdown(
    origin_city: str,
    destination_city: str,
    num_days: int,
    num_people: int,
    travel_style: str,
    transport_rides: List[Dict[str, Any]],
    currency: str = "PKR",
    is_peak_season: bool = False
) -> Dict[str, Any]:
    """
    Generate comprehensive cost breakdown with all categories.
    Uses location-aware pricing for accommodation and food.
    """
    num_nights = num_days - 1 if num_days > 1 else 1
    
    # Calculate all cost categories with location awareness
    accommodation = calculate_accommodation_costs(
        num_nights, num_people, travel_style, 
        destination_city=destination_city,
        is_peak_season=is_peak_season
    )
    food = calculate_food_costs(num_days, num_people, travel_style, destination_city=destination_city)
    activities = calculate_activity_costs(num_days, num_people, travel_style)
    
    # Calculate transport costs from rides
    transport_total = sum(ride.get("cost_breakdown", {}).get("expected", 0) for ride in transport_rides)
    transport_low = sum(ride.get("cost_breakdown", {}).get("low", 0) for ride in transport_rides)
    transport_high = sum(ride.get("cost_breakdown", {}).get("high", 0) for ride in transport_rides)
    
    # Subtotal before contingency
    subtotal = (
        accommodation["total_cost"] +
        food["total_cost"] +
        activities["total_cost"] +
        transport_total
    )
    
    # Contingency buffer
    contingency = subtotal * CONTINGENCY_BUFFER
    
    # Grand total
    grand_total = subtotal + contingency
    
    # Per-person cost
    cost_per_person = grand_total / num_people
    
    return {
        "currency": currency,
        "origin_city": origin_city,
        "destination_city": destination_city,
        "num_days": num_days,
        "num_nights": num_nights,
        "num_people": num_people,
        "travel_style": travel_style,
        "breakdown": {
            "transport": {
                "low": round(transport_low, 2),
                "expected": round(transport_total, 2),
                "high": round(transport_high, 2),
                "currency": currency,
                "rides": transport_rides
            },
            "accommodation": accommodation,
            "food": food,
            "activities": activities,
            "contingency": {
                "amount": round(contingency, 2),
                "percentage": CONTINGENCY_BUFFER * 100,
                "description": "Buffer for unexpected expenses"
            }
        },
        "totals": {
            "subtotal": round(subtotal, 2),
            "contingency": round(contingency, 2),
            "grand_total": round(grand_total, 2),
            "cost_per_person": round(cost_per_person, 2)
        },
        "assumptions": {
            "fuel_rate_pkr_per_liter": FUEL_RATE_PKR_PER_LITER,
            "indrive_base_fare_pkr": INDRIVE_BASE_FARE,
            "indrive_per_km_pkr": INDRIVE_PER_KM,
            "people_per_room": 2,
            "activities_per_day": 2,
            "contingency_percentage": CONTINGENCY_BUFFER * 100
        }
    }


def generate_scenario_comparison(
    origin_city: str,
    destination_city: str,
    num_days: int,
    num_people: int,
    transport_rides: List[Dict[str, Any]],
    currency: str = "PKR",
    is_peak_season: bool = False
) -> Dict[str, Any]:
    """
    Generate budget-optimized vs comfort-optimized scenario comparison.
    """
    # Budget scenario
    budget_breakdown = generate_comprehensive_cost_breakdown(
        origin_city, destination_city, num_days, num_people,
        "budget", transport_rides, currency, is_peak_season
    )
    
    # Comfort scenario
    comfort_breakdown = generate_comprehensive_cost_breakdown(
        origin_city, destination_city, num_days, num_people,
        "mid_range", transport_rides, currency, is_peak_season
    )
    
    # Calculate deltas
    cost_delta = comfort_breakdown["totals"]["grand_total"] - budget_breakdown["totals"]["grand_total"]
    cost_delta_percent = (cost_delta / budget_breakdown["totals"]["grand_total"]) * 100 if budget_breakdown["totals"]["grand_total"] > 0 else 0
    
    return {
        "currency": currency,
        "scenarios": {
            "budget_optimized": budget_breakdown,
            "comfort_optimized": comfort_breakdown
        },
        "comparison": {
            "cost_delta": round(cost_delta, 2),
            "cost_delta_percent": round(cost_delta_percent, 2),
            "budget_total": round(budget_breakdown["totals"]["grand_total"], 2),
            "comfort_total": round(comfort_breakdown["totals"]["grand_total"], 2),
            "trade_offs": {
                "budget": "Lower cost, basic accommodation, street food, minimal activities",
                "comfort": "Higher cost, better accommodation, restaurant meals, more activities"
            }
        }
    }

