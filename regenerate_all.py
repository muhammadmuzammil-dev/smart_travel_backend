"""
Script to regenerate all data and embeddings after adding new JSON files.
Run this after adding new data files like GB_normalized.json
"""

import os
import sys
from pathlib import Path

# Add current directory to path
BASE_DIR = Path(__file__).parent
sys.path.insert(0, str(BASE_DIR))

def run_step(step_name: str, script_path: str):
    """Run a preprocessing step and report results."""
    print(f"\n{'='*60}")
    print(f"Step: {step_name}")
    print(f"Running: {script_path}")
    print('='*60)
    
    if not os.path.exists(script_path):
        print(f"❌ Script not found: {script_path}")
        return False
    
    try:
        # Import and run the script
        if "preprocessing" in script_path:
            from utils import preprocessing
            preprocessing.merge_all()
            print("✅ Preprocessing completed")
        elif "generate_embeddings" in script_path:
            from generate_embeddings import main
            main()
            print("✅ Embeddings generated")
        elif "load_embeddings" in script_path:
            from load_embeddings import main
            main()
            print("✅ Embeddings loaded into ChromaDB")
        else:
            print(f"⚠️ Unknown script type: {script_path}")
            return False
        return True
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Main regeneration pipeline."""
    print("\n" + "="*60)
    print("🔄 REGENERATING ALL DATA AND EMBEDDINGS")
    print("="*60)
    
    steps = [
        ("1. Preprocessing JSON files", "utils/preprocessing.py"),
        ("2. Generating embeddings", "generate_embeddings.py"),
        ("3. Loading embeddings into ChromaDB", "load_embeddings.py"),
    ]
    
    results = []
    for step_name, script_path in steps:
        success = run_step(step_name, script_path)
        results.append((step_name, success))
        if not success:
            print(f"\n⚠️ Step failed: {step_name}")
            response = input("Continue anyway? (y/n): ")
            if response.lower() != 'y':
                print("\n❌ Regeneration stopped by user")
                return
    
    # Summary
    print("\n" + "="*60)
    print("📊 REGENERATION SUMMARY")
    print("="*60)
    for step_name, success in results:
        status = "✅" if success else "❌"
        print(f"{status} {step_name}")
    
    all_success = all(success for _, success in results)
    if all_success:
        print("\n✅ All steps completed successfully!")
        print("\nNext steps:")
        print("1. Restart your backend server: uvicorn main:app --reload")
        print("2. Test with a query: Generate itinerary for Islamabad")
    else:
        print("\n⚠️ Some steps failed. Check errors above.")
    
    return all_success

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)

