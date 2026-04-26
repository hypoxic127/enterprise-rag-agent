import os
import sys
import shutil

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.vector_store import get_vector_index

def main():
    print("Preparing data directory...")
    os.makedirs("data", exist_ok=True)
    if os.path.exists("mock_data.txt"):
        shutil.copy("mock_data.txt", "data/mock_data.txt")
        print("Copied mock_data.txt to data/")
    
    print("Ingesting data into Qdrant...")
    get_vector_index()
    print("Ingestion complete!")

if __name__ == "__main__":
    main()
