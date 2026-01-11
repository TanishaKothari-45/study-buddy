import os
from dotenv import load_dotenv

load_dotenv()

# Try both possible env variable names
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")

if not GEMINI_API_KEY:
    print("GEMINI_API_KEY not found in environment variables")
    print("Please set GEMINI_API_KEY or GOOGLE_API_KEY in .env file")
