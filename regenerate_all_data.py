"""
Complete regeneration script for all travel data.
This script will:
1. Preprocess all JSON files (including GB_normalized.json)
2. Generate embeddings for spots
3. Load embeddings into ChromaDB

Run this after adding new JSON files or updating existing ones.
"""

import os
import sys
import subprocess
from pathlib import Path

# Add current directory to path
BASE_DIR = Path(__file__).parent
sys.path.insert(0, str(BASE_DIR))

def run_step(step_name: str, script_path: str, description: str):
    """Run a preprocessing step and report results."""
    print(f"\n{'='*70}")
    print(f"Step: {step_name}")
    print(f"Description: {description}")
    print(f"Running: {script_path}")
    print('='*70)
    
    script_full_path = BASE_DIR / script_path
    
    if not script_full_path.exists():
        print(f"[ERROR] Script not found: {script_full_path}")
        return False
    
    try:
        # Run the script
        result = subprocess.run(
            [sys.executable, str(script_full_path)],
            cwd=str(BASE_DIR),
            capture_output=True,
            text=True,
            encoding='utf-8'
        )
        
        if result.returncode == 0:
            print(f"[OK] {step_name} completed successfully")
            if result.stdout:
                print("Output:")
                print(result.stdout)
            return True
        else:
            print(f"[ERROR] {step_name} failed with exit code {result.returncode}")
            if result.stderr:
                print("Error output:")
                print(result.stderr)
            if result.stdout:
                print("Standard output:")
                print(result.stdout)
            return False
            
    except Exception as e:
        print(f"[ERROR] Error running {step_name}: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Main regeneration workflow."""
    print("\n" + "="*70)
    print("SMART TRAVEL AI - COMPLETE DATA REGENERATION")
    print("="*70)
    print("\nThis will regenerate all data and embeddings from JSON files.")
    print("Including: GB_normalized.json, kpk.json, Punjab_final.json, etc.")
    print("\nSteps:")
    print("1. Preprocess all JSON files → structured_spots.json")
    print("2. Generate embeddings → spots_with_embeddings.json")
    print("3. Load embeddings into ChromaDB")
    print("\n" + "="*70)
    
    # Step 1: Preprocessing
    success = run_step(
        "Preprocessing",
        "utils/preprocessing.py",
        "Process all JSON files and create structured_spots.json"
    )
    
    if not success:
        print("\n[ERROR] Preprocessing failed. Stopping.")
        return
    
    # Step 2: Generate embeddings
    success = run_step(
        "Generate Embeddings",
        "generate_embeddings.py",
        "Generate embeddings for all spots using sentence-transformers"
    )
    
    if not success:
        print("\n[ERROR] Embedding generation failed. Stopping.")
        return
    
    # Step 3: Load embeddings into ChromaDB
    success = run_step(
        "Load into ChromaDB",
        "load_embeddings.py",
        "Load all embeddings into ChromaDB vector database"
    )
    
    if not success:
        print("\n[ERROR] Loading into ChromaDB failed.")
        return
    
    # Final summary
    print("\n" + "="*70)
    print("[SUCCESS] REGENERATION COMPLETE!")
    print("="*70)
    print("\nAll data has been regenerated:")
    print("  [OK] structured_spots.json - All spots from JSON files")
    print("  [OK] spots_with_embeddings.json - Spots with embeddings")
    print("  [OK] ChromaDB - Vector database updated")
    print("\nYou can now start the backend server:")
    print("  cd backend")
    print("  uvicorn main:app --reload")
    print("="*70)


if __name__ == "__main__":
    main()

