#!/bin/bash

# Generate Encryption Key for API Key Storage
# This script generates a secure Fernet encryption key for encrypting user API keys

echo "🔐 Generating encryption key for API key storage..."
echo ""

# Generate the key using Python's cryptography library
ENCRYPTION_KEY=$(python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")

echo "Generated encryption key:"
echo ""
echo "ENCRYPTION_KEY=$ENCRYPTION_KEY"
echo ""
echo "⚠️  IMPORTANT SECURITY NOTICE:"
echo "1. Add this to your .env file immediately"
echo "2. NEVER commit this key to git"
echo "3. Keep this key safe - losing it means you cannot decrypt existing API keys"
echo "4. Use a different key for each environment (dev/prod)"
echo ""
echo "To add to .env file, run:"
echo "echo \"ENCRYPTION_KEY=$ENCRYPTION_KEY\" >> .env"
