"""
Test script to verify Supabase connection and user table setup.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
env_path = Path(__file__).parent / ".env"
if env_path.exists():
    load_dotenv(env_path)
    print(f"✅ Loaded .env file from: {env_path}")
else:
    print(f"⚠️ .env file not found at: {env_path}")
    print("   Trying to load from current directory...")
    load_dotenv()  # Try loading from current directory

from supabase_client import get_supabase_client
import bcrypt

def test_supabase_connection():
    """Test if Supabase connection works."""
    print("Testing Supabase connection...")
    print("-" * 60)
    
    supabase = get_supabase_client()
    if not supabase:
        print("❌ Failed to initialize Supabase client")
        print("   Check your .env file for SUPABASE_URL and SUPABASE_KEY")
        return False
    
    print("✅ Supabase client initialized")
    
    # Test table existence
    try:
        result = supabase.table("users").select("id").limit(1).execute()
        print("✅ Users table exists and is accessible")
        return True
    except Exception as e:
        error_msg = str(e)
        if "relation" in error_msg.lower() or "does not exist" in error_msg.lower():
            print("❌ Users table not found!")
            print("   Please run the SQL script in Supabase SQL Editor")
            print("   See SUPABASE_SETUP.md for instructions")
        else:
            print(f"❌ Error accessing users table: {e}")
        return False

def test_user_registration():
    """Test user registration."""
    print("\nTesting user registration...")
    print("-" * 60)
    
    supabase = get_supabase_client()
    if not supabase:
        return False
    
    # Generate a test email
    import random
    test_email = f"test_{random.randint(1000, 9999)}@example.com"
    test_password = "testpassword123"
    
    # Hash password
    salt = bcrypt.gensalt()
    password_hash = bcrypt.hashpw(test_password.encode('utf-8'), salt).decode('utf-8')
    
    try:
        # Try to insert
        result = supabase.table("users").insert({
            "email": test_email,
            "password_hash": password_hash,
            "full_name": "Test User"
        }).execute()
        
        if result.data:
            print(f"✅ Successfully registered test user: {test_email}")
            
            # Clean up - delete test user
            try:
                supabase.table("users").delete().eq("email", test_email).execute()
                print(f"✅ Test user cleaned up")
            except:
                pass
            
            return True
        else:
            print("❌ Registration returned no data")
            return False
            
    except Exception as e:
        error_msg = str(e)
        if "duplicate key" in error_msg.lower() or "unique constraint" in error_msg.lower():
            print("⚠️ User already exists (this is expected if you ran this before)")
            return True
        else:
            print(f"❌ Registration failed: {e}")
            return False

def main():
    print("=" * 60)
    print("Supabase Connection Test")
    print("=" * 60)
    print()
    
    # Check if env vars are loaded
    supabase_url = os.getenv("SUPABASE_URL", "")
    supabase_key = os.getenv("SUPABASE_KEY", "")
    
    if not supabase_url or not supabase_key:
        print("❌ Environment variables not loaded!")
        print()
        print("Please check:")
        print(f"1. .env file exists at: {Path(__file__).parent / '.env'}")
        print("2. .env file contains:")
        print("   SUPABASE_URL=https://your-project-id.supabase.co")
        print("   SUPABASE_KEY=your-anon-key-here")
        print()
        print("Current values:")
        print(f"   SUPABASE_URL: {'Set' if supabase_url else 'NOT SET'}")
        print(f"   SUPABASE_KEY: {'Set' if supabase_key else 'NOT SET'}")
        return
    
    print(f"✅ Environment variables loaded")
    print(f"   SUPABASE_URL: {supabase_url[:30]}...")
    print(f"   SUPABASE_KEY: {supabase_key[:20]}...")
    print()
    
    # Test connection
    connection_ok = test_supabase_connection()
    
    if connection_ok:
        # Test registration
        registration_ok = test_user_registration()
        
        print("\n" + "=" * 60)
        if connection_ok and registration_ok:
            print("✅ All tests passed! Supabase is configured correctly.")
            print("\nNext steps:")
            print("1. Start your server: uvicorn main:app --reload")
            print("2. Test the API at: http://localhost:8000/docs")
        else:
            print("⚠️ Some tests failed. Check the errors above.")
    else:
        print("\n" + "=" * 60)
        print("❌ Connection test failed. Please check your configuration.")
    
    print("=" * 60)

if __name__ == "__main__":
    main()

