from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, field_validator, model_validator
from datetime import datetime


class ItineraryRequest(BaseModel):
    destination_city: str = Field(..., min_length=1, max_length=100, description="Destination city name")
    departure_city: Optional[str] = Field(None, max_length=100, description="Departure city name")
    region: Optional[str] = Field(None, max_length=100, description="Region or province")
    interests: Optional[List[str]] = Field(None, description="List of interests")
    budget_level: str = Field(..., description="Budget level: low, medium, or high")
    budget_amount: Optional[float] = Field(None, gt=0, le=10000000, description="Budget amount in PKR")
    num_days: int = Field(..., gt=0, le=30, description="Number of days for the trip")
    transport_mode: Optional[str] = Field(None, max_length=50, description="Transport mode")
    travel_date: Optional[str] = Field(None, max_length=50, description="Travel date or date range")
    num_of_people: Optional[int] = Field(1, gt=0, le=20, description="Number of travelers")
    language: Optional[str] = Field('en', description="Language preference: 'en' for English, 'ur' for Urdu")

    @field_validator('destination_city')
    @classmethod
    def validate_destination_city(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError('Destination city cannot be empty')
        return v.strip()

    @field_validator('budget_level')
    @classmethod
    def validate_budget_level(cls, v: str) -> str:
        allowed_levels = ['low', 'medium', 'high']
        v_lower = v.lower().strip()
        if v_lower not in allowed_levels:
            raise ValueError(f'Budget level must be one of: {", ".join(allowed_levels)}')
        return v_lower

    @field_validator('transport_mode')
    @classmethod
    def validate_transport_mode(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        allowed_modes = ['own_car', 'public_transport', 'ride_sharing', 'mixed']
        v_lower = v.lower().strip()
        # Check if it matches any allowed mode or contains keywords
        if any(mode in v_lower for mode in allowed_modes):
            return v_lower
        # If it's a valid keyword, map it
        if 'car' in v_lower or 'own' in v_lower:
            return 'own_car'
        elif 'public' in v_lower:
            return 'public_transport'
        elif 'ride' in v_lower or 'sharing' in v_lower:
            return 'ride_sharing'
        elif 'mixed' in v_lower:
            return 'mixed'
        return v_lower

    @field_validator('travel_date')
    @classmethod
    def validate_travel_date(cls, v: Optional[str]) -> Optional[str]:
        if v is None or not v.strip():
            return None
        v = v.strip()
        # Try to parse common date formats
        date_formats = [
            "%Y-%m-%d",
            "%d-%m-%Y",
            "%d/%m/%Y",
            "%B %d, %Y",
            "%b %d, %Y",
            "%Y-%m-%d %H:%M:%S",
        ]
        # If it's a date range or descriptive text, allow it
        if any(keyword in v.lower() for keyword in ['to', '-', 'and', 'through', 'until']):
            return v
        # Try to parse as ISO format
        try:
            datetime.fromisoformat(v)
            return v
        except ValueError:
            pass
        # Try other formats
        for fmt in date_formats:
            try:
                datetime.strptime(v, fmt)
                return v
            except ValueError:
                continue
        # If it's descriptive text like "June 15-20, 2025", allow it
        return v

    @field_validator('interests')
    @classmethod
    def validate_interests(cls, v: Optional[List[str]]) -> Optional[List[str]]:
        if v is None:
            return None
        # Filter out empty strings and limit length
        cleaned = [interest.strip() for interest in v if interest and interest.strip()]
        if len(cleaned) > 20:
            raise ValueError('Maximum 20 interests allowed')
        return cleaned[:20] if cleaned else None

    @field_validator('departure_city', 'region')
    @classmethod
    def validate_optional_strings(cls, v: Optional[str]) -> Optional[str]:
        if v is None or not v.strip():
            return None
        return v.strip()

    @model_validator(mode='after')
    def validate_budget_consistency(self):
        """Ensure budget_amount is provided if budget_level is specified"""
        if self.budget_amount is not None and self.budget_amount <= 0:
            raise ValueError('Budget amount must be positive')
        if self.budget_amount is not None and self.num_days and self.num_of_people:
            budget_per_person_per_day = self.budget_amount / (self.num_days * self.num_of_people)
            if budget_per_person_per_day < 500:
                raise ValueError('Budget too low: minimum 500 PKR per person per day required')
        return self


class SpotLocation(BaseModel):
    name: str
    latitude: float
    longitude: float
    city: Optional[str] = None


class DayPlan(BaseModel):
    day: int
    places: List[str]
    description: str
    date: Optional[str] = None
    images: Optional[List[str]] = None
    spot_locations: Optional[List[SpotLocation]] = None  # Coordinates for map display


class ItineraryResponse(BaseModel):
    query_used: str
    num_spots_considered: int
    days: List[DayPlan]
    total_estimated_cost: float
    currency: str = "PKR"
    # This is where the LLM-generated nice text will go:
    pretty_itinerary_text: Optional[str] = None
    budget_breakdown: Optional[Dict[str, float]] = None
    recommended_hotels: Optional[List[str]] = None
    weather_considerations: Optional[str] = None
    travel_window: Optional[str] = None
    transport_costs: Optional[Dict[str, Any]] = None  # Transport cost breakdown
    weather_data: Optional[Dict[str, Any]] = None  # Current weather and forecast
    all_images: Optional[List[str]] = None  # All images from all spots in the itinerary

