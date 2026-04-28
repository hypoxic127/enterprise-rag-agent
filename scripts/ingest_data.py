"""
Data Ingestion Script — v2.0

Reads documents from ./data/ directory, chunks them with SentenceSplitter,
embeds with GeminiEmbedding, and upserts into the Qdrant collection.

Usage:
    python scripts/ingest_data.py                          # Ingest from ./data/
    python scripts/ingest_data.py --data-dir ./legal_docs  # Custom directory
"""

import os
import sys
import argparse
import logging

# Ensure app modules are importable
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.vector_store import ingest_documents

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description="Ingest documents into Qdrant vector store")
    parser.add_argument("--data-dir", default="data", help="Directory containing documents to ingest")
    parser.add_argument("--collection", default="enterprise_rag_gemini", help="Qdrant collection name")
    args = parser.parse_args()

    data_dir = args.data_dir
    if not os.path.exists(data_dir):
        logger.error("Data directory '%s' does not exist. Please create it and add documents.", data_dir)
        sys.exit(1)

    file_count = len([f for f in os.listdir(data_dir) if os.path.isfile(os.path.join(data_dir, f))])
    logger.info("Found %d file(s) in '%s'", file_count, data_dir)

    ingest_documents(data_dir=data_dir, collection_name=args.collection)
    logger.info("All done! Collection '%s' is ready for queries.", args.collection)


if __name__ == "__main__":
    main()
