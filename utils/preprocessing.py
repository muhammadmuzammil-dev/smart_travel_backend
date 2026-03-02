import os, re, json, logging, difflib
import pandas as pd
from collections import defaultdict
from typing import List, Dict, Any, Optional

# ───────────────────────── Logging ─────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s: %(message)s"
)

# ───────────────────────── Paths ───────────────────────────
BASE_DIR = os.path.dirname(os.path.dirname(__file__))  # backend/
data_dir = os.path.join(BASE_DIR, "data")
hotels_folder = os.path.join(data_dir, "hotels")
kpk_path = os.path.join(data_dir, "kpk_clean.json")
gilgit_path = os.path.join(data_dir, "GilgitBaltistan.json")

# ─────────────── Exclusions & Aliases ───────────────
EXCLUDE_CSV_CITIES = {
    "islamabad","lahore","karachi","rawalpindi","multan","sialkot",
    "faisalabad","bahawalpur","hyderabad","quetta","taxila","harappa",
    "gujranwala","muzaffarabad","neelum_valley","arang_kel","ratti_gali",
    "sharda"
}

ALIAS_TO_ATTR_CITY = {
    "malam_jabba": "Swat",
    "kalam": "Swat",
    "kaghan": "Naran Valley",
    "shogran": "Naran Valley",
    "nathiagali": "Abbottabad",
    "ayubia": "Abbottabad",
    "karimabad": "Hunza",
    "mingora": "Mingora",
    "naran": "Naran Valley",
    "skardu": "Skardu",
    "gilgit": "Gilgit",
    "chitral": "Chitral",
    "abbottabad": "Abbottabad",
    "peshawar": "Peshawar",
}

# ───────────────────── Helper functions ────────────────────
def file_exists(path, required=True):
    if os.path.exists(path):
        logging.info(f"FOUND: {path}")
        return True
    msg = f"MISSING: {path}"
    logging.error(msg) if required else logging.warning(msg)
    return False

def extract_lat_lon_from_url(map_url):
    if not isinstance(map_url, str):
        return None, None
    m = re.search(r"!3d([-0-9.]+)!2d([-0-9.]+)", map_url)
    return (float(m.group(1)), float(m.group(2))) if m else (None, None)

def budget_category(price):
    if price is None: return None
    return "low" if price < 5000 else "mid" if price < 12000 else "high"

def norm_city(name: str) -> str:
    if not isinstance(name, str): return ""
    s = name.lower()
    for t in ["district","valley","city","tehsil","_", "-", " "]:
        s = s.replace(t, " ")
    return re.sub(r"\s+", " ", s).strip()

def extract_city_from_location(loc: str) -> str:
    if not isinstance(loc, str): return "Unknown"
    parts = [p.strip() for p in loc.split(",") if p.strip()]
    noise = re.compile(r"(\+)|\b(road|rd\.?|street|st\.?|phase|sector|bazar|gt\s*road)\b", re.I)
    for p in parts:
        if not noise.search(p):
            return p.title()
    return parts[0].title() if parts else "Unknown"

# ─────────────── NEW: Load province data with new structure ───────────────
def load_province_data_new_format(file_path: str) -> List[Dict[str, Any]]:
    """
    Load province JSON files with the new hierarchical structure:
    province -> divisions -> districts -> destinations
    
    Returns a list of destination records with all new fields.
    """
    if not file_exists(file_path, required=False):
        return []
    
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        logging.exception(f"Failed to read {file_path}: {e}")
        return []
    
    destinations = []
    province_name = data.get("province", "Unknown")
    
    # Iterate through divisions
    for division in data.get("divisions", []):
        division_name = division.get("name", "Unknown")
        
        # Iterate through districts
        for district in division.get("districts", []):
            district_name = district.get("name", "Unknown")
            
            # Iterate through destinations
            for dest in district.get("destinations", []):
                location = dest.get("location", {})
                coordinates = location.get("coordinates", {})
                
                # Extract all fields - use province from location if available, otherwise from top level
                location_province = location.get("province", "")
                final_province = location_province if location_province else province_name
                
                # Handle district - can be string or list
                location_district = location.get("district")
                if isinstance(location_district, list):
                    location_district = location_district[0] if location_district else district_name
                elif not location_district:
                    location_district = district_name
                
                record = {
                    "name": dest.get("name", ""),
                    "description": dest.get("description", ""),
                    "category": dest.get("category", ""),
                    "highlights": dest.get("highlights", []),
                    "best_time_to_visit": dest.get("best_time_to_visit", ""),
                    "images": dest.get("images", []),
                    "province": final_province,
                    "division": division_name,
                    "district": location_district,
                    "city": location_district,  # For backward compatibility
                    "region": final_province,  # For backward compatibility
                    "latitude": coordinates.get("latitude"),
                    "longitude": coordinates.get("longitude"),
                    "image_url": dest.get("images", [None])[0] if dest.get("images") else None,
                    "url": None  # Can be added if available in future
                }
                
                # Filter out records with invalid names (like "Province", "Divisions", etc.)
                name = record.get("name", "").strip()
                invalid_names = {"province", "division", "divisions", "district", "districts", "city", "region"}
                if not name or name.lower() in invalid_names:
                    continue
                
                destinations.append(record)
    
    logging.info(f"Loaded {len(destinations)} destinations from {file_path}")
    return destinations

