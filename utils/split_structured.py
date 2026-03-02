import json
import os
from typing import List, Dict, Any

HERE = os.path.dirname(os.path.dirname(__file__))  # backend/utils -> backend
DATA_DIR = os.path.join(HERE, "data")


def load_structured(path: str) -> List[Dict[str, Any]]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: str, data: Any) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)


def split_structured(structured: List[Dict[str, Any]]):
    cities = []
    spots = []
    for rec in structured:
        # city record: keep as-is (including hotels)
        cities.append(rec)

        # spot record: copy but remove 'hotels' key if present
        spot = {k: v for k, v in rec.items() if k != "hotels"}
        spots.append(spot)

    return cities, spots


def main():
    src = os.path.join(DATA_DIR, "structured_places.json")
    out_cities = os.path.join(DATA_DIR, "cities.json")
    out_spots = os.path.join(DATA_DIR, "spots.json")

    if not os.path.exists(src):
        print(f"Source not found: {src}")
        return

    structured = load_structured(src)
    cities, spots = split_structured(structured)

    write_json(out_cities, cities)
    write_json(out_spots, spots)

    print(f"Wrote {len(cities)} cities to {out_cities}")
    print(f"Wrote {len(spots)} spots to {out_spots}")


if __name__ == "__main__":
    main()
