import os
import shutil
import subprocess
import sys

# Configuration
HOUDINI_HELP_DIR = r"C:/Program Files/Side Effects Software/Houdini 20.5.584/houdini/help"
ZIPS_TO_INDEX = ["nodes.zip", "hom.zip", "vex.zip", "basics.zip"]
DB_DIR = "chroma_db"
PYTHON_EXE = r"venv/Scripts/python.exe"

def main():
    if os.path.exists(DB_DIR):
        print(f"Removing existing database at {DB_DIR}...")
        shutil.rmtree(DB_DIR)
    
    for zip_name in ZIPS_TO_INDEX:
        zip_path = os.path.join(HOUDINI_HELP_DIR, zip_name)
        if not os.path.exists(zip_path):
            print(f"Warning: {zip_path} not found. Skipping.")
            continue
            
        print(f"\n--- Indexing {zip_name} ---")
        result = subprocess.run([PYTHON_EXE, "indexer.py", zip_path], capture_output=True, text=True)
        if result.returncode == 0:
            print(f"Successfully indexed {zip_name}")
        else:
            print(f"Failed to index {zip_name}")
            print(result.stdout)
            print(result.stderr)

if __name__ == "__main__":
    main()
