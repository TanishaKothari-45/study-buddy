# Features Using Gemini API

This document lists all features that require a Gemini API key.

## Features Requiring User's Personal API Key

### 1. **Mains Answer Generation** (`/mains-answer`)
- **Endpoint:** `POST /api/v1/mains-answer/generate`
- **What it does:** Generates comprehensive UPSC Mains-style answers for Geography questions
- **Frontend check:** ✅ Checks API key status before starting generation
- **Backend validation:** ✅ Returns 400 error if no API key set
- **Timeout protection:** ✅ 60-second timeout on Gemini API calls

### 2. **Evaluate Answer** (`/evaluate`)
- **Endpoint:** `POST /api/v1/evaluate-answer/`
- **What it does:** OCR + evaluation of handwritten answers with improvement suggestions
- **Frontend check:** ✅ Checks API key status before starting evaluation
- **Backend validation:** ✅ Returns 400 error if no API key set
- **Timeout protection:** ✅ 60-second timeout on Gemini API calls

## Features Using System API Key (No User Key Required)

### 3. **Training Data Generation** (`/training-data`)
- **Endpoint:** `POST /api/v1/training-data/extract-answer`
- **What it does:** Extracts questions and answers from PDFs for training data
- **API Key:** Uses system `GEMINI_API_KEY` from environment variables
- **User requirement:** ❌ No user API key needed

## How API Key Validation Works

### Frontend Flow:
```
User clicks "Generate" button
    ↓
Check API key status via GET /api/v1/api-key/status
    ↓
If no API key → Show error: "Please set your Gemini API key first"
    ↓
If API key exists → Proceed with generation request
```

### Backend Flow:
```
Receive generation request
    ↓
Call get_gemini_api_key_for_request(current_user)
    ↓
If no key found → Return 400: "No Gemini API key configured"
    ↓
If key exists → Initialize GeminiClient and proceed
    ↓
Gemini API call with 60s timeout
    ↓
If timeout → Retry (max 2 retries) → Return error if all fail
```

## Error Messages

### User-Facing Errors:
- **"Please set your Gemini API key first. You'll see a banner at the top of the page."**
  - Frontend validation - shown before API call
  
- **"No Gemini API key configured. Please set your personal API key in settings to use this feature."**
  - Backend validation - shown if frontend check was bypassed

- **Timeout errors:**
  - After 60 seconds of waiting for Gemini API response
  - Retries 2 times with exponential backoff
  - Shows proper error instead of hanging forever

## API Key Banner

The `ApiKeyBanner` component shows at the top of all pages when:
- User is logged in AND
- User has not set their Gemini API key

Banner features:
- ✅ Masked input (shows `****` instead of actual key)
- ✅ Link to get free API key from Google
- ✅ Mentions it's totally free
- ✅ Encryption before sending to backend
- ✅ Success/error feedback
