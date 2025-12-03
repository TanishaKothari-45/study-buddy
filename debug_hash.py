import hashlib
import json

def hash_string(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]

question = "Discuss the distribution of cotton textile industry in India"
word_count = 350
model_version = "gemini-2.5-pro-v1"

normalized_q = question.lower().strip()
composite = f"{normalized_q}|{word_count}|{model_version}"
hash_id = hash_string(composite)

print(f"Question: {normalized_q}")
print(f"Composite: {composite}")
print(f"Hash: {hash_id}")
print(f"Expected Key: study_buddy:answer:{model_version}:{hash_id}")
