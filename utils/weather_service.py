"""
Weather service using Open-Meteo API (free, no API key required).
Provides current weather and forecasts with warnings.
"""

import requests
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
from functools import lru_cache
import time

# Cache for weather data (5 minutes)
_weather_cache: Dict[str, tuple] = {}
CACHE_DURATION = 300  # 5 minutes in seconds

# Open-Meteo API base URL
OPEN_METEO_BASE_URL = "https://api.open-meteo.com/v1/forecast"


def _get_cached_weather(cache_key: str) -> Optional[Dict[str, Any]]:
    """Get cached weather data if still valid."""
    if cache_key in _weather_cache:
        data, timestamp = _weather_cache[cache_key]
        if time.time() - timestamp < CACHE_DURATION:
            return data
    return None


def _set_cached_weather(cache_key: str, data: Dict[str, Any]):
    """Cache weather data with timestamp."""
    _weather_cache[cache_key] = (data, time.time())


def get_weather_data(latitude: float, longitude: float) -> Optional[Dict[str, Any]]:
    """
    Get current weather data for given coordinates using Open-Meteo.
    
    Args:
        latitude: Latitude coordinate
        longitude: Longitude coordinate
    
    Returns:
        Dictionary with weather data or None if API call fails
    """
    if latitude is None or longitude is None:
        return None
    
    cache_key = f"weather_{latitude}_{longitude}"
    cached = _get_cached_weather(cache_key)
    if cached:
        return cached
    
    try:
        params = {
            "latitude": latitude,
            "longitude": longitude,
            "current": "temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m,wind_direction_10m,precipitation,cloud_cover",
            "timezone": "auto"
        }
        
        response = requests.get(OPEN_METEO_BASE_URL, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        current = data.get("current", {})
        
        # Map weather codes to descriptions
        weather_code = current.get("weather_code", 0)
        weather_description = _get_weather_description(weather_code)
        
        # Format the response
        weather_data = {
            "temperature": current.get("temperature_2m"),
            "humidity": current.get("relative_humidity_2m"),
            "description": weather_description,
            "weather_code": weather_code,
            "wind_speed": current.get("wind_speed_10m"),  # km/h
            "wind_direction": current.get("wind_direction_10m"),
            "precipitation": current.get("precipitation", 0),  # mm
            "cloud_cover": current.get("cloud_cover"),
            "timestamp": datetime.utcnow().isoformat()
        }
        
        _set_cached_weather(cache_key, weather_data)
        return weather_data
    
    except requests.exceptions.RequestException as e:
        print(f"[Weather] API request failed: {e}")
        return None
    except Exception as e:
        print(f"[Weather] Error processing weather data: {e}")
        return None


def _get_weather_description(code: int) -> str:
    """Convert WMO weather code to description."""
    # WMO Weather interpretation codes (WW)
    weather_codes = {
        0: "Clear sky",
        1: "Mainly clear",
        2: "Partly cloudy",
        3: "Overcast",
        45: "Foggy",
        48: "Depositing rime fog",
        51: "Light drizzle",
        53: "Moderate drizzle",
        55: "Dense drizzle",
        56: "Light freezing drizzle",
        57: "Dense freezing drizzle",
        61: "Slight rain",
        63: "Moderate rain",
        65: "Heavy rain",
        66: "Light freezing rain",
        67: "Heavy freezing rain",
        71: "Slight snow fall",
        73: "Moderate snow fall",
        75: "Heavy snow fall",
        77: "Snow grains",
        80: "Slight rain showers",
        81: "Moderate rain showers",
        82: "Violent rain showers",
        85: "Slight snow showers",
        86: "Heavy snow showers",
        95: "Thunderstorm",
        96: "Thunderstorm with slight hail",
        99: "Thunderstorm with heavy hail"
    }
    return weather_codes.get(code, "Unknown")


def get_weather_forecast(latitude: float, longitude: float, days: int = 5) -> Optional[List[Dict[str, Any]]]:
    """
    Get weather forecast for given coordinates using Open-Meteo.
    
    Args:
        latitude: Latitude coordinate
        longitude: Longitude coordinate
        days: Number of days to forecast (max 16 for free tier)
    
    Returns:
        List of forecast data dictionaries or None if API call fails
    """
    if latitude is None or longitude is None:
        return None
    
    # Limit to 16 days for free tier
    days = min(days, 16)
    
    cache_key = f"forecast_{latitude}_{longitude}_{days}"
    cached = _get_cached_weather(cache_key)
    if cached:
        return cached
    
    try:
        params = {
            "latitude": latitude,
            "longitude": longitude,
            "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_sum,wind_speed_10m_max",
            "timezone": "auto",
            "forecast_days": days
        }
        
        response = requests.get(OPEN_METEO_BASE_URL, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        daily = data.get("daily", {})
        time_list = daily.get("time", [])
        weather_codes = daily.get("weather_code", [])
        temp_max = daily.get("temperature_2m_max", [])
        temp_min = daily.get("temperature_2m_min", [])
        precipitation = daily.get("precipitation_sum", [])
        wind_speed = daily.get("wind_speed_10m_max", [])
        
        forecasts = []
        for i in range(min(len(time_list), days)):
            code = weather_codes[i] if i < len(weather_codes) else 0
            forecast = {
                "date": time_list[i] if i < len(time_list) else "",
                "temperature_max": temp_max[i] if i < len(temp_max) else None,
                "temperature_min": temp_min[i] if i < len(temp_min) else None,
                "description": _get_weather_description(code),
                "weather_code": code,
                "precipitation": precipitation[i] if i < len(precipitation) else 0,
                "wind_speed": wind_speed[i] if i < len(wind_speed) else None
            }
            forecasts.append(forecast)
        
        _set_cached_weather(cache_key, forecasts)
        return forecasts
    
    except requests.exceptions.RequestException as e:
        print(f"[Weather] Forecast API request failed: {e}")
        return None
    except Exception as e:
        print(f"[Weather] Error processing forecast data: {e}")
        return None


def generate_weather_warnings(weather_data: Optional[Dict[str, Any]], forecasts: Optional[List[Dict[str, Any]]] = None) -> List[str]:
    """
    Generate weather warnings based on current conditions and forecast.
    
    Args:
        weather_data: Current weather data
        forecasts: Optional forecast data
    
    Returns:
        List of warning messages
    """
    warnings = []
    
    if not weather_data:
        return warnings
    
    # Extreme temperature warnings
    temp = weather_data.get("temperature")
    if temp is not None:
        if temp > 40:
            warnings.append("⚠️ Extreme heat warning: Temperature exceeds 40°C. Stay hydrated and avoid outdoor activities during peak hours.")
        elif temp < 0:
            warnings.append("⚠️ Freezing temperatures: Dress warmly and be cautious of icy conditions.")
        elif temp > 35:
            warnings.append("🌡️ High temperature: Stay hydrated and seek shade during peak hours.")
    
    # Wind warnings
    wind_speed = weather_data.get("wind_speed")
    if wind_speed is not None:
        if wind_speed > 60:
            warnings.append("⚠️ Strong wind warning: Wind speeds exceed 60 km/h. Be cautious when traveling.")
        elif wind_speed > 40:
            warnings.append("🌬️ Moderate winds expected. Secure loose items and drive carefully.")
    
    # Precipitation warnings
    precipitation = weather_data.get("precipitation", 0)
    description = weather_data.get("description", "").lower()
    weather_code = weather_data.get("weather_code", 0)
    
    if "rain" in description or weather_code in [61, 63, 65, 80, 81, 82]:
        if precipitation > 10:
            warnings.append("🌧️ Heavy rain expected. Pack rain gear and waterproof clothing.")
        else:
            warnings.append("🌧️ Rain expected. Pack rain gear and waterproof clothing.")
    elif "snow" in description or weather_code in [71, 73, 75, 77, 85, 86]:
        warnings.append("❄️ Snow expected. Dress in layers, wear warm boots, and drive carefully.")
    elif "thunderstorm" in description or weather_code in [95, 96, 99]:
        warnings.append("⛈️ Thunderstorm warning: Seek shelter and avoid outdoor activities.")
    elif "fog" in description or weather_code in [45, 48]:
        warnings.append("🌫️ Foggy conditions: Drive with extra caution and use low-beam headlights.")
    
    # Check forecast for upcoming severe weather
    if forecasts:
        for forecast in forecasts[:3]:  # Check next 3 days
            forecast_code = forecast.get("weather_code", 0)
            forecast_precip = forecast.get("precipitation", 0)
            
            if forecast_code in [95, 96, 99]:
                warnings.append("⛈️ Thunderstorms forecasted in coming days. Plan indoor activities as backup.")
                break
            elif forecast_precip > 20:  # More than 20mm
                warnings.append("🌧️ Heavy precipitation expected in forecast. Pack appropriate rain gear.")
                break
            
            temp_max = forecast.get("temperature_max")
            if temp_max and temp_max > 40:
                warnings.append("🌡️ Extreme heat forecasted. Plan activities for early morning or evening.")
                break
    
    # Cloud cover warnings
    cloud_cover = weather_data.get("cloud_cover")
    if cloud_cover is not None and cloud_cover > 80:
        warnings.append("☁️ Overcast conditions: May affect visibility and outdoor photography.")
    
    return warnings


def get_weather_for_destination(
    latitude: float,
    longitude: float,
    travel_dates: Optional[str] = None,
    num_days: int = 1
) -> Dict[str, Any]:
    """
    Get comprehensive weather information for a destination.
    
    Args:
        latitude: Destination latitude
        longitude: Destination longitude
        travel_dates: Optional travel date range
        num_days: Number of days for forecast
    
    Returns:
        Dictionary with current weather, forecast, and warnings
    """
    current_weather = get_weather_data(latitude, longitude)
    forecast = get_weather_forecast(latitude, longitude, num_days) if num_days > 0 else None
    warnings = generate_weather_warnings(current_weather, forecast)
    
    return {
        "current_weather": current_weather,
        "forecast": forecast,
        "warnings": warnings,
        "location": {
            "latitude": latitude,
            "longitude": longitude
        }
    }
