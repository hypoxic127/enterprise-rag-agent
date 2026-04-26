import qdrant_client
from llama_index.core import VectorStoreIndex, StorageContext
from llama_index.vector_stores.qdrant import QdrantVectorStore
from app.services.document_processor import load_and_split_documents
from llama_index.core.settings import Settings
from llama_index.llms.gemini import Gemini
from llama_index.embeddings.gemini import GeminiEmbedding
from dotenv import load_dotenv
import os

load_dotenv()

# Initialize global settings
api_key = os.getenv("GOOGLE_API_KEY", "")
Settings.embed_model = GeminiEmbedding(model_name="models/gemini-embedding-001", api_key=api_key)
Settings.llm = Gemini(model="models/gemini-2.5-pro", api_key=api_key)

def get_vector_index(collection_name: str = "enterprise_rag_gemini", data_dir: str = "data"):
    # Connect to Qdrant
    qdrant_host = os.getenv("QDRANT_HOST", "localhost")
    client = qdrant_client.QdrantClient(host=qdrant_host, port=6333)
    vector_store = QdrantVectorStore(client=client, collection_name=collection_name)
    storage_context = StorageContext.from_defaults(vector_store=vector_store)
    
    # Process documents and create nodes
    nodes = load_and_split_documents(data_dir)
    
    # Create VectorStoreIndex
    index = VectorStoreIndex(
        nodes=nodes,
        storage_context=storage_context
    )
    return index
