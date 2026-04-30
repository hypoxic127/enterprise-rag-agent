"""
RBAC-Aware Data Ingestion Script — v3.0

Ingests documents with access control metadata. Each file can be tagged
with roles that control who can retrieve it.

Usage:
    python scripts/ingest_with_rbac.py
    python scripts/ingest_with_rbac.py --data-dir ./data --roles-file ./data/rbac_roles.json

RBAC roles JSON format:
{
    "salary_report.pdf": ["executive"],
    "engineering_handbook.md": ["engineering", "management"],
    "mock_data.txt": ["all"]
}

Files not listed in the roles file default to ["all"] (accessible to everyone).
"""

import os
import sys
import json
import argparse

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.vector_store import ingest_documents
from app.core.logger import setup_logging

logger = setup_logging()


def load_roles_file(roles_path: str) -> dict[str, list[str]]:
    """Load the RBAC roles mapping from a JSON file."""
    if not os.path.exists(roles_path):
        logger.warning("Roles file '%s' not found — all docs will use default ['all']", roles_path)
        return {}

    with open(roles_path, "r", encoding="utf-8") as f:
        roles = json.load(f)

    logger.info("Loaded RBAC roles for %d files from '%s'", len(roles), roles_path)
    for fname, tags in roles.items():
        logger.info("  %s → %s", fname, tags)
    return roles


def main():
    parser = argparse.ArgumentParser(description="Ingest documents with RBAC metadata into Qdrant")
    parser.add_argument("--data-dir", default="data", help="Directory containing documents to ingest")
    parser.add_argument("--collection", default="enterprise_rag_gemini", help="Qdrant collection name")
    parser.add_argument("--roles-file", default="data/rbac_roles.json", help="JSON file mapping filenames to access roles")
    args = parser.parse_args()

    data_dir = args.data_dir
    if not os.path.exists(data_dir):
        logger.error("Data directory '%s' does not exist.", data_dir)
        sys.exit(1)

    file_count = len([f for f in os.listdir(data_dir) if os.path.isfile(os.path.join(data_dir, f))])
    logger.info("Found %d file(s) in '%s'", file_count, data_dir)

    # Load RBAC roles
    roles_map = load_roles_file(args.roles_file)

    # Ingest with RBAC metadata
    ingest_documents(
        data_dir=data_dir,
        collection_name=args.collection,
        access_roles_map=roles_map,
    )
    logger.info("RBAC-aware ingestion complete! Collection '%s' is ready.", args.collection)


if __name__ == "__main__":
    main()
