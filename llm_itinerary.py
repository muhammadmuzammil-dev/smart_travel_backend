import os
from functools import lru_cache
from typing import Dict, List

try:
    from groq import Groq
except ImportError:
    Groq = None

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None


def _get_env_var(key: str, default: str = "") -> str:
    return os.getenv(key, default).strip()


GROQ_MODEL_NAME = _get_env_var("GROQ_CHAT_MODEL", "llama-3.3-70b-versatile")
OPENAI_MODEL_NAME = _get_env_var("OPENAI_CHAT_MODEL", "gpt-4o-mini")


@lru_cache(maxsize=1)
def _get_groq_client():
    if Groq is None:
        return None
    api_key = _get_env_var("GROQ_API_KEY")
    if not api_key:
        return None
    try:
        return Groq(api_key=api_key)
    except Exception as exc:
        print(f"[LLM] Unable to init Groq client: {exc}")
        return None


@lru_cache(maxsize=1)
def _get_openai_client():
    if OpenAI is None:
        return None
    api_key = _get_env_var("OPENAI_API_KEY")
    if not api_key:
        return None
    try:
        return OpenAI(api_key=api_key)
    except Exception as exc:
        print(f"[LLM] Unable to init OpenAI client: {exc}")
        return None


# ─────────────────────────────────────────────────────────
# LOCAL FALLBACK "FAKE LLM" – NO INTERNET NEEDED
# ─────────────────────────────────────────────────────────
def _local_generate_itinerary_text(preferences: Dict, spots: List[Dict]) -> str:
    """
    Pure Python generator for a nice-looking itinerary text.
    Used when Groq/OpenAI are not configured or fail.
    """
    destination = preferences.get("destination_city", "your destination")
    departure_city = preferences.get("departure_city") or "Flexible origin"
    region = preferences.get("region") or ""
    num_days = preferences.get("num_days", 3)
    interests = preferences.get("interests") or []
    budget = preferences.get("budget_level", "medium")
    transport = preferences.get("transport_mode") or "local transport"
    travel_window = preferences.get("travel_window") or preferences.get("travel_date") or "Flexible dates"

    if isinstance(interests, list):
        interests_text = ", ".join(interests) if interests else "general sightseeing"
    else:
        interests_text = str(interests)

    # Distribute spots across days
    num_days = max(1, int(num_days))
    days: List[List[Dict]] = [[] for _ in range(num_days)]

    if spots:
        idx = 0
        for s in spots:
            days[idx % num_days].append(s)
            idx += 1

    lines: List[str] = []
    header = f"Detailed {num_days}-Day Itinerary for {destination}, {region}".strip(", ")
    lines.append(header)
    lines.append("=" * len(header))
    lines.append("")
    lines.append(f"Interests: {interests_text}")
    lines.append(f"Budget level: {budget.capitalize()} | Transport: {transport}")
    lines.append(f"Departure city: {departure_city}")
    lines.append(f"Travel dates: {travel_window}")
    lines.append("")
    lines.append("Note: This itinerary is generated based on curated spots from our internal dataset.")
    lines.append("")

    for day_idx in range(num_days):
        day_num = day_idx + 1
        day_spots = days[day_idx]

        lines.append(f"Day {day_num} – Explore {destination}")
        lines.append("-" * (len(lines[-1])))

        if not day_spots:
            lines.append("  • Flexible day for local exploration, cafes, and short walks.")
            lines.append("  • You can also revisit your favourite spots from earlier days.")
            lines.append("")
            continue

        # Morning, Afternoon, Evening splitting
        morning = day_spots[:1]
        afternoon = day_spots[1:3]
        evening = day_spots[3:]

        def fmt_spot(s: Dict) -> str:
            name = s.get("name") or s.get("spot_name") or "Unknown spot"
            city = s.get("city") or destination
            region_s = s.get("region") or region
            return f"{name} ({city}, {region_s})"

        # Morning
        if morning:
            lines.append("  Morning:")
            for s in morning:
                lines.append(f"    • Visit {fmt_spot(s)}")
            lines.append("    • Start early to avoid crowds and enjoy cooler weather.")
            lines.append("")

        # Afternoon
        if afternoon:
            lines.append("  Afternoon:")
            for s in afternoon:
                lines.append(f"    • Continue to {fmt_spot(s)}")
            lines.append("    • Plan a lunch break at a local restaurant or dhaba nearby.")
            lines.append("")

        # Evening
        if evening:
            lines.append("  Evening:")
            for s in evening:
                lines.append(f"    • Optional evening visit: {fmt_spot(s)}")
            lines.append("    • Return to your accommodation, rest, and enjoy a relaxed dinner.")
            lines.append("")
        else:
            lines.append("  Evening:")
            lines.append("    • Relax at your hotel/guesthouse and explore nearby markets for shopping.")
            lines.append("")

        # Small generic tip per day
        lines.append("  Tip:")
        lines.append("    • Keep water, snacks, and a light jacket with you, as weather can change quickly.")
        lines.append("")

    return "\n".join(lines)


