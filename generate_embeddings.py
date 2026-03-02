"""
Generate embeddings for travel spots with enhanced data including images and best_time_to_visit.
This script processes structured_spots.json and creates embeddings with comprehensive text.
"""

import os
import json
from typing import List, Dict, Any
from sentence_transformers import SentenceTransformer

# Initialize the embedding model
MODEL_NAME = "all-MiniLM-L6-v2"
model = SentenceTransformer(MODEL_NAME)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
SPOTS_INPUT = os.path.join(DATA_DIR, "structured_spots.json")
SPOTS_OUTPUT = os.path.join(DATA_DIR, "spots_with_embeddings.json")


def build_embedding_text(spot: Dict[str, Any]) -> str:
    """
    Build comprehensive text for embedding that includes all relevant information:
    - Name, description, category
    - Highlights
    - Best time to visit
    - Location context (district, division, province)
    - Image context
    """
    parts = []
    
    # Name and category
    name = spot.get("name", "")
    category = spot.get("category", "")
    if name:
        parts.append(f"Destination: {name}")
    if category:
        parts.append(f"Category: {category}")
    
    # Description
    description = spot.get("description", "")
    if description:
        parts.append(f"Description: {description}")
    
    # Highlights
    highlights = spot.get("highlights", [])
    if highlights:
        if isinstance(highlights, list):
            highlights_text = ". ".join(str(h) for h in highlights if h)
        else:
            highlights_text = str(highlights)
        if highlights_text:
            parts.append(f"Highlights: {highlights_text}")
    
    # Best time to visit
    best_time = spot.get("best_time_to_visit", "")
    if best_time:
        parts.append(f"Best time to visit: {best_time}")
    
    # Location context
    district = spot.get("district", "")
    division = spot.get("division", "")
    province = spot.get("region", "") or spot.get("province", "")
    city = spot.get("city", "")
    
    location_parts = []
    if city:
        location_parts.append(city)
    if district and district != city:
        location_parts.append(f"district {district}")
    if division:
        location_parts.append(f"{division} division")
    if province:
        location_parts.append(province)
    
    if location_parts:
        parts.append(f"Location: {', '.join(location_parts)}")
    
    # Image context
    images = spot.get("images", [])
    if images:
        if isinstance(images, list):
            image_count = len([img for img in images if img])
            if image_count > 0:
                parts.append(f"Visual content: {image_count} image(s) available showing the destination")
    
    # Combine all parts
    embedding_text = ". ".join(parts)
    return embedding_text


def generate_embeddings_for_spots(spots: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Generate embeddings for all spots.
    Returns list of spots with added 'embedding' field.
    """
    print(f"Generating embeddings for {len(spots)} spots...")
    
    # Build embedding texts
    texts = []
    for spot in spots:
        text = build_embedding_text(spot)
        texts.append(text)
    
    # Generate embeddings in batches
    print("Computing embeddings...")
    embeddings = model.encode(texts, show_progress_bar=True, convert_to_numpy=True)
    
    # Add embeddings to spots
    spots_with_embeddings = []
    for i, spot in enumerate(spots):
        spot_copy = spot.copy()
        spot_copy["embedding"] = embeddings[i].tolist()
        spots_with_embeddings.append(spot_copy)
    
    print(f"[OK] Generated embeddings for {len(spots_with_embeddings)} spots")
    return spots_with_embeddings


def main():
    """Main function to generate embeddings."""
    # Load spots
    if not os.path.exists(SPOTS_INPUT):
        print(f"Error: {SPOTS_INPUT} not found. Run preprocessing first.")
        return
    
    print(f"Loading spots from {SPOTS_INPUT}...")
    with open(SPOTS_INPUT, "r", encoding="utf-8") as f:
        spots = json.load(f)
    
    print(f"Loaded {len(spots)} spots")
    
    # Generate embeddings
    spots_with_embeddings = generate_embeddings_for_spots(spots)
    
    # Save results
    print(f"Saving embeddings to {SPOTS_OUTPUT}...")
    with open(SPOTS_OUTPUT, "w", encoding="utf-8") as f:
        json.dump(spots_with_embeddings, f, indent=2, ensure_ascii=False)
    
    print(f"[OK] Saved {len(spots_with_embeddings)} spots with embeddings to {SPOTS_OUTPUT}")


if __name__ == "__main__":
    main()

