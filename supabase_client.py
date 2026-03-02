"""
Supabase client initialization and utilities for user management.
"""

import os
from pathlib import Path
from typing import Optional
from functools import lru_cache

# Load .env file if it exists
try:
    from dotenv import load_dotenv
    env_path = Path(__file__).parent / ".env"
    if env_path.exists():
        load_dotenv(env_path)
    else:
        load_dotenv()  # Try loading from current directory
except ImportError:
    pass  # dotenv not installed, will use system env vars

try:
    from supabase import create_client, Client
except ImportError:
    Client = None
    create_client = None


def _get_env_var(key: str, default: str = "") -> str:
    """Get environment variable."""
    return os.getenv(key, default).strip()


@lru_cache(maxsize=1)
def get_supabase_client() -> Optional[Client]:
    """
    Get or create Supabase client instance.
    Returns None if Supabase is not configured.
    """
    if Client is None or create_client is None:
        print("[Supabase] supabase-py package not installed. Install with: pip install supabase")
        return None
    
    supabase_url = _get_env_var("SUPABASE_URL")
    supabase_key = _get_env_var("SUPABASE_KEY")
    
    if not supabase_url or not supabase_key:
        print("[Supabase] SUPABASE_URL or SUPABASE_KEY not set in environment variables")
        return None
    
    try:
        client = create_client(supabase_url, supabase_key)
        print("[Supabase] Client initialized successfully")
        return client
    except Exception as e:
        print(f"[Supabase] Failed to initialize client: {e}")
        return None


# SQL Schema for users table (run this in Supabase SQL editor):
"""
CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    full_name TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);

-- Function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Trigger to auto-update updated_at
CREATE TRIGGER update_users_updated_at BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
"""

