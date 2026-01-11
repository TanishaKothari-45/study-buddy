#!/usr/bin/env python3
"""
Test script to trigger MMR retriever and see debug logs
"""
import requests
import json

# Backend URL (adjust if different)
BACKEND_URL = "http://localhost:8000"

# Test request payload
payload = {
    "num_questions": 2,  # Small number for quick test
    "topics": [],  # Empty topics for general query
    "difficulty": "medium"
}

print("=" * 80)
print("Testing Mock Test Generation Endpoint")
print("=" * 80)
print(f"URL: {BACKEND_URL}/mock-test/generate")
print(f"Payload: {json.dumps(payload, indent=2)}")
print()

try:
    response = requests.post(
        f"{BACKEND_URL}/mock-test/generate",
        json=payload,
        headers={"Content-Type": "application/json"},
        timeout=60
    )
    
    print(f"Status Code: {response.status_code}")
    print()
    
    if response.status_code == 200:
        result = response.json()
        print("✅ Success!")
        print(f"Generated {len(result.get('questions', []))} questions")
    else:
        print("❌ Error Response:")
        print(response.text)
        
except requests.exceptions.ConnectionError:
    print("❌ Could not connect to backend!")
    print(f"   Make sure the backend is running at {BACKEND_URL}")
    print("   Start it with: cd backend && python -m uvicorn app.main:app --reload")
except Exception as e:
    print(f"❌ Error: {e}")

print()
print("=" * 80)
print("Check your backend logs for the 🔍 debug messages!")
print("Look for lines starting with:")
print("  - 🔍 Type of langchain_embeddings")
print("  - 🔍 Type of collection._embedding_function")
print("  - 🔍 Creating LangChainChroma")
print("=" * 80)


