import os
import chromadb
import re
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

def clean_wiki_text(text: str) -> str:
    """Removes or simplifies Houdini Help Wiki markup."""
    # Convert [[Link|Label]] or [[Link]] to Label
    text = re.sub(r'\[\[([^\]|]+\|)?([^\]]+)\]\]', r'\2', text)
    # Convert [Link|Label] or [Link] to Label
    text = re.sub(r'\[([^\]|]+\|)?([^\]]+)\]', r'\2', text)
    # Remove #tag: value lines
    text = re.sub(r'^#[a-z]+:.*$', '', text, flags=re.MULTILINE)
    # Simplify python method signatures ::method -> method
    text = re.sub(r'^::', '', text, flags=re.MULTILINE)
    # Remove excessive empty lines
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()

def get_breadcrumb(filepath: str, internal_path: str = None) -> str:
    """Generates a breadcrumb from the file path."""
    path = internal_path if internal_path else filepath
    # Convert C:/Path/To/Zip.zip::sop/null.txt to Nodes > SOP > null
    if "::" in path:
        parts = path.split("::")[-1].split("/")
    else:
        parts = path.replace("\\", "/").split("/")[-3:]
    
    clean_parts = [p.replace(".txt", "").replace(".md", "").capitalize() for p in parts if p]
    return " > ".join(clean_parts)

from langchain_text_splitters import RecursiveCharacterTextSplitter

import zipfile

def process_content_chunks(content, filepath, file, text_splitter, docs, ids, metadatas):
    breadcrumb = get_breadcrumb(filepath)
    clean_content = clean_wiki_text(content)
    
    # Prepend breadcrumb to improve semantic search context
    contextualized_content = f"Context: {breadcrumb}\n\n{clean_content}"
    
    chunks = text_splitter.split_text(contextualized_content)
    for i, chunk in enumerate(chunks):
        docs.append(chunk)
        ids.append(f"{filepath}_chunk_{i}")
        metadatas.append({
            "source": filepath, 
            "filename": file,
            "chunk_index": i,
            "breadcrumb": breadcrumb
        })
    return len(chunks)

def index_directory(docs_dir: str):
    print(f"Indexing target: {docs_dir}")
    collection = get_collection()
    
    docs = []
    ids = []
    metadatas = []
    
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=200,
        length_function=len,
        add_start_index=True,
    )
    
    if os.path.isfile(docs_dir):
        # Handle the case where the user passes a direct path to a file (e.g., a .zip)
        walk_generator = [(os.path.dirname(docs_dir), [], [os.path.basename(docs_dir)])]
    else:
        walk_generator = os.walk(docs_dir)
    
    for root, _, files in walk_generator:
        for file in files:
            filepath = os.path.join(root, file)
            
            # Handle standard text files
            if file.endswith((".md", ".txt")):
                try:
                    with open(filepath, "r", encoding="utf-8") as f:
                        content = f.read()
                    num_chunks = process_content_chunks(content, filepath, file, text_splitter, docs, ids, metadatas)
                    print(f"Read {file} and created {num_chunks} chunks.")
                except Exception as e:
                    print(f"Failed to read {file}: {e}")
                    
            # Handle Houdini help ZIP archives
            elif file.endswith(".zip"):
                print(f"\nProcessing ZIP archive: {file}...")
                try:
                    with zipfile.ZipFile(filepath, 'r') as z:
                        for info in z.infolist():
                            if info.filename.endswith((".md", ".txt")):
                                try:
                                    with z.open(info) as f:
                                        # Houdini docs might contain non-UTF8 characters, so we handle errors
                                        content = f.read().decode("utf-8", errors="replace")
                                    
                                    internal_path = f"{filepath}::{info.filename}"
                                    num_chunks = process_content_chunks(content, internal_path, info.filename, text_splitter, docs, ids, metadatas)
                                    # Too noisy to print every single file in the zip
                                except Exception as e:
                                    print(f"Failed to extract/read {info.filename} from {file}: {e}")
                    print(f"Finished processing ZIP: {file}")
                except Exception as e:
                    print(f"Failed to open ZIP {file}: {e}")
                
    if docs:
        print(f"\nPreparing to index {len(docs)} total chunks...")
        # Upsert in batches to avoid potential ChromaDB limits
        batch_size = 100
        total_batches = (len(docs) - 1) // batch_size + 1
        
        for i in range(0, len(docs), batch_size):
            collection.upsert(
                documents=docs[i:i+batch_size],
                metadatas=metadatas[i:i+batch_size],
                ids=ids[i:i+batch_size]
            )
            print(f"Upserted batch {i//batch_size + 1}/{total_batches}")
            
        print(f"Successfully indexed {len(docs)} total chunks into '{COLLECTION_NAME}'.")
    else:
        print("No .md or .txt files found.")

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        index_directory(sys.argv[1])
    else:
        print("Usage: python indexer.py <directory_with_md_files>")
