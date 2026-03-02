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

# Supabase configuration
SUPABASE_URL = _get_env_var("SUPABASE_URL", "")
SUPABASE_KEY = _get_env_var("SUPABASE_KEY", "")

# Note: Open-Meteo API is free and doesn't require an API key


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

