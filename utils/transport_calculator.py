"""
Transport cost calculator with distance and mode-based pricing.
Uses Haversine formula for distance calculation.
"""

import math
from typing import List, Dict, Any, Optional, Tuple


def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calculate the great circle distance between two points on Earth
    using the Haversine formula.
    
    Returns distance in kilometers.
    """
    if None in (lat1, lon1, lat2, lon2):
        return 0.0
    
    # Radius of Earth in kilometers
    R = 6371.0
    
    # Convert latitude and longitude from degrees to radians
    lat1_rad = math.radians(lat1)
    lon1_rad = math.radians(lon1)
    lat2_rad = math.radians(lat2)
    lon2_rad = math.radians(lon2)
    
    # Haversine formula
    dlat = lat2_rad - lat1_rad
    dlon = lon2_rad - lon1_rad
    
    a = math.sin(dlat / 2)**2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    
    distance = R * c
    return distance


def calculate_distance_matrix(spots: List[Dict[str, Any]]) -> List[List[float]]:
    """
    Calculate distance matrix between all spots.
    Returns a 2D list where matrix[i][j] is the distance from spot i to spot j.
    """
    n = len(spots)
    matrix = [[0.0] * n for _ in range(n)]
    
    for i in range(n):
        for j in range(n):
            if i == j:
                matrix[i][j] = 0.0
            else:
                spot1 = spots[i]
                spot2 = spots[j]
                lat1 = spot1.get("latitude")
                lon1 = spot1.get("longitude")
                lat2 = spot2.get("latitude")
                lon2 = spot2.get("longitude")
                
                distance = haversine_distance(lat1, lon1, lat2, lon2)
                matrix[i][j] = distance
    
    return matrix


# Transport mode pricing (PKR per kilometer)
TRANSPORT_RATES = {
    "own_car": {
        "fuel_cost_per_km": 15.0,  # Average fuel cost in PKR per km
        "description": "Private car fuel cost"
    },
    "public_transport": {
        "bus_per_km": 2.5,  # Bus fare per km
        "train_per_km": 1.5,  # Train fare per km (if available)
        "description": "Public transport (bus/train)"
    },
    "ride_sharing": {
        "per_km": 25.0,  # Ride-sharing cost per km (higher than public transport)
        "base_fare": 100.0,  # Base fare
        "description": "Ride-sharing service"
    },
    "mixed": {
        "description": "Mixed transport modes"
    }
}


def calculate_transport_cost(
    distance_km: float,
    mode: str,
    num_people: int = 1
) -> float:
    """
    Calculate transport cost for a given distance and mode.
    
    Args:
        distance_km: Distance in kilometers
        mode: Transport mode (own_car, public_transport, ride_sharing, mixed)
        num_people: Number of people traveling
    
    Returns:
        Total cost in PKR
    """
    if distance_km <= 0:
        return 0.0
    
    mode = mode.lower() if mode else "public_transport"
    
    if mode == "own_car":
        # Fuel cost is per vehicle, not per person
        cost = distance_km * TRANSPORT_RATES["own_car"]["fuel_cost_per_km"]
        return cost
    
    elif mode == "public_transport":
        # Public transport is per person
        cost_per_person = distance_km * TRANSPORT_RATES["public_transport"]["bus_per_km"]
        # Minimum fare
        if cost_per_person < 50:
            cost_per_person = 50
        return cost_per_person * num_people
    
    elif mode == "ride_sharing":
        # Ride-sharing has base fare + per km cost
        base_fare = TRANSPORT_RATES["ride_sharing"]["base_fare"]
        per_km_cost = distance_km * TRANSPORT_RATES["ride_sharing"]["per_km"]
        # Can be shared among people (divide by 2-4 people typically)
        if num_people <= 1:
            return base_fare + per_km_cost
        elif num_people <= 4:
            # Shared ride, split base fare
            return (base_fare / num_people) + (per_km_cost / num_people)
        else:
            # Large group, might need multiple rides
            num_rides = math.ceil(num_people / 4)
            return num_rides * (base_fare + per_km_cost)
    
    elif mode == "mixed":
        # Weighted average: 40% own_car, 60% public_transport
        car_cost = calculate_transport_cost(distance_km, "own_car", num_people)
        public_cost = calculate_transport_cost(distance_km, "public_transport", num_people)
        return 0.4 * car_cost + 0.6 * public_cost
    
    else:
        # Default to public transport
        return calculate_transport_cost(distance_km, "public_transport", num_people)


def calculate_itinerary_transport_costs(
    spots: List[Dict[str, Any]],
    mode: str,
    num_people: int = 1,
    departure_city: Optional[Dict[str, Any]] = None,
    include_detailed_rides: bool = True
) -> Dict[str, Any]:
    """
    Calculate total transport costs for an itinerary with detailed ride information.
    
    Args:
        spots: List of destination spots with coordinates
        mode: Transport mode
        num_people: Number of people
        departure_city: Optional departure location with coordinates
        include_detailed_rides: Whether to include detailed ride info with links
    
    Returns:
        Dictionary with total cost, breakdown, detailed rides, and distance matrix
    """
    if not spots:
        return {
            "total_cost": 0.0,
            "cost_breakdown": [],
            "detailed_rides": [],
            "total_distance": 0.0,
            "distance_matrix": [],
            "mode": mode,
            "num_people": num_people
        }
    
    # Import cost optimizer for detailed ride info
    if include_detailed_rides:
        try:
            from .cost_optimizer import generate_ride_details
        except ImportError:
            include_detailed_rides = False
    
    # Calculate distance matrix
    all_locations = []
    if departure_city:
        all_locations.append(departure_city)
    all_locations.extend(spots)
    
    distance_matrix = calculate_distance_matrix(all_locations)
    
    # Calculate costs for each leg
    cost_breakdown = []
    detailed_rides = []
    total_cost = 0.0
    total_distance = 0.0
    
    # Cost from departure to first destination
    if departure_city and spots:
        dist = distance_matrix[0][1] if len(all_locations) > 1 else 0
        if dist > 0:
            cost = calculate_transport_cost(dist, mode, num_people)
            from_name = departure_city.get("name", "Departure")
            to_name = spots[0].get("name", "Destination 1")
            
            cost_breakdown.append({
                "from": from_name,
                "to": to_name,
                "distance_km": round(dist, 2),
                "cost_pkr": round(cost, 2),
                "mode": mode
            })
            
            # Generate detailed ride info if requested
            if include_detailed_rides:
                origin_coords = (departure_city.get("latitude"), departure_city.get("longitude"))
                dest_coords = (spots[0].get("latitude"), spots[0].get("longitude"))
                ride_detail = generate_ride_details(
                    origin=from_name,
                    destination=to_name,
                    origin_coords=origin_coords if all(c is not None for c in origin_coords) else None,
                    dest_coords=dest_coords if all(c is not None for c in dest_coords) else None,
                    distance_km=dist,
                    mode=mode,
                    num_people=num_people,
                    is_peak=False  # Could be determined based on time
                )
                detailed_rides.append(ride_detail)
            
            total_cost += cost
            total_distance += dist
    
    # Costs between destinations
    start_idx = 1 if departure_city else 0
    for i in range(len(spots) - 1):
        spot1_idx = start_idx + i
        spot2_idx = start_idx + i + 1
        
        if spot2_idx < len(all_locations):
            dist = distance_matrix[spot1_idx][spot2_idx]
            if dist > 0:
                cost = calculate_transport_cost(dist, mode, num_people)
                from_name = spots[i].get("name", f"Destination {i+1}")
                to_name = spots[i+1].get("name", f"Destination {i+2}")
                
                cost_breakdown.append({
                    "from": from_name,
                    "to": to_name,
                    "distance_km": round(dist, 2),
                    "cost_pkr": round(cost, 2),
                    "mode": mode
                })
                
                # Generate detailed ride info if requested
                if include_detailed_rides:
                    origin_coords = (spots[i].get("latitude"), spots[i].get("longitude"))
                    dest_coords = (spots[i+1].get("latitude"), spots[i+1].get("longitude"))
                    ride_detail = generate_ride_details(
                        origin=from_name,
                        destination=to_name,
                        origin_coords=origin_coords if all(c is not None for c in origin_coords) else None,
                        dest_coords=dest_coords if all(c is not None for c in dest_coords) else None,
                        distance_km=dist,
                        mode=mode,
                        num_people=num_people,
                        is_peak=False
                    )
                    detailed_rides.append(ride_detail)
                
                total_cost += cost
                total_distance += dist
    
    # Cost from last destination back to departure (if provided)
    if departure_city and spots:
        last_spot_idx = len(all_locations) - 1
        dist = distance_matrix[last_spot_idx][0]
        if dist > 0:
            cost = calculate_transport_cost(dist, mode, num_people)
            from_name = spots[-1].get("name", "Last Destination")
            to_name = departure_city.get("name", "Return")
            
            cost_breakdown.append({
                "from": from_name,
                "to": to_name,
                "distance_km": round(dist, 2),
                "cost_pkr": round(cost, 2),
                "mode": mode
            })
            
            # Generate detailed ride info if requested
            if include_detailed_rides:
                origin_coords = (spots[-1].get("latitude"), spots[-1].get("longitude"))
                dest_coords = (departure_city.get("latitude"), departure_city.get("longitude"))
                ride_detail = generate_ride_details(
                    origin=from_name,
                    destination=to_name,
                    origin_coords=origin_coords if all(c is not None for c in origin_coords) else None,
                    dest_coords=dest_coords if all(c is not None for c in dest_coords) else None,
                    distance_km=dist,
                    mode=mode,
                    num_people=num_people,
                    is_peak=False
                )
                detailed_rides.append(ride_detail)
            
            total_cost += cost
            total_distance += dist
    
    result = {
        "total_cost": round(total_cost, 2),
        "cost_breakdown": cost_breakdown,
        "total_distance": round(total_distance, 2),
        "distance_matrix": distance_matrix,
        "mode": mode,
        "num_people": num_people
    }
    
    if include_detailed_rides:
        result["detailed_rides"] = detailed_rides
    
    return result