# ─────────────── Step 1 – Attractions (KPK) ───────────────
def load_kpk_attractions():
    if not file_exists(kpk_path): return {}
    try:
        with open(kpk_path,"r",encoding="utf-8") as f: data=json.load(f)
    except Exception as e:
        logging.exception(f"Failed to read {kpk_path}: {e}"); return {}

    cities = defaultdict(lambda:{
        "region":"Khyber Pakhtunkhwa","attractions":[],
        "hotels":{"low":[],"mid":[],"high":[]}
    })
    for p in data:
        city = extract_city_from_location(p.get("location",""))
        rec = {
            "name": p.get("title") or p.get("name"),
            "description": p.get("description",""),
            "latitude": p.get("latitude"),
            "longitude": p.get("longitude"),
            "image_url": p.get("image_url"),
            "url": None
        }
        cities[city]["attractions"].append(rec)
    logging.info(f"KPK attractions: {sum(len(v['attractions']) for v in cities.values())} across {len(cities)} cities.")
    return cities

# ─────────────── Step 1b – Attractions (GB) ───────────────
def load_gilgit_attractions():
    if not file_exists(gilgit_path): return {}
    try:
        with open(gilgit_path,"r",encoding="utf-8") as f: data=json.load(f)
    except Exception as e:
        logging.exception(f"Failed to read {gilgit_path}: {e}"); return {}

    cities = defaultdict(lambda:{
        "region":"Gilgit-Baltistan","attractions":[],
        "hotels":{"low":[],"mid":[],"high":[]}
    })
    total=0
    for d in data:
        city = d.get("district_name","Unknown").replace("District","").strip().title()
        for dest in d.get("destinations",[]):
            lat,lon = extract_lat_lon_from_url(dest.get("map_url"))
            rec = {
                "name": dest.get("title"),
                "description": dest.get("description",""),
                "latitude": lat, "longitude": lon,
                "image_url": dest.get("image"),
                "url": dest.get("url")
            }
            cities[city]["attractions"].append(rec); total+=1
    logging.info(f"GB attractions: {total} across {len(cities)} cities.")
    return cities

# ─────────────── Step 2 – Hotels ───────────────
def load_hotels():
    hotels = defaultdict(lambda: {"low": [], "mid": [], "high": []})
    if not file_exists(hotels_folder, required=False):
        return hotels

    csvs = [f for f in os.listdir(hotels_folder) if f.lower().endswith(".csv")]
    if not csvs:
        logging.warning("No hotel CSVs found.")
        return hotels

    logging.info(f"Hotel CSV files discovered ({len(csvs)}): {', '.join(csvs)}")

    for fn in csvs:
        base = os.path.splitext(fn)[0].lower()
        city_from_file = ALIAS_TO_ATTR_CITY.get(base, base).title()
        path = os.path.join(hotels_folder, fn)

        try:
            df = pd.read_csv(path).fillna("")
        except Exception as e:
            logging.exception(f"Failed {fn}: {e}")
            continue

        added = 0
        for _, row in df.iterrows():
            name = None
            for c in ["name", "Name", "hotel_name", "Hotel", "title"]:
                if c in df.columns and str(row[c]).strip():
                    name = str(row[c]).strip()
                    break
            if not name:
                continue

            price = None
            for c in df.columns:
                if "price" in c.lower():
                    digits = re.findall(r"\d+", str(row[c]).replace(",", ""))
                    if digits:
                        price = float(digits[0])
                    break

            tier = budget_category(price)
            if tier:
                hotels[city_from_file][tier].append({"name": name, "price": price})
                added += 1

        logging.info(f"{fn}: {added} hotels → {city_from_file}")

    return hotels

