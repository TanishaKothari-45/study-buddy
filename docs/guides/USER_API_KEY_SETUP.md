# User-Specific Gemini API Keys Setup Guide

## 🎯 Overview

This feature allows users to provide their own Gemini API keys instead of using a shared system key. This provides:

- **User Privacy**: Each user uses their own API quota
- **Security**: API keys are encrypted before storage using Fernet (AES-128)
- **Free to Use**: Gemini API has a generous free tier
- **Easy Setup**: Simple UI for users to configure their keys

## 🚀 Backend Setup

### 1. Install Dependencies

```bash
cd backend
pip install cryptography>=41.0.0
```

### 2. Generate Encryption Key

```bash
./backend/generate_encryption_key.sh
```

This will output something like:
```
ENCRYPTION_KEY=xyz123abc456...
```

### 3. Add to .env File

Add the generated key to your `.env` file:

```bash
echo "ENCRYPTION_KEY=<your-generated-key>" >> .env
```

**⚠️ CRITICAL SECURITY:**
- NEVER commit this key to git (already in .gitignore)
- Keep it safe - losing it means you cannot decrypt existing API keys
- Use different keys for dev/prod environments

### 4. Run Database Migration

```bash
cd backend
python migrate_add_api_key.py
```

This adds the `encrypted_gemini_api_key` column to the users table.

### 5. Restart Backend Server

```bash
cd backend
uvicorn app.main:app --reload --port 8001 

# Terminal 2: Worker (Port 8002)
cd backend
python -m app.worker
```

## 🎨 Frontend Setup

No additional setup needed! The frontend automatically:
- Shows API key banner when user hasn't set their key
- Validates and encrypts API keys before sending to backend
- Masks API keys in the UI (shows `**********xyz123`)
- Provides direct link to get free Gemini API key

## 📝 How It Works

### Backend Flow

1. **User Sets API Key** (`POST /api/v1/api-key/set`)
   - Validates key format (starts with "AI")
   - Encrypts key using Fernet (AES-128 + HMAC)
   - Stores encrypted key in database
   - Never stores plain text key

2. **User Makes Request** (e.g., `/api/v1/mains-answer/generate`)
   - Backend checks if user has personal API key set
   - If yes: Decrypts and uses user's key
   - If no: Returns error asking user to set their key
   - System default key is NO LONGER used

3. **Security**
   - Keys encrypted at rest (database)
   - Keys decrypted only in memory during request
   - HMAC ensures keys haven't been tampered with
   - Encryption key never exposed to frontend

### Frontend Flow

1. **On Page Load**
   - Checks if user has API key set (`GET /api/v1/api-key/status`)
   - Shows banner if not set

2. **User Sets Key**
   - Enters key in masked input
   - Frontend validates format
   - Sends to backend for encryption
   - Backend returns masked version for display

3. **Using Features**
   - When user clicks "Generate Answer", etc.
   - Frontend sends request with auth token
   - Backend automatically uses user's API key
   - No frontend code changes needed!

## 🔒 Security Features

✅ **Encryption**: Fernet (symmetric encryption, AES-128 with HMAC)  
✅ **At Rest**: Keys encrypted in database  
✅ **In Transit**: HTTPS (in production)  
✅ **Masked Display**: Show only last 4 chars (`**********xyz123`)  
✅ **No Logs**: API keys never logged  
✅ **Gitignore**: Encryption key patterns excluded

## 🧪 Testing

### Test API Key Encryption

```python
python -c "
from backend.app.core.encryption import get_api_key_encryptor
enc = get_api_key_encryptor()

# Test encryption/decryption
original = 'AIzaSyDummyKeyForTesting123'
encrypted = enc.encrypt_api_key(original)
decrypted = enc.decrypt_api_key(encrypted)

print(f'Original:  {original}')
print(f'Encrypted: {encrypted}')
print(f'Decrypted: {decrypted}')
print(f'Match: {original == decrypted}')
print(f'Masked: {enc.mask_api_key(original)}')
"
```

### Test API Endpoints

```bash
# 1. Login
curl -X POST http://localhost:8001/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "test@example.com", "password": "password"}}'

# 2. Set API Key
curl -X POST http://localhost:8001/api/v1/api-key/set \
  -H "Authorization: Bearer <your-token>" \
  -H "Content-Type: application/json" \
  -d '{"api_key": "AIzaSyYourActualGeminiKey"}'

# 3. Check Status
curl -X GET http://localhost:8001/api/v1/api-key/status \
  -H "Authorization: Bearer <your-token>"

# 4. Delete Key
curl -X DELETE http://localhost:8001/api/v1/api-key/delete \
  -H "Authorization: Bearer <your-token>"
```

## 📚 API Endpoints

### GET /api/v1/api-key/status
Check if user has set their API key (returns masked version)

**Response:**
```json
{
  "has_api_key": true,
  "masked_key": "**********xyz123"
}
```

### POST /api/v1/api-key/set
Set or update user's Gemini API key

**Request:**
```json
{
  "api_key": "AIzaSyYourGeminiKey"
}
```

**Response:**
```json
{
  "success": true,
  "message": "API key saved successfully and encrypted",
  "masked_key": "**********Key"
}
```

### DELETE /api/v1/api-key/delete
Delete user's API key

**Response:**
```json
{
  "success": true,
  "message": "API key deleted successfully"
}
```

## 🎓 User Guide

### For End Users

1. **Get Free Gemini API Key**
   - Visit: https://aistudio.google.com/app/apikey
   - Sign in with Google account
   - Click "Create API Key"
   - Copy the key (starts with "AIza...")

2. **Set API Key in Study Buddy**
   - Login to Study Buddy
   - You'll see a banner: "Set Your Gemini API Key to Get Started"
   - Click "Set API Key"
   - Paste your key
   - Click "Save API Key"

3. **Start Using Features**
   - Generate Mains Answers
   - Evaluate Answers
   - All Gemini-powered features now work!

## 🔧 Troubleshooting

### "Invalid API key format" Error
- Gemini API keys start with "AIza"
- Copy the entire key from Google AI Studio
- Don't add quotes or spaces

### "Failed to encrypt API key" Error
- Check that `ENCRYPTION_KEY` is set in `.env`
- Restart backend server after adding `ENCRYPTION_KEY`

### "No Gemini API key available" Error
- User hasn't set their personal API key yet
- Frontend will show banner to set key

### Lost Encryption Key
- If you lose `ENCRYPTION_KEY`, existing encrypted keys cannot be decrypted
- Users will need to re-enter their API keys
- Generate new `ENCRYPTION_KEY` and run migration

## 📊 Database Schema

```sql
ALTER TABLE users ADD COLUMN encrypted_gemini_api_key TEXT;
```

The column stores the encrypted API key as base64-encoded string.

## 🎯 Migration Guide

### From System API Key to User API Keys

1. **Keep System Key** (optional fallback):
   ```python
   # In backend/app/utils/user_api_key.py
   # System key is still available as fallback
   ```

2. **Notify Users**:
   - Banner appears automatically
   - Users can set their key when ready

3. **Remove System Key** (optional):
   - Once all users have set their keys
   - Remove `GEMINI_API_KEY` from `.env`
   - Update code to make user key required

## 📦 Files Modified/Created

### Backend
- `backend/app/models/user.py` - Added `encrypted_gemini_api_key` column
- `backend/app/schemas/user.py` - Added `has_gemini_api_key` field
- `backend/app/core/encryption.py` - Encryption utilities (NEW)
- `backend/app/routes/api_key.py` - API key management endpoints (NEW)
- `backend/app/utils/user_api_key.py` - User API key helpers (NEW)
- `backend/app/routes/evaluate_answer.py` - Use user's API key
- `backend/app/routes/mains_answer.py` - Use user's API key
- `backend/migrate_add_api_key.py` - Database migration script (NEW)
- `backend/generate_encryption_key.sh` - Key generation script (NEW)

### Frontend
- `web/src/components/layout/ApiKeyBanner.tsx` - API key UI component (NEW)
- `web/src/components/layout/PageWrapper.tsx` - Page wrapper with banner (NEW)
- `web/src/context/AuthContext.tsx` - Added `has_gemini_api_key` field
- `web/src/app/page.tsx` - Uses PageWrapper with banner

### Configuration
- `.gitignore` - Added encryption key patterns
- `backend/requirements.txt` - Added cryptography package

## 🚨 Production Checklist

- [ ] Generate secure `ENCRYPTION_KEY` for production
- [ ] Add `ENCRYPTION_KEY` to production environment variables
- [ ] Run database migration in production
- [ ] Test encryption/decryption with real keys
- [ ] Monitor error logs for decryption failures
- [ ] Set up key rotation policy (optional)
- [ ] Document key backup procedure

## 📞 Support

If users have questions:
- Direct them to https://aistudio.google.com/app/apikey
- Gemini API is free with generous limits
- No credit card required for free tier

---

**Built with ❤️ for Study Buddy AI**
