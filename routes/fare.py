"""
Ride fare calculator endpoint.
Calculates dynamic fares for Uber, Careem, InDrive, and Bykea
between any two Pakistani cities, with distance via Haversine and
optional peak-hour surge.
"""

import math
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from utils.transport_calculator import haversine_distance

router = APIRouter()

# ── City coordinates (lat, lon) for major Pakistani cities ───────────────────
CITY_COORDS: dict[str, tuple[float, float]] = {
    "Karachi":          (24.8607,  67.0011),
    "Lahore":           (31.5204,  74.3587),
    "Islamabad":        (33.6844,  73.0479),
    "Rawalpindi":       (33.5651,  73.0169),
    "Faisalabad":       (31.4504,  73.1350),
    "Multan":           (30.1798,  71.4214),
    "Peshawar":         (34.0151,  71.5249),
    "Quetta":           (30.1798,  66.9750),
    "Sialkot":          (32.4945,  74.5229),
    "Gujranwala":       (32.1877,  74.1945),
    "Hyderabad":        (25.3960,  68.3578),
    "Sargodha":         (32.0740,  72.6861),
    "Bahawalpur":       (29.3956,  71.6836),
    "Sukkur":           (27.7052,  68.8574),
    "Larkana":          (27.5570,  68.2137),
    "Sheikhupura":      (31.7167,  73.9850),
    "Rahim Yar Khan":   (28.4202,  70.2952),
    "Gujrat":           (32.5736,  74.0790),
    "Kasur":            (31.1200,  74.4500),
    "Mardan":           (34.2010,  72.0490),
    "Mingora":          (34.7717,  72.3600),
    "Nawabshah":        (26.2442,  68.4100),
    "Chiniot":          (31.7270,  72.9783),
    "Kotri":            (25.3657,  68.3110),
    "Khanpur":          (28.6455,  70.6567),
    "Hafizabad":        (32.0673,  73.6867),
    "Kohat":            (33.5869,  71.4430),
    "Jacobabad":        (28.2820,  68.4510),
    "Shikarpur":        (27.9555,  68.6378),
    "Muzaffargarh":     (30.0701,  71.1934),
    "Khanewal":         (30.3019,  71.9323),
    "Hasan Abdal":      (33.8190,  72.6930),
    "Kamoke":           (31.9759,  74.2229),
    "Umerkot":          (25.3619,  69.7360),
    "Ahmedpur East":    (29.1450,  71.2590),
    "Kot Addu":         (30.4704,  70.9644),
    "Wazirabad":        (32.4426,  74.1202),
    "Dera Ghazi Khan":  (30.0489,  70.6338),
    "Chakwal":          (32.9302,  72.8508),
    "Swat":             (34.7717,  72.3600),
    "Naran":            (34.9051,  73.6517),
    "Hunza":            (36.3167,  74.6500),
    "Skardu":           (35.2971,  75.6333),
    "Murree":           (33.9042,  73.3940),
    "Gilgit":           (35.9219,  74.3083),
    "Chitral":          (35.8510,  71.7889),
    "Abbottabad":       (34.1491,  73.2117),
    "Mansehra":         (34.3298,  73.1972),
    "Haripur":          (33.9944,  72.9355),
}

# Mountain cities — terrain surcharge applied
MOUNTAIN_CITIES = {
    "Naran", "Hunza", "Skardu", "Gilgit", "Chitral", "Murree",
    "Swat", "Mingora", "Mansehra", "Abbottabad", "Haripur", "Chakwal",
}

