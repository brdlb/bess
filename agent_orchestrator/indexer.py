import os
import chromadb
from chromadb.utils import embedding_functions

# Minimal script to index HOM documentation into ChromaDB
# Usage: python indexer.py /path/to/docs

DB_PATH = os.path.join(os.path.dirname(__file__), "chroma_db")
COLLECTION_NAME = "hou_docs"

def get_collection():
    client = chromadb.PersistentClient(path=DB_PATH)
    
    # Use OpenAI Embeddings if key exists, otherwise use default sentence-transformers
    openai_key = os.environ.get("OPENAI_API_KEY")
    if openai_key:
        emb_fn = embedding_functions.OpenAIEmbeddingFunction(
            api_key=openai_key,
            model_name="text-embedding-3-small"
        )
    else:
        # Default fallback (downloads a small ~80MB model)
        emb_fn = embedding_functions.DefaultEmbeddingFunction()
        
    collection = client.get_or_create_collection(
        name=COLLECTION_NAME, 
        embedding_function=emb_fn
    )
    return collection

def index_directory(docs_dir: str):
    print(f"Indexing directory: {docs_dir}")
    collection = get_collection()
    
    docs = []
    ids = []
    metadatas = []
    
    for root, _, files in os.walk(docs_dir):
        for file in files:
            if file.endswith((".md", ".txt")):
                filepath = os.path.join(root, file)
                with open(filepath, "r", encoding="utf-8") as f:
                    content = f.read()
                    
                # In a real app, we would chunk the text. Here we index the whole file.
                docs.append(content)
                ids.append(filepath)
                metadatas.append({"source": filepath, "filename": file})
                print(f"Read {file}")
                
    if docs:
        collection.upsert(
            documents=docs,
            metadatas=metadatas,
            ids=ids
        )
        print(f"Successfully indexed {len(docs)} documents into '{COLLECTION_NAME}'.")
    else:
        print("No .md or .txt files found.")

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        index_directory(sys.argv[1])
    else:
        print("Usage: python indexer.py <directory_with_md_files>")
