
import os
import chromadb
from indexer import get_collection

def test_chroma():
    print(f"Testing ChromaDB at: {os.path.abspath('chroma_db')}")
    try:
        collection = get_collection()
        count = collection.count()
        print(f"Collection '{collection.name}' contains {count} documents.")
        
        if count > 0:
            print("\nSampling first 2 records:")
            sample = collection.get(limit=2)
            for i in range(len(sample['ids'])):
                print(f"ID: {sample['ids'][i]}")
                print(f"Source: {sample['metadatas'][i].get('source')}")
                print(f"Chunk Preview: {sample['documents'][i][:100]}...")
            
            query = "how to create a node"
            print(f"\nQuerying: '{query}'")
            results = collection.query(query_texts=[query], n_results=3)
            print("Top Results:")
            for i, doc in enumerate(results['documents'][0]):
                meta = results['metadatas'][0][i]
                print(f"{i+1}. Source: {meta.get('source')}")
                print(f"   Snippet: {doc[:150]}...\n")
        else:
            print("Collection is empty. Use indexer.py to add documents.")
    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    test_chroma()
