import os
import chromadb
from indexer import get_collection

def test_chroma():
    collection = get_collection()
    query = "emitter particle system node type name SOP"
    print(f"Querying: '{query}'")
    results = collection.query(query_texts=[query], n_results=5)
    for i, doc in enumerate(results['documents'][0]):
        meta = results['metadatas'][0][i]
        print(f"--- Result {i+1} --- (Source: {meta.get('source')})")
        print(doc)
        print()

if __name__ == "__main__":
    test_chroma()
