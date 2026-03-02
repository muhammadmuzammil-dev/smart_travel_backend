# backend/load_embeddings.py

import os
import json
from typing import Any, Dict, List

from vector_store import get_spots_collection, BASE_DIR

DATA_DIR = os.path.join(BASE_DIR, "data")

SPOTS_FILE = os.path.join(DATA_DIR, "spots_with_embeddings.json")
CITIES_FILE = os.path.join(DATA_DIR, "cities_with_embeddings.json")
HOTELS_FILE = os.path.join(DATA_DIR, "hotels_with_embeddings.json")

collection = get_spots_collection()


def load_json(path: str) -> List[Dict[str, Any]]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def to_metadata_value(v: Any) -> Any:
    """
    Chroma metadatas CANNOT contain None, and must be
    bool/int/float/str or simple types. We convert others to str.
    Special handling for lists (images, highlights) - convert to JSON string.
    """
    if v is None:
        return None
    if isinstance(v, (bool, int, float, str)):
        return v
    # lists, dicts, etc → JSON stringify for better storage
    if isinstance(v, (list, dict)):
        return json.dumps(v, ensure_ascii=False)
    return str(v)


def sanitize_metadata(rec: Dict[str, Any]) -> Dict[str, Any]:
    """
    Remove the 'embedding' field and drop any keys with None.
    Also ensure values are safe types.
    """
    meta: Dict[str, Any] = {}
    for k, v in rec.items():
        if k == "embedding":
            continue
        vv = to_metadata_value(v)
        if vv is not None:
            meta[k] = vv
    return meta


def insert_records(records: List[Dict[str, Any]], prefix: str):
    ids: List[str] = []
    docs: List[str] = []
    metas: List[Dict[str, Any]] = []
    embeds: List[List[float]] = []

    for i, rec in enumerate(records):
        emb = rec.get("embedding")
        if not emb:
            continue

        # Generate unique ID
        rec_id = rec.get("id")
        if not rec_id:
            # Create ID from name and location
            name = rec.get("name", "")
            city = rec.get("city", "")
            rec_id = f"{name}_{city}_{i}" if name and city else f"{prefix}_{i}"
        ids.append(f"{prefix}::{rec_id}")

        # Build comprehensive document text for better retrieval
        doc_parts = []
        if rec.get("name"):
            doc_parts.append(rec["name"])
        if rec.get("description"):
            doc_parts.append(rec["description"])
        if rec.get("category"):
            doc_parts.append(f"Category: {rec['category']}")
        if rec.get("best_time_to_visit"):
            doc_parts.append(f"Best time: {rec['best_time_to_visit']}")
        
        doc_text = ". ".join(doc_parts) if doc_parts else (
            rec.get("description")
            or rec.get("name")
            or rec.get("city")
            or rec.get("region")
            or prefix
        )
        docs.append(str(doc_text))

        embeds.append(emb)
        meta = sanitize_metadata(rec)
        meta["record_type"] = prefix
        metas.append(meta)

    if ids:
        collection.add(
            ids=ids,
            embeddings=embeds,
            metadatas=metas,
            documents=docs,
        )
        print(f"Inserted {len(ids)} records -> prefix = {prefix}")
    else:
        print(f"No records inserted for prefix = {prefix}")


def main():
    print("Loading JSON data...")
    
    # Load spots (required)
    if not os.path.exists(SPOTS_FILE):
        print(f"Error: {SPOTS_FILE} not found. Run generate_embeddings.py first.")
        return
    
    spots = load_json(SPOTS_FILE)
    print(f"Loaded {len(spots)} spots")

    print("Inserting spot embeddings...")
    insert_records(spots, "spot")

    # Load cities (optional)
    if os.path.exists(CITIES_FILE):
        cities = load_json(CITIES_FILE)
        print(f"Loaded {len(cities)} cities")
        print("Inserting city embeddings...")
        insert_records(cities, "city")
    else:
        print(f"Note: {CITIES_FILE} not found, skipping city embeddings")
    
    # Load hotels (optional)
    if os.path.exists(HOTELS_FILE):
        hotels = load_json(HOTELS_FILE)
        print(f"Loaded {len(hotels)} hotels")
        print("Inserting hotel embeddings...")
        insert_records(hotels, "hotel")
    else:
        print(f"Note: {HOTELS_FILE} not found, skipping hotel embeddings. Run hotel_processor.py first.")

    print("\n[SUCCESS] DONE - All embeddings stored in Chroma!")
    print(f"DB Path: {os.path.join(BASE_DIR, 'vector_db')}")


if __name__ == "__main__":
    main()
