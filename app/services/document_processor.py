import os
from llama_index.core import SimpleDirectoryReader
from llama_index.core.node_parser import SentenceSplitter

def load_and_split_documents(data_dir: str):
    """
    Load documents from the specified directory and split them into nodes.
    """
    if not os.path.exists(data_dir):
        os.makedirs(data_dir, exist_ok=True)
        # Create a sample document for testing
        with open(os.path.join(data_dir, "sample.txt"), "w", encoding="utf-8") as f:
            f.write("Enterprise-RAG-Agent is an intelligent legal and investment analysis system built with Python, LlamaIndex, Qdrant, and Next.js.")
            
    # Load documents
    reader = SimpleDirectoryReader(input_dir=data_dir, required_exts=[".txt", ".pdf", ".md"])
    documents = reader.load_data()
    
    # Split documents into nodes
    parser = SentenceSplitter(chunk_size=512, chunk_overlap=50)
    nodes = parser.get_nodes_from_documents(documents)
    
    return nodes
