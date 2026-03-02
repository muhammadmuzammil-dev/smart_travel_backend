"""
Quick script to check if .env file exists and has required variables.
"""

import os
from pathlib import Path

def main():
    print("=" * 60)
    print("Environment Variables Check")
    print("=" * 60)
    print()
    
    # Check .env file location
    env_path = Path(__file__).parent / ".env"
    print(f"Looking for .env file at: {env_path}")
    print()
    
    if env_path.exists():
        print("✅ .env file found!")
        print()
        
        # Load .env file
        try:
            from dotenv import load_dotenv
            load_dotenv(env_path)
            print("✅ .env file loaded successfully")
        except ImportError:
            print("⚠️ python-dotenv not installed. Install with: pip install python-dotenv")
            print("   Trying to read environment variables from system...")
        except Exception as e:
            print(f"❌ Error loading .env file: {e}")
            return
        
        print()
        print("Environment Variables:")
        print("-" * 60)
        
        # Check required variables
        supabase_url = os.getenv("SUPABASE_URL", "")
        supabase_key = os.getenv("SUPABASE_KEY", "")
        
        if supabase_url:
            print(f"✅ SUPABASE_URL: {supabase_url[:40]}...")
        else:
            print("❌ SUPABASE_URL: NOT SET")
        
        if supabase_key:
            print(f"✅ SUPABASE_KEY: {supabase_key[:20]}...")
        else:
            print("❌ SUPABASE_KEY: NOT SET")
        
        # Check optional variables
        groq_key = os.getenv("GROQ_API_KEY", "")
        openai_key = os.getenv("OPENAI_API_KEY", "")
        
        print()
        print("Optional Variables:")
        print("-" * 60)
        print(f"{'✅' if groq_key else '⚠️'} GROQ_API_KEY: {'Set' if groq_key else 'Not set (optional)'}")
        print(f"{'✅' if openai_key else '⚠️'} OPENAI_API_KEY: {'Set' if openai_key else 'Not set (optional)'}")
        
        print()
        print("=" * 60)
        
        if supabase_url and supabase_key:
            print("✅ All required variables are set!")
            print()
            print("Next step: Run 'python test_supabase.py' to test the connection")
        else:
            print("❌ Missing required variables!")
            print()
            print("Please add to your .env file:")
            print("SUPABASE_URL=https://your-project-id.supabase.co")
            print("SUPABASE_KEY=your-anon-key-here")
    else:
        print("❌ .env file NOT FOUND!")
        print()
        print("Please create a .env file in the backend directory with:")
        print()
        print("SUPABASE_URL=https://your-project-id.supabase.co")
        print("SUPABASE_KEY=your-anon-key-here")
        print()
        print("To find these values:")
        print("1. Go to Supabase Dashboard → Settings → API")
        print("2. Copy 'Project URL' as SUPABASE_URL")
        print("3. Copy 'anon public' key as SUPABASE_KEY")
    
    print("=" * 60)

if __name__ == "__main__":
    main()

