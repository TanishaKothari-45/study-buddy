# API Client Error Handling Guide

## Overview

We've implemented a robust, centralized API client (`/web/src/lib/apiClient.ts`) that handles all HTTP requests with built-in error handling, retry logic, authentication, and user notifications.

## Features

✅ **Automatic Error Extraction** - Parses FastAPI error responses (`detail`, `message`, `error` fields)  
✅ **Smart Retry Logic** - Retries transient failures (500, 502, 503, 504, 429, 408) with exponential backoff  
✅ **Authentication** - Auto-injects JWT tokens from localStorage  
✅ **401 Handling** - Redirects to login with return URL stored  
✅ **Toast Notifications** - Shows user-friendly error messages automatically  
✅ **TypeScript Support** - Fully typed with generics for response data  
✅ **Multiple Error Types** - `ApiError`, `NetworkError`, `AuthenticationError`, `ValidationError`

## Architecture

```
┌─────────────────┐
│   React Page    │
│  (mains-answer) │
└────────┬────────┘
         │
         │ api.post('/endpoint', data)
         ▼
┌─────────────────┐
│   apiClient     │◄─── Centralized HTTP Client
│                 │
│ • Add auth token│
│ • Make request  │
│ • Extract errors│
│ • Retry logic   │
│ • Show toasts   │
└────────┬────────┘
         │
         │ HTTPException
         ▼
┌─────────────────┐
│  FastAPI Route  │
│  (backend)      │
│                 │
│ Returns:        │
│ {"detail": "…"} │
└─────────────────┘
```

## Usage Examples

### Basic GET Request

```typescript
import api from '@/lib/apiClient';

// Simple GET - errors handled automatically
const users = await api.get('/users');

// With TypeScript typing
interface User {
  id: number;
  name: string;
  email: string;
}

const users = await api.get<User[]>('/users');
```

### POST Request with Data

```typescript
import api, { ApiError } from '@/lib/apiClient';

try {
  const result = await api.post('/mains-answer/generate', {
    question: "Discuss climate change impacts",
    word_count: 250
  });
  
  setData(result);
} catch (err) {
  // Error toast already shown automatically
  // Just handle local state
  if (err instanceof ApiError) {
    console.log('Status:', err.statusCode);
    console.log('Message:', err.message);
  }
}
```

### FormData Upload (Multipart)

```typescript
import { apiClient } from '@/lib/apiClient';

const formData = new FormData();
formData.append('file', fileBlob);
formData.append('question', 'What is this?');

const result = await apiClient('/evaluate-answer/', {
  method: 'POST',
  body: formData,
  headers: {}, // Let browser set Content-Type for multipart
});
```

### Skip Auto Error Toast

```typescript
// Useful for silent background requests
const data = await api.get('/status', {
  skipErrorToast: true
});
```

### Skip Authentication

```typescript
// For public endpoints (login, signup)
const result = await api.post('/auth/login', credentials, {
  skipAuth: true
});
```

### Custom Retry Configuration

```typescript
const data = await api.get('/unstable-endpoint', {
  retryConfig: {
    maxRetries: 5,
    retryDelay: 2000,
    retryableStatuses: [429, 500, 502, 503],
  }
});
```

### Skip Retry Logic

```typescript
// For endpoints that should fail fast
const result = await api.post('/payment', data, {
  skipRetry: true
});
```

## Error Types

### ApiError
Standard API error with status code and message.
```typescript
catch (err) {
  if (err instanceof ApiError) {
    console.log(err.statusCode); // 400, 404, 500, etc.
    console.log(err.message);    // Extracted from response
  }
}
```

### NetworkError
No response received (network offline, DNS failure, etc.)
```typescript
catch (err) {
  if (err instanceof NetworkError) {
    console.log(err.message); // "Network error. Please check your internet connection."
  }
}
```

### AuthenticationError
401 Unauthorized - triggers automatic redirect to login.
```typescript
catch (err) {
  if (err instanceof AuthenticationError) {
    // User already redirected to /login
    // Return URL stored in sessionStorage
  }
}
```

### ValidationError
422 Unprocessable Entity - FastAPI validation errors.
```typescript
catch (err) {
  if (err instanceof ValidationError) {
    console.log(err.errors); // Array of validation error objects
  }
}
```

## Backend Error Response Format

FastAPI returns errors in this format:
```json
{
  "detail": "You have exceeded your Gemini API quota. Please check your API key limits or try again later."
}
```

The API client automatically extracts `detail`, `message`, or `error` fields and shows them to the user.