# ── Fare service definitions ─────────────────────────────────────────────────
#  base_fare  : flat starting amount (PKR)
#  per_km     : PKR per km after base
#  peak_mult  : multiplier applied to total fare during peak hours
#  max_dist   : maximum distance this service operates (km), None = unlimited
#  negotiate  : whether the fare is negotiable (InDrive)
SERVICES = [
    {
        "service":    "Uber",
        "category":  "UberGo",
        "base_fare":  150,
        "per_km":     32,
        "peak_mult":  1.5,
        "max_dist":   None,
        "negotiate":  False,
        "icon":       "🚗",
        "color":      "#000000",
    },
    {
        "service":    "Uber",
        "category":  "UberMini",
        "base_fare":  120,
        "per_km":     28,
        "peak_mult":  1.5,
        "max_dist":   None,
        "negotiate":  False,
        "icon":       "🚙",
        "color":      "#000000",
    },
    {
        "service":    "Uber",
        "category":  "Comfort",
        "base_fare":  250,
        "per_km":     45,
        "peak_mult":  1.3,
        "max_dist":   None,
        "negotiate":  False,
        "icon":       "🛻",
        "color":      "#000000",
    },
    {
        "service":    "Careem",
        "category":  "Go",
        "base_fare":  140,
        "per_km":     30,
        "peak_mult":  1.4,
        "max_dist":   None,
        "negotiate":  False,
        "icon":       "🟢",
        "color":      "#1D4ED8",
    },
    {
        "service":    "Careem",
        "category":  "Business",
        "base_fare":  220,
        "per_km":     42,
        "peak_mult":  1.3,
        "max_dist":   None,
        "negotiate":  False,
        "icon":       "💼",
        "color":      "#1D4ED8",
    },
    {
        "service":    "InDrive",
        "category":  "Standard",
        "base_fare":  100,
        "per_km":     25,
        "peak_mult":  1.0,   # InDrive has no surge — negotiated fares
        "max_dist":   None,
        "negotiate":  True,
        "icon":       "🤝",
        "color":      "#F59E0B",
    },
    {
        "service":    "Bykea",
        "category":  "Bike",
        "base_fare":  60,
        "per_km":     15,
        "peak_mult":  1.2,
        "max_dist":   80,    # Bikes not suitable for long-haul
        "negotiate":  False,
        "icon":       "🏍️",
        "color":      "#DC2626",
    },
    {
        "service":    "Bykea",
        "category":  "Delivery",
        "base_fare":  80,
        "per_km":     18,
        "peak_mult":  1.2,
        "max_dist":   80,
        "negotiate":  False,
        "icon":       "📦",
        "color":      "#DC2626",
    },
]

# ── Pydantic schemas ─────────────────────────────────────────────────────────

class FareRequest(BaseModel):
    origin_city:      str = Field(..., description="Departure city name")
    destination_city: str = Field(..., description="Destination city name")
    num_people:       int = Field(1, ge=1, le=6, description="Number of passengers (1-6)")
    is_peak:          bool = Field(False, description="Apply peak-hour surge pricing")


class ServiceFare(BaseModel):
    service:        str
    category:       str
    icon:           str
    color:          str
    base_fare:      float
    per_km_rate:    float
    fare_min:       float   # -10 % negotiation floor
    fare_expected:  float   # calculated fare (with surge if peak)
    fare_max:       float   # +20 % upper bound
    currency:       str
    is_available:   bool
    is_peak_active: bool
    note:           str


class FareResponse(BaseModel):
    origin_city:       str
    destination_city:  str
    distance_km:       float
    duration_minutes:  int
    origin_coords:     dict
    destination_coords: dict
    fares:             List[ServiceFare]
    cheapest_service:  str
    cheapest_fare:     float
    is_peak:           bool
    calculated_at:     str


# ── Helper functions ─────────────────────────────────────────────────────────

def _duration_minutes(distance_km: float, is_mountain: bool) -> int:
    """Estimate travel time. Mountain routes are slower."""
    if is_mountain:
        # Mountain roads: ~35 km/h average
        return max(10, int((distance_km / 35) * 60))
    if distance_km < 50:
        # City: ~30 km/h
        return max(5, int((distance_km / 30) * 60))
    # Highway: ~80 km/h
    return max(15, int((distance_km / 80) * 60))


def _num_rides_needed(num_people: int) -> int:
    """Standard rides seat 1-4 passengers."""
    return math.ceil(num_people / 4)


