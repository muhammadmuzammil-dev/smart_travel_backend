"""
Quick setup verification script.
Run this to check if everything is configured correctly.
"""

import os
import sys
from pathlib import Path

def check_file_exists(filepath: str, description: str) -> bool:
    """Check if a file exists."""
    exists = os.path.exists(filepath)
    status = "✅" if exists else "❌"
    print(f"{status} {description}: {filepath}")
    return exists

def check_env_var(var_name: str, required: bool = True) -> bool:
    """Check if environment variable is set."""
    value = os.getenv(var_name, "")
    exists = bool(value)
    status = "✅" if exists else ("❌" if required else "⚠️")
    print(f"{status} {var_name}: {'Set' if exists else ('Required' if required else 'Optional')}")
    return exists

def main():
    print("=" * 60)
    print("Smart Travel Application - Setup Verification")
    print("=" * 60)
    print()
    
    BASE_DIR = Path(__file__).parent
    DATA_DIR = BASE_DIR / "data"
    
    all_good = True
    
    # Check environment variables
    print("📋 Environment Variables:")
    print("-" * 60)
    supabase_url = check_env_var("SUPABASE_URL", required=True)
    supabase_key = check_env_var("SUPABASE_KEY", required=True)
    groq_key = check_env_var("GROQ_API_KEY", required=False)
    openai_key = check_env_var("OPENAI_API_KEY", required=False)
    print()
    
    # Check data files
    print("📁 Data Files:")
    print("-" * 60)
    spots_file = check_file_exists(DATA_DIR / "structured_spots.json", "Structured spots")
    spots_emb = check_file_exists(DATA_DIR / "spots_with_embeddings.json", "Spots with embeddings")
    hotels_emb = check_file_exists(DATA_DIR / "hotels_with_embeddings.json", "Hotels with embeddings")
    cities_file = check_file_exists(DATA_DIR / "structured_cities.json", "Structured cities")
    print()
    
    # Check vector database
    print("🗄️ Vector Database:")
    print("-" * 60)
    vector_db = check_file_exists(BASE_DIR / "vector_db", "ChromaDB directory")
    if vector_db:
        db_files = list((BASE_DIR / "vector_db").glob("*"))
        print(f"   Found {len(db_files)} database files")
    print()
    
    # Check required packages
    print("📦 Python Packages:")
    print("-" * 60)
    packages = [
        "fastapi",
        "uvicorn",
        "chromadb",
        "sentence_transformers",
        "supabase",
        "bcrypt",
        "requests",
        "pydantic"
    ]
    
    missing_packages = []
    for package in packages:
        try:
            __import__(package.replace("-", "_"))
            print(f"✅ {package}: Installed")
        except ImportError:
            print(f"❌ {package}: Not installed")
            missing_packages.append(package)
    print()
    
    # Summary
    print("=" * 60)
    print("Summary:")
    print("-" * 60)
    
    issues = []
    
    if not supabase_url or not supabase_key:
        issues.append("❌ Supabase credentials not configured")
        all_good = False
    
    if not spots_file:
        issues.append("⚠️ Run: python utils/preprocessing.py")
    
    if not spots_emb:
        issues.append("⚠️ Run: python generate_embeddings.py")
    
    if not hotels_emb:
        issues.append("⚠️ Run: python utils/hotel_processor.py")
    
    if not vector_db:
        issues.append("⚠️ Run: python load_embeddings.py")
    
    if missing_packages:
        issues.append(f"❌ Install missing packages: pip install {' '.join(missing_packages)}")
        all_good = False
    
    if all_good and not issues:
        print("✅ All checks passed! Your setup looks good.")
        print()
        print("Next steps:")
        print("1. Start the server: uvicorn main:app --reload")
        print("2. Visit: http://localhost:8000/docs")
    else:
        print("⚠️ Some issues found:")
        for issue in issues:
            print(f"   {issue}")
        print()
        print("Please refer to SETUP_GUIDE.md for detailed instructions.")
    
    print("=" * 60)

if __name__ == "__main__":
    main()