# ─────────────────────────────────────────────────────────
# SHARED PROMPT BUILDER (for real LLMs, if keys exist)
# ─────────────────────────────────────────────────────────
def build_spots_summary(spots: List[Dict]) -> str:
    lines = []
    for i, s in enumerate(spots, start=1):
        name = s.get('name', 'Unknown')
        city = s.get('city', '')
        region = s.get('region', '')
        desc = s.get('desc', '')
        images = s.get('images', [])
        
        line = (
            f"{i}. {name} – "
            f"{city}, {region}. "
            f"{desc}"
        )
        
        # Add image info if available
        if images:
            image_count = len(images) if isinstance(images, list) else 1
            line += f" [Images available: {image_count} photo(s)]"
        
        lines.append(line)
    return "\n".join(lines)


def _build_prompt(preferences: Dict, spots: List[Dict], language: str = "en") -> str:
    spots_text = build_spots_summary(spots)

    interests = preferences.get("interests") or []
    if isinstance(interests, list):
        interests_text = ", ".join(interests) if interests else "general sightseeing"
    else:
        interests_text = str(interests)

    language_instruction = ""
    if language == "ur":
        language_instruction = "\nIMPORTANT: Write the entire itinerary in Urdu (اردو). Use proper Urdu script and maintain a natural, friendly tone."
    
    prompt = f"""
You are an expert Pakistani travel planner.
{language_instruction}

Create a detailed, day-by-day travel itinerary for a trip with the following preferences:

- Destination city: {preferences.get("destination_city")}
- Departure city: {preferences.get("departure_city") or "Not specified"}
- Region: {preferences.get("region") or "N/A"}
- Number of days: {preferences.get("num_days")}
- Interests: {interests_text}
- Budget level: {preferences.get("budget_level") or "not specified"}
- Transport mode: {preferences.get("transport_mode") or "not specified"}
- Travel dates: {preferences.get("travel_window") or preferences.get("travel_date") or "flexible"}

Use ONLY the following list of places from our internal dataset as the main options. 
You can choose the best ones and decide which day to visit which spot:

{spots_text}

Requirements for the itinerary:
- Provide a clear heading for each day (e.g., "Day 1 – Explore Upper Swat").
- IMPORTANT: Do NOT use markdown bold formatting (**) or markdown headers (#) for day headings. Use plain text only.
- For each day, describe the morning, afternoon, and evening activities.
- Mention which specific spots from the list are visited each day.
- Keep the tone friendly but concise.
- Assume the user is starting each day from accommodation within the destination city.
- Include small practical tips (start early, clothing, snacks) but do NOT invent totally new locations.
- Note: Many destinations have images available - you can mention this when describing scenic or photogenic spots.
- Format day headers as plain text like: "Day 1 – Explore Upper Swat" (no bold, no markdown)

Return only the itinerary text. Do NOT include meta commentary or JSON.
    """.strip()
    return prompt


