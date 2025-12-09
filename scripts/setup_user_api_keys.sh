#!/bin/bash

# =============================================================================
# User API Key Setup - Automated Installation Script
# =============================================================================

set -e  # Exit on any error

echo "🚀 Setting up User API Key feature..."
echo ""

# Navigate to backend directory
cd "$(dirname "$0")"
BACKEND_DIR=$(pwd)
PROJECT_ROOT=$(dirname "$BACKEND_DIR")

echo "📂 Working directory: $BACKEND_DIR"
echo ""

# =============================================================================
# STEP 1: Install Python dependencies
# =============================================================================
echo "📦 Step 1/4: Installing cryptography package..."
pip install cryptography>=41.0.0 -q
echo "✅ Dependencies installed"
echo ""

# =============================================================================
# STEP 2: Check if ENCRYPTION_KEY already exists in .env
# =============================================================================
ENV_FILE="$PROJECT_ROOT/.env"

if [ ! -f "$ENV_FILE" ]; then
    echo "⚠️  .env file not found, creating one..."
    touch "$ENV_FILE"
fi

if grep -q "^ENCRYPTION_KEY=" "$ENV_FILE"; then
    echo "✅ Step 2/4: ENCRYPTION_KEY already exists in .env"
    echo ""
else
    echo "🔐 Step 2/4: Generating new ENCRYPTION_KEY..."
    
    # Generate encryption key
    ENCRYPTION_KEY=$(python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
    
    # Add to .env file
    echo "" >> "$ENV_FILE"
    echo "# API Key Encryption (DO NOT COMMIT)" >> "$ENV_FILE"
    echo "ENCRYPTION_KEY=$ENCRYPTION_KEY" >> "$ENV_FILE"
    
    echo "✅ ENCRYPTION_KEY generated and added to .env"
    echo "   Key: $ENCRYPTION_KEY"
    echo ""
fi

# =============================================================================
# STEP 3: Run database migration
# =============================================================================
echo "🗄️  Step 3/4: Running database migration..."
python migrate_add_api_key.py
echo ""

# =============================================================================
# STEP 4: Verify setup
# =============================================================================
echo "🔍 Step 4/4: Verifying setup..."

# Check if encryption key is set
if grep -q "^ENCRYPTION_KEY=" "$ENV_FILE"; then
    echo "✅ ENCRYPTION_KEY found in .env"
else
    echo "❌ ENCRYPTION_KEY not found in .env"
    exit 1
fi

# Test encryption/decryption
python3 -c "
from app.core.encryption import get_api_key_encryptor
try:
    enc = get_api_key_encryptor()
    test_key = 'AIzaSyTestKey123'
    encrypted = enc.encrypt_api_key(test_key)
    decrypted = enc.decrypt_api_key(encrypted)
    assert test_key == decrypted, 'Encryption test failed'
    print('✅ Encryption/decryption test passed')
except Exception as e:
    print(f'❌ Encryption test failed: {e}')
    exit(1)
"

echo ""
echo "=" * 70
echo "✨ Setup Complete!"
echo "=" * 70
echo ""
echo "✅ User API Key feature is ready to use!"
echo ""
echo "📝 Next steps:"
echo "   1. Restart your backend server:"
echo "      uvicorn app.main:app --reload --port 8001"
echo ""
echo "   2. Frontend will automatically show API key banner"
echo "   3. Users can get free Gemini API keys from:"
echo "      https://aistudio.google.com/app/apikey"
echo ""
echo "🔒 Security notes:"
echo "   • ENCRYPTION_KEY is in .env (already gitignored)"
echo "   • NEVER commit .env to git"
echo "   • User API keys are encrypted in database"
echo ""
echo "📖 Full documentation: ../USER_API_KEY_SETUP.md"
echo ""
