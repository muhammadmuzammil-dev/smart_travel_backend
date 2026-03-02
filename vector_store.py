# backend/vector_store.py

import os
import chromadb

# Base dir = backend folder
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Where Chroma will store its DB files
VECTOR_DB_DIR = os.path.join(BASE_DIR, "vector_db")
os.makedirs(VECTOR_DB_DIR, exist_ok=True)

# NEW Chroma API: use PersistentClient (no Settings, no legacy stuff)
chroma_client = chromadb.PersistentClient(path=VECTOR_DB_DIR)

SPOTS_COLLECTION_NAME = "travel_spots"


def get_spots_collection():
    """
    Main collection for all city/spot embeddings.
    """
    return chroma_client.get_or_create_collection(SPOTS_COLLECTION_NAME)
