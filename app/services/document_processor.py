import os
from llama_index.core import SimpleDirectoryReader
from llama_index.core.node_parser import SentenceSplitter
from loguru import logger


def load_and_split_documents(
    data_dir: str,
    access_roles_map: dict[str, list[str]] | None = None,
):
    """
    Load documents from the specified directory and split them into nodes.
    
    Args:
        data_dir: Directory containing documents.
        access_roles_map: Optional mapping of filename → access roles.
            Example: {"salary_report.pdf": ["executive"], "handbook.txt": ["all"]}
            If not provided, all documents default to ["all"] (public).
    """
    if not os.path.exists(data_dir):
        os.makedirs(data_dir, exist_ok=True)
        with open(os.path.join(data_dir, "sample.txt"), "w", encoding="utf-8") as f:
            f.write("Enterprise-RAG-Agent is an intelligent legal and investment analysis system built with Python, LlamaIndex, Qdrant, and Next.js.")
            
    # Load documents
    reader = SimpleDirectoryReader(input_dir=data_dir, required_exts=[".txt", ".pdf", ".md"])
    documents = reader.load_data()
    
    # Split documents into nodes
    parser = SentenceSplitter(chunk_size=512, chunk_overlap=50)
    nodes = parser.get_nodes_from_documents(documents)

    # Inject access_roles metadata into each node
    default_roles = ["all"]
    for node in nodes:
        file_name = node.metadata.get("file_name", "")
        if access_roles_map and file_name in access_roles_map:
            node.metadata["access_roles"] = access_roles_map[file_name]
        else:
            node.metadata["access_roles"] = default_roles

    tagged_count = sum(1 for n in nodes if n.metadata.get("access_roles") != default_roles)
    logger.info("Processed %d nodes (%d with custom RBAC tags)", len(nodes), tagged_count)
    
    return nodes