# ─────────────────────────────────────────────────────────
# HELPER: STRIP MARKDOWN BOLD FROM DAY HEADERS
# ─────────────────────────────────────────────────────────
def _strip_markdown_bold_from_headers(text: str) -> str:
    """
    Remove markdown bold formatting (**) and header markers (#) from day headers to prevent them from being displayed as bold.
    """
    import re
    lines = text.split('\n')
    cleaned_lines = []
    for line in lines:
        # Check if this is a day header line (starts with Day X, 🗺️ Day X, or # Day X)
        if re.match(r'^(\s*)(#+\s*)?(🗺️\s*)?(Day\s+\d+)', line, re.IGNORECASE):
            # Remove markdown formatting: **, #, and extra spaces
            cleaned_line = line.replace('**', '')
            cleaned_line = re.sub(r'^#+\s*', '', cleaned_line)  # Remove leading # markers
            cleaned_line = cleaned_line.strip()
            # Preserve the emoji and day text but ensure no bold formatting
            cleaned_lines.append(cleaned_line)
        else:
            cleaned_lines.append(line)
    return '\n'.join(cleaned_lines)


# ─────────────────────────────────────────────────────────
# PUBLIC ENTRY POINT – ALWAYS RETURNS A STRING
# ─────────────────────────────────────────────────────────
def generate_itinerary_llm(preferences: Dict, spots: List[Dict], language: str = "en") -> str:
    """
    Main function used by the FastAPI route.

    Behaviour:
    - If Groq/OpenAI keys are valid → use real LLM to generate text.
    - If keys are missing/invalid OR network fails → use local fallback generator.
    """

    # Safety: never crash the API because of LLM issues.
    try:
        # No spots? Just return a short message.
        if not spots:
            return "No suitable tourist spots were found for these preferences. Please try adjusting your city, region, or interests."

        groq_client = _get_groq_client()
        openai_client = _get_openai_client()

        # If no keys configured, go straight to local generator.
        if groq_client is None and openai_client is None:
            return _local_generate_itinerary_text(preferences, spots)

        prompt = _build_prompt(preferences, spots, language)
        
        system_message = "You are a helpful travel itinerary planner."
        if language == "ur":
            system_message = "آپ ایک مددگار سفر کا منصوبہ ساز ہیں۔ آپ کو اردو میں جواب دینا چاہیے۔"

        # 1) Try OpenAI first for better itinerary generation
        if openai_client is not None:
            try:
                openai_resp = openai_client.chat.completions.create(
                    model=OPENAI_MODEL_NAME or "gpt-4o-mini",
                    messages=[
                        {"role": "system", "content": system_message},
                        {"role": "user", "content": prompt},
                    ],
                    temperature=0.7,
                )
                result = openai_resp.choices[0].message.content
                # Strip markdown bold from day headers
                return _strip_markdown_bold_from_headers(result)
            except Exception as e:
                print(f"[LLM] OpenAI failed, falling back to Groq: {e}")

        # 2) Try Groq as fallback
        if groq_client is not None:
            try:
                groq_resp = groq_client.chat.completions.create(
                    model=GROQ_MODEL_NAME or "llama-3.3-70b-versatile",
                    messages=[
                        {"role": "system", "content": system_message},
                        {"role": "user", "content": prompt},
                    ],
                    temperature=0.7,
                )
                result = groq_resp.choices[0].message.content
                # Strip markdown bold from day headers
                return _strip_markdown_bold_from_headers(result)
            except Exception as e:
                print(f"[LLM] Groq failed, falling back to local generator: {e}")

        # 3) If both LLMs fail for any reason → local fallback
        return _local_generate_itinerary_text(preferences, spots)

    except Exception as e:
        print(f"[LLM] Completely failed, using minimal fallback: {e}")
        # Last-resort fallback, never crash the endpoint.
        return _local_generate_itinerary_text(preferences, spots)