# ─────────────── Step 3 – Merge ───────────────
def load_province_attractions(path, region_name, district_key=None, dest_key=None):
    """Generic loader for any province JSON file."""
    if not file_exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        logging.exception(f"Failed to read {path}: {e}")
        return {}

    cities = defaultdict(lambda: {
        "region": region_name,
        "attractions": [],
        "hotels": {"low": [], "mid": [], "high": []}
    })

    # Province file type detection
    if dest_key:  # e.g. GilgitBaltistan.json, Balochistan.json
        for d in data:
            if isinstance(d, dict):
                city = d.get(district_key, "Unknown").replace("District", "").strip().title()
                for dest in d.get(dest_key, []):
                    lat, lon = extract_lat_lon_from_url(dest.get("map_url"))
                    rec = {
                        "name": dest.get("title"),
                        "description": dest.get("description", ""),
                        "latitude": lat, "longitude": lon,
                        "image_url": dest.get("image"),
                        "url": dest.get("url")
                    }
                    cities[city]["attractions"].append(rec)
            elif isinstance(d, str):
                # fallback for string entries
                city = d.replace("District", "").strip().title()
                cities[city]["attractions"].append({
                    "name": city,
                    "description": "",
                    "latitude": None,
                    "longitude": None,
                    "image_url": None,
                    "url": None
                })
    else:  # e.g. KPK.json, Punjab.json, Islamabad.json
        for p in data:
            if isinstance(p, dict):
                city = extract_city_from_location(p.get("location", ""))
                rec = {
                    "name": p.get("title") or p.get("name"),
                    "description": p.get("description", ""),
                    "latitude": p.get("latitude"),
                    "longitude": p.get("longitude"),
                    "image_url": p.get("image_url"),
                    "url": None
                }
                cities[city]["attractions"].append(rec)
            elif isinstance(p, str):
                # fallback if file only contains city names or simple entries
                cities[p.title()]["attractions"].append({
                    "name": p.title(),
                    "description": "",
                    "latitude": None,
                    "longitude": None,
                    "image_url": None,
                    "url": None
                })

    total = sum(len(v["attractions"]) for v in cities.values())
    logging.info(f"{region_name}: {total} attractions across {len(cities)} cities.")
    return cities