## Migration Guide

### Before (Old Pattern)
```typescript
// ❌ Manual error handling everywhere
try {
  const res = await fetch(`${API_URL}/endpoint`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${token}`
    },
    body: JSON.stringify(data)
  });
  
  if (!res.ok) {
    const errData = await res.json().catch(() => ({}));
    const errorMessage = errData.detail || "Request failed";
    throw new Error(errorMessage);
  }
  
  const result = await res.json();
  setData(result);
} catch (err) {
  setError(err instanceof Error ? err.message : "Unknown error");
  showToast(err.message, 'error');
}
```

### After (New Pattern)
```typescript
// ✅ Clean, centralized error handling
try {
  const result = await api.post('/endpoint', data);
  setData(result);
} catch (err) {
  // Error toast already shown
  if (err instanceof ApiError) {
    setError(err.message);
  }
}
```

## Converted Files

### ✅ Fully Migrated
- `/web/src/app/mains-answer/page.tsx` - Uses `api.post()` for answer generation
- `/web/src/app/evaluate/page.tsx` - Uses `apiClient()` for FormData upload

### 🔄 To Be Migrated
- `/web/src/app/mock-test/page.tsx`
- `/web/src/app/chat/page.tsx`
- `/web/src/app/training-data/page.tsx`
- `/web/src/components/layout/ApiKeyModal.tsx`
- `/web/src/components/layout/DeleteApiKeyModal.tsx`

## Configuration

API client reads from environment variables:
```bash
NEXT_PUBLIC_API_URL=http://localhost:8000/api/v1
```

## Testing Error Scenarios

### Test Quota Error (429)
```bash
# Backend should return:
{"detail": "You have exceeded your Gemini API quota..."}

# User sees toast: "You have exceeded your Gemini API quota..."
# No generic "Failed to generate answer"
```

### Test Invalid API Key
```bash
# Backend should return:
{"detail": "Invalid Gemini API key. Please check your API key in settings."}

# User sees proper error message
# API key banner appears
```

### Test Network Error
```bash
# Disconnect internet
# User sees: "Network error. Please check your internet connection."
# Request retries 2 times before failing
```

### Test 401 Session Expiry
```bash
# Backend returns 401
# User sees: "Your session has expired. Redirecting to login..."
# Redirects after 3 seconds
# Current page stored as return URL
```

## Best Practices

1. **Always use typed responses**
   ```typescript
   interface MyResponse { id: number; name: string }
   const data = await api.get<MyResponse>('/endpoint');
   ```

2. **Handle errors locally only for UI state**
   ```typescript
   try {
     const data = await api.post('/endpoint', payload);
     setResult(data);
   } catch (err) {
     // Toast already shown - just update local state
     setLoading(false);
   }
   ```

3. **Use specific error types when needed**
   ```typescript
   catch (err) {
     if (err instanceof ApiError && err.statusCode === 429) {
       setShowRateLimitWarning(true);
     }
   }
   ```

4. **Skip auto-toast for background requests**
   ```typescript
   const status = await api.get('/health', { skipErrorToast: true });
   ```

5. **Use FormData correctly**
   ```typescript
   // ✅ Correct - empty headers
   await apiClient('/upload', { method: 'POST', body: formData, headers: {} });
   
   // ❌ Wrong - Content-Type conflicts with multipart
   await apiClient('/upload', { method: 'POST', body: formData });
   ```

## Troubleshooting

### "Error toast not showing"
**Solution:** Make sure `ClientWrapper` calls `setGlobalToastHandler()` in useEffect:
```typescript
React.useEffect(() => {
  setApiToastHandler(addToast);
}, [addToast]);
```

### "Still seeing generic error messages"
**Solution:** Check backend is raising `HTTPException` with proper `detail`:
```python
raise HTTPException(
    status_code=429,
    detail="You have exceeded your Gemini API quota..."
)
```

### "401 redirect not working"
**Solution:** Verify `handle401Error()` is called and `isRedirecting` flag is managed properly.

### "Retry not working"
**Solution:** Check status code is in `retryableStatuses` array (408, 429, 500, 502, 503, 504).

## Summary

The new API client provides:
- **Developer Experience:** Less boilerplate, cleaner code
- **User Experience:** Proper error messages, automatic retries, seamless auth flow
- **Maintainability:** Centralized logic, easier to debug and extend
- **Type Safety:** Full TypeScript support with generics

All HTTP errors now display the actual backend error message instead of generic "Failed to generate answer" messages.