def _compute_fare(
    svc: dict,
    distance_km: float,
    num_people: int,
    is_peak: bool,
    terrain_mult: float,
) -> ServiceFare:
    is_available = svc["max_dist"] is None or distance_km <= svc["max_dist"]

    num_rides = _num_rides_needed(num_people) if svc["service"] != "Bykea" else num_people

    raw = (svc["base_fare"] + svc["per_km"] * distance_km) * num_rides
    raw *= terrain_mult

    is_peak_active = is_peak and svc["peak_mult"] > 1.0
    if is_peak_active:
        raw *= svc["peak_mult"]

    fare_expected = round(raw, 0)
    fare_min      = round(raw * 0.90, 0)
    fare_max      = round(raw * 1.20, 0)

    # Build note
    notes = []
    if svc["negotiate"]:
        notes.append("Negotiable fare")
    if is_peak_active:
        notes.append(f"Peak surge ×{svc['peak_mult']}")
    if terrain_mult > 1.0:
        notes.append("Mountain route surcharge")
    if not is_available:
        notes.append(f"Not available over {svc['max_dist']} km")
    note = " · ".join(notes) if notes else "Standard fare"

    return ServiceFare(
        service=svc["service"],
        category=svc["category"],
        icon=svc["icon"],
        color=svc["color"],
        base_fare=svc["base_fare"],
        per_km_rate=svc["per_km"],
        fare_min=fare_min if is_available else 0,
        fare_expected=fare_expected if is_available else 0,
        fare_max=fare_max if is_available else 0,
        currency="PKR",
        is_available=is_available,
        is_peak_active=is_peak_active,
        note=note,
    )


# ── Route ────────────────────────────────────────────────────────────────────

@router.post("/calculate", response_model=FareResponse, summary="Calculate ride fares between two cities")
async def calculate_fare(req: FareRequest):
    """
    Calculate ride fares for Uber, Careem, InDrive, and Bykea
    between two Pakistani cities.
    """
    # Normalise city names (title-case lookup)
    origin_key = None
    dest_key   = None
    for key in CITY_COORDS:
        if key.lower() == req.origin_city.strip().lower():
            origin_key = key
        if key.lower() == req.destination_city.strip().lower():
            dest_key = key

    if origin_key is None:
        available = ", ".join(sorted(CITY_COORDS.keys()))
        raise HTTPException(
            status_code=404,
            detail=f"City '{req.origin_city}' not found. Available cities: {available}",
        )
    if dest_key is None:
        available = ", ".join(sorted(CITY_COORDS.keys()))
        raise HTTPException(
            status_code=404,
            detail=f"City '{req.destination_city}' not found. Available cities: {available}",
        )
    if origin_key == dest_key:
        raise HTTPException(
            status_code=400,
            detail="Origin and destination cannot be the same city.",
        )

    o_lat, o_lon = CITY_COORDS[origin_key]
    d_lat, d_lon = CITY_COORDS[dest_key]

    distance_km = round(haversine_distance(o_lat, o_lon, d_lat, d_lon), 2)

    is_mountain = dest_key in MOUNTAIN_CITIES or origin_key in MOUNTAIN_CITIES
    terrain_mult = 1.3 if is_mountain else 1.0

    duration = _duration_minutes(distance_km, is_mountain)

    fares = [
        _compute_fare(svc, distance_km, req.num_people, req.is_peak, terrain_mult)
        for svc in SERVICES
    ]

    # Cheapest available fare
    available_fares = [f for f in fares if f.is_available]
    cheapest = min(available_fares, key=lambda f: f.fare_expected) if available_fares else fares[0]

    return FareResponse(
        origin_city=origin_key,
        destination_city=dest_key,
        distance_km=distance_km,
        duration_minutes=duration,
        origin_coords={"lat": o_lat, "lon": o_lon},
        destination_coords={"lat": d_lat, "lon": d_lon},
        fares=fares,
        cheapest_service=f"{cheapest.service} {cheapest.category}",
        cheapest_fare=cheapest.fare_expected,
        is_peak=req.is_peak,
        calculated_at=datetime.now(timezone.utc).isoformat(),
    )
