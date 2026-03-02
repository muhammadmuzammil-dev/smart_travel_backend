from typing import List, Dict, Any, Optional
import json

from sentence_transformers import SentenceTransformer
from vector_store import get_spots_collection

# ---------- Embedding model ----------
MODEL_NAME = "all-MiniLM-L6-v2"
_model = SentenceTransformer(MODEL_NAME)


def _embed_query(text: str) -> List[float]:
    """Embed a query string into a vector using the same model as embed_data.py."""
    if not text:
        text = "tourist attractions Pakistan"
    return _model.encode(text, convert_to_numpy=True).tolist()


 


def search_spots_for_preferences(
    preferences: Dict[str, Any],
    top_k: int = 50,  # Increased to get more results
) -> List[Dict[str, Any]]:
    """
    Simple, *forgiving* retrieval:
    - Build one text query from city + region + interests
    - Ask Chroma for top_k results
    - Return a list of spot dicts with name, city, region, desc, distance
    """

    collection = get_spots_collection()

    city = (preferences.get("destination_city") or "").strip()
    region = (preferences.get("region") or "").strip()
    interests = preferences.get("interests") or []

    if isinstance(interests, list):
        interests_str = ", ".join(interests)
    else:
        interests_str = str(interests)

    # Build a more specific query string prioritizing the destination city
    query_parts = []
    if city:
        # Emphasize the city name multiple times for better matching
        query_parts.append(f"{city} tourist attractions")
        query_parts.append(f"{city} places to visit")
        query_parts.append(f"destinations in {city}")
        query_parts.append(f"things to do in {city}")
    if region:
        query_parts.append(f"{region} tourism destinations")
    if interests_str:
        query_parts.append(f"{interests_str} in {city}" if city else interests_str)
    
    # Combine with emphasis on city - repeat city name for better vector matching
    if query_parts:
        query_text = ". ".join(query_parts)
        # Add city name at the end again for extra emphasis
        if city:
            query_text += f" {city}"
    else:
        query_text = "beautiful tourist places in Pakistan"

    result = collection.query(
        query_texts=[query_text],
        n_results=top_k,
        include=["metadatas", "distances"],
    )

    metadatas_list = result.get("metadatas", [[]])[0]
    distances_list = result.get("distances", [[]])[0]

    spots: List[Dict[str, Any]] = []
    for meta, dist in zip(metadatas_list, distances_list):
        if not meta:
            continue
        record_type = meta.get("record_type")
        if record_type and record_type != "spot":
            continue

        # Validate that we have a proper name field
        name = meta.get("name") or meta.get("spot_name") or ""
        if not name or not name.strip():
            continue
        
        # Filter out invalid names (metadata fields)
        name_lower = name.strip().lower()
        invalid_names = {"province", "division", "divisions", "district", "districts", "city", "region"}
        if name_lower in invalid_names:
            continue

        # make sure it's a normal dict and attach distance
        spot = dict(meta)
        spot["distance"] = float(dist)
        spots.append(spot)

    # If we have a specific city, prioritize metadata filtering to get ONLY that city's spots
    if city:
        try:
            normalized_city = city.strip()
            
            # First, try to get spots by exact city match using metadata filter
            # This ensures we get spots ONLY from the specified city
            filtered_result = collection.get(
                where={"city": normalized_city, "record_type": "spot"},
                limit=top_k * 2,  # Get more to ensure we have enough
            )
            
            # Also try district match
            filtered_result2 = collection.get(
                where={"district": normalized_city, "record_type": "spot"},
                limit=top_k * 2,
            )
            
            # Combine results from both queries
            city_spots = []
            existing_names = set()
            
            for meta in filtered_result.get("metadatas", []) + filtered_result2.get("metadatas", []):
                if not meta:
                    continue
                
                name = meta.get("name") or meta.get("spot_name") or ""
                name_clean = str(name).strip().lower()
                if not name_clean:
                    continue
                
                # Skip invalid names
                invalid_names = {"province", "division", "divisions", "district", "districts", "city", "region"}
                if name_clean in invalid_names:
                    continue
                
                # Avoid duplicates
                if name_clean not in existing_names:
                    spot = dict(meta)
                    spot["distance"] = 0.0  # No distance for metadata filter
                    city_spots.append(spot)
                    existing_names.add(name_clean)
            
            # If we found city-specific spots, use those instead of vector search results
            # This ensures we ONLY get spots from the specified city
            if city_spots:
                print(f"[Retrieval] Found {len(city_spots)} spots for {city} via metadata filter")
                # Sort by name for consistency
                city_spots.sort(key=lambda x: str(x.get("name", "")).lower())
                return city_spots[:top_k]
            else:
                print(f"[Retrieval] No spots found for {city} via metadata filter, using vector search results")
        except Exception as e:
            # Metadata filtering failed, continue with vector search results
            print(f"[Retrieval] Metadata filter failed: {e}, using vector search results")
    
    return spots


def search_hotels_for_city(
    city: str,
    budget_level: Optional[str] = None,
    top_k: int = 10,
) -> List[Dict[str, Any]]:
    """
    Search for hotels in a specific city using vector search.
    
    Args:
        city: City name to search hotels for
        budget_level: Optional budget level (low, medium, high) to filter
        top_k: Number of results to return
    
    Returns:
        List of hotel dictionaries with metadata
    """
    collection = get_spots_collection()
    
    # Build query text
    query_text = f"hotels in {city}"
    if budget_level:
        query_text += f" {budget_level} budget"
    
    result = collection.query(
        query_texts=[query_text],
        n_results=top_k,
        include=["metadatas", "distances"],
    )
    
    metadatas_list = result.get("metadatas", [[]])[0]
    distances_list = result.get("distances", [[]])[0]
    
    hotels: List[Dict[str, Any]] = []
    for meta, dist in zip(metadatas_list, distances_list):
        if not meta:
            continue
        record_type = meta.get("record_type")
        if record_type and record_type != "hotel":
            continue
        
        # Parse JSON strings back to lists/dicts if needed
        hotel = {}
        for k, v in meta.items():
            if k == "record_type":
                continue
            # Try to parse JSON strings
            if isinstance(v, str) and (v.startswith("[") or v.startswith("{")):
                try:
                    hotel[k] = json.loads(v)
                except:
                    hotel[k] = v
            else:
                hotel[k] = v
        
        hotel["distance"] = float(dist)
        hotels.append(hotel)
    
    # Filter by budget if specified
    if budget_level and hotels:
        budget_ranges = {
            "low": (0, 5000),
            "medium": (5000, 15000),
            "high": (15000, float('inf'))
        }
        
        if budget_level in budget_ranges:
            min_price, max_price = budget_ranges[budget_level]
            filtered_hotels = []
            for hotel in hotels:
                price = hotel.get("price")
                if price is None:
                    # Include hotels without price if no other filter
                    filtered_hotels.append(hotel)
                elif min_price <= price <= max_price:
                    filtered_hotels.append(hotel)
            hotels = filtered_hotels
    
    # Sort by distance (lower is better)
    hotels.sort(key=lambda x: x.get("distance", float('inf')))
    
    return hotels