"""
Process hotel CSV files and create embeddings for hotel data.
"""

import os
import csv
import json
import re
from typing import List, Dict, Any, Optional
from pathlib import Path
from sentence_transformers import SentenceTransformer

# Initialize the embedding model
MODEL_NAME = "all-MiniLM-L6-v2"
model = SentenceTransformer(MODEL_NAME)

BASE_DIR = Path(__file__).resolve().parents[1]  # backend/utils -> backend
DATA_DIR = BASE_DIR / "data"
HOTELS_DIR = DATA_DIR / "hotels"
HOTELS_OUTPUT = DATA_DIR / "hotels_with_embeddings.json"


def extract_price_from_string(price_str: str) -> Optional[float]:
    """Extract numeric price from string like 'PKR 10,800'."""
    if not price_str:
        return None
    
    # Remove currency symbols and extract numbers
    digits = re.findall(r'\d+', price_str.replace(',', ''))
    if digits:
        return float(digits[0])
    return None


def normalize_city_name(filename: str) -> str:
    """Normalize city name from CSV filename."""
    # Remove .csv extension and normalize
    city = filename.replace('.csv', '').replace('_', ' ').title()
    return city


def build_hotel_embedding_text(hotel: Dict[str, Any]) -> str:
    """
    Build comprehensive text for hotel embedding.
    """
    parts = []
    
    # Name
    name = hotel.get("name", "")
    if name:
        parts.append(f"Hotel: {name}")
    
    # Description
    description = hotel.get("description", "")
    if description:
        parts.append(f"Description: {description}")
    
    # Address and location
    address = hotel.get("address", "")
    city = hotel.get("city", "")
    if address:
        parts.append(f"Location: {address}")
    elif city:
        parts.append(f"Location: {city}")
    
    # Price and rating
    price = hotel.get("price")
    if price:
        parts.append(f"Price: PKR {price} per night")
    
    rating = hotel.get("rating")
    if rating:
        parts.append(f"Rating: {rating}/10")
    
    # Distance
    distance = hotel.get("distance", "")
    if distance:
        parts.append(f"Distance: {distance}")
    
    # City context
    if city:
        parts.append(f"City: {city}")
    
    return ". ".join(parts)


def process_hotel_csvs() -> List[Dict[str, Any]]:
    """
    Process all hotel CSV files and return list of hotel records.
    """
    hotels = []
    
    if not HOTELS_DIR.exists():
        print(f"Hotels directory not found: {HOTELS_DIR}")
        return hotels
    
    csv_files = list(HOTELS_DIR.glob("*.csv"))
    if not csv_files:
        print(f"No CSV files found in {HOTELS_DIR}")
        return hotels
    
    print(f"Processing {len(csv_files)} hotel CSV files...")
    
    for csv_file in csv_files:
        city_name = normalize_city_name(csv_file.stem)
        
        try:
            with open(csv_file, "r", encoding="utf-8", newline="") as f:
                reader = csv.DictReader(f)
                
                for row in reader:
                    # Extract hotel data
                    name = row.get("Name") or row.get("name", "").strip()
                    if not name:
                        continue
                    
                    address = row.get("Address") or row.get("address", "").strip()
                    distance = row.get("Distance") or row.get("distance", "").strip()
                    description = row.get("Description") or row.get("description", "").strip()
                    rating_str = row.get("Rating") or row.get("rating", "").strip()
                    price_str = row.get("Price") or row.get("price", "").strip()
                    image_url = row.get("Image") or row.get("image", "").strip()
                    hotel_url = row.get("Hotel_URL") or row.get("hotel_url", "").strip()
                    
                    # Parse rating
                    rating = None
                    if rating_str and rating_str.lower() != "n/a":
                        try:
                            rating = float(rating_str)
                        except ValueError:
                            pass
                    
                    # Parse price
                    price = extract_price_from_string(price_str)
                    
                    hotel = {
                        "name": name,
                        "address": address,
                        "city": city_name,
                        "distance": distance,
                        "description": description,
                        "rating": rating,
                        "price": price,
                        "image_url": image_url if image_url else None,
                        "hotel_url": hotel_url if hotel_url else None
                    }
                    
                    hotels.append(hotel)
        
        except Exception as e:
            print(f"Error processing {csv_file}: {e}")
            continue
    
    print(f"Processed {len(hotels)} hotels")
    return hotels


def generate_hotel_embeddings(hotels: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Generate embeddings for all hotels.
    """
    if not hotels:
        return []
    
    print(f"Generating embeddings for {len(hotels)} hotels...")
    
    # Build embedding texts
    texts = []
    for hotel in hotels:
        text = build_hotel_embedding_text(hotel)
        texts.append(text)
    
    # Generate embeddings
    print("Computing embeddings...")
    embeddings = model.encode(texts, show_progress_bar=True, convert_to_numpy=True)
    
    # Add embeddings to hotels
    hotels_with_embeddings = []
    for i, hotel in enumerate(hotels):
        hotel_copy = hotel.copy()
        hotel_copy["embedding"] = embeddings[i].tolist()
        hotels_with_embeddings.append(hotel_copy)
    
    print(f"✅ Generated embeddings for {len(hotels_with_embeddings)} hotels")
    return hotels_with_embeddings


def main():
    """Main function to process hotels and generate embeddings."""
    # Process CSV files
    hotels = process_hotel_csvs()
    
    if not hotels:
        print("No hotels found to process")
        return
    
    # Generate embeddings
    hotels_with_embeddings = generate_hotel_embeddings(hotels)
    
    # Save results
    print(f"Saving hotels to {HOTELS_OUTPUT}...")
    with open(HOTELS_OUTPUT, "w", encoding="utf-8") as f:
        json.dump(hotels_with_embeddings, f, indent=2, ensure_ascii=False)
    
    print(f"✅ Saved {len(hotels_with_embeddings)} hotels with embeddings to {HOTELS_OUTPUT}")


if __name__ == "__main__":
    main()

