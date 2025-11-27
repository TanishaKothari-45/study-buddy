import os
from dotenv import load_dotenv

load_dotenv()

GEMINI_API_KEY = os.getenv("GOOGLE_API_KEY")

if not GEMINI_API_KEY:
    print("GEMINI_API_KEY not found in environment variables")
    print("Please set the GEMINI_API_KEY in .env file")
