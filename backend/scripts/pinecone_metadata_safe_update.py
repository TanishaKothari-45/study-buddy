# === pinecone_metadata_safe_update.py ===

from pinecone import Pinecone
import os
from tqdm import tqdm
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
project_root = Path(__file__).resolve().parent.parent.parent
env_path = project_root / ".env"
load_dotenv(env_path)

index_name = "study-buddy"

pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))

index = pc.Index(index_name)

# Step 1: Fetch stats
stats = index.describe_index_stats()
total = stats.get('total_vector_count', 0)
dim = stats.get('dimension', 1536)

print(f"📦 Found {total} vectors in index '{index_name}' (dim={dim})")

dummy_vector = [0.0] * dim

res = index.query(vector=dummy_vector, top_k=min(total, 10000), include_metadata=True)

print(f"🔍 Retrieved {len(res['matches'])} items for patching preview → text...")

updates = []

for match in res["matches"]:
    mid = match["id"]
    meta = match.get("metadata", {})
    if not meta:
        continue
    
    if "content_preview" in meta and "text" not in meta:
        updates.append({
            "id": mid,
            "set_metadata": {"text": meta["content_preview"]}
        })

print(f"🧩 Ready to update {len(updates)} entries safely (duplicate content_preview → text).")

if updates:
    batch_size = 100
    for i in tqdm(range(0, len(updates), batch_size), desc="Updating Pinecone metadata"):
        batch = updates[i:i + batch_size]
        # Update each vector individually (Pinecone update API format)
        for update_item in batch:
            index.update(
                id=update_item["id"],
                set_metadata=update_item["set_metadata"]
            )

print("✅ Safe metadata patch complete! (content_preview duplicated as text)")