def merge_all():
    """Merge all province data - supports both old and new formats."""
    # Load new format files first
    new_format_files = {
        "Islamabad_final.json": "Islamabad Capital Territory",
        "AJK.json": "Azad Jammu & Kashmir",
        "Punjab_final.json": "Punjab",
        "Sindh.json": "Sindh",
        "kpk.json": "Khyber Pakhtunkhwa",
        "Balochistan_final.json": "Balochistan",
        "GB_normalized.json": "Gilgit-Baltistan"  # New GB file with normalized structure
    }
    
    all_destinations = []
    
    # Process new format files
    for filename, province_name in new_format_files.items():
        file_path = os.path.join(data_dir, filename)
        destinations = load_province_data_new_format(file_path)
        all_destinations.extend(destinations)
    
    # Build SPOTS dataset from new format
    spots = []
    for dest in all_destinations:
        spots.append({
            "city": dest.get("city", ""),
            "region": dest.get("region", ""),
            "name": dest.get("name", ""),
            "description": dest.get("description", ""),
            "category": dest.get("category", ""),
            "highlights": dest.get("highlights", []),
            "best_time_to_visit": dest.get("best_time_to_visit", ""),
            "images": dest.get("images", []),
            "district": dest.get("district", ""),
            "division": dest.get("division", ""),
            "latitude": dest.get("latitude"),
            "longitude": dest.get("longitude"),
            "image_url": dest.get("image_url"),
            "url": dest.get("url")
        })
    
    # Also process old format files for backward compatibility
    kpk = load_province_attractions(kpk_path, "Khyber Pakhtunkhwa")
    gb = load_province_attractions(gilgit_path, "Gilgit-Baltistan", "district_name", "destinations")

    punjab_path = os.path.join(data_dir, "Punjab.json")
    islamabad_path = os.path.join(data_dir, "Islamabad.json")
    balochistan_path = os.path.join(data_dir, "Balochistan.json")

    punjab = load_province_attractions(punjab_path, "Punjab")
    islamabad = load_province_attractions(islamabad_path, "Islamabad")
    balochistan = load_province_attractions(balochistan_path, "Balochistan", "district_name", "destinations")

    all_provinces = [kpk, gb, punjab, islamabad, balochistan]
    hotel_data = load_hotels()

    # Add old format spots if they don't exist in new format
    for province in all_provinces:
        for city, data in province.items():
            for a in data["attractions"]:
                # Check if this spot already exists in new format
                exists = any(
                    s.get("name") == a.get("name") and 
                    s.get("city") == city 
                    for s in spots
                )
                if not exists:
                    spots.append({
                        "city": city,
                        "region": data["region"],
                        "name": a["name"],
                        "description": a["description"],
                        "latitude": a["latitude"],
                        "longitude": a["longitude"],
                        "image_url": a["image_url"],
                        "url": a["url"],
                        "category": "",
                        "highlights": [],
                        "best_time_to_visit": "",
                        "images": [a["image_url"]] if a.get("image_url") else [],
                        "district": city,
                        "division": ""
                    })
    
    spots_out = os.path.join(data_dir, "structured_spots.json")
    os.makedirs(data_dir, exist_ok=True)
    with open(spots_out, "w", encoding="utf-8") as f:
        json.dump(spots, f, indent=4, ensure_ascii=False)
    logging.info(f"✅ structured_spots.json created ({len(spots)} attractions).")

    # ── Build CITIES dataset ──
    cities = []
    CITY_REGION_MAP = {
        # ── Khyber Pakhtunkhwa ──
        "abbottabad": "Khyber Pakhtunkhwa",
        "kaghan": "Khyber Pakhtunkhwa",
        "kalam": "Khyber Pakhtunkhwa",
        "malam_jabba": "Khyber Pakhtunkhwa",
        "mingora": "Khyber Pakhtunkhwa",
        "naran": "Khyber Pakhtunkhwa",
        "nathiagali": "Khyber Pakhtunkhwa",
        "peshawar": "Khyber Pakhtunkhwa",
        "shogran": "Khyber Pakhtunkhwa",
        "swat": "Khyber Pakhtunkhwa",

        # ── Gilgit-Baltistan ──
        "gilgit": "Gilgit-Baltistan",
        "hunza": "Gilgit-Baltistan",
        "karimabad": "Gilgit-Baltistan",
        "skardu": "Gilgit-Baltistan",

        # ── Punjab ──
        "bahawalpur": "Punjab",
        "faisalabad": "Punjab",
        "gujranwala": "Punjab",
        "lahore": "Punjab",
        "multan": "Punjab",
        "murree": "Punjab",
        "sialkot": "Punjab",
        "taxila": "Punjab",

        # ── Sindh ──
        "hyderabad": "Sindh",
        "karachi": "Sindh",

        # ── Balochistan ──
        "quetta": "Balochistan",

        # ── Azad Jammu & Kashmir ──
        "muzaffarabad": "Azad Jammu & Kashmir",
        "neelum_valley": "Azad Jammu & Kashmir",
        "arang_kel": "Azad Jammu & Kashmir",
        "ratti_gali": "Azad Jammu & Kashmir",
        "sharda": "Azad Jammu & Kashmir",

        # ── Islamabad Capital Territory ──
        "islamabad": "Islamabad Capital Territory",
        "rawalpindi": "Islamabad Capital Territory",

        # ── Historic / mixed ──
        "harappa": "Punjab",
        "bhurban": "Punjab",
    }
    # Build cities.json
    for city, tiers in hotel_data.items():
        total = sum(len(v) for v in tiers.values())
        if total == 0:
            continue
        region = CITY_REGION_MAP.get(city.lower(), "Unknown")
        cities.append({
            "city": city.title(),
            "region": region,
            "hotels": tiers
        })

    cities_out = os.path.join(data_dir, "structured_cities.json")
    with open(cities_out, "w", encoding="utf-8") as f:
        json.dump(cities, f, indent=4, ensure_ascii=False)
    logging.info(f"✅ structured_cities.json created ({len(cities)} cities).")

# ───────────────────────── Run ─────────────────────────
if __name__=="__main__":
    for p in [data_dir,hotels_folder,kpk_path,gilgit_path]:
        file_exists(p,required=False)
    merge_all()
