# Map Rendering Fix - Technical Summary

## Problem
ReactMarkdown v10+ blocks `data:` URLs by default for security reasons, causing maps to render with empty `src` attributes.

## Root Cause
- Backend generates: `![Map Title](data:image/svg+xml;base64,PHN2Zy4uLg==)`
- ReactMarkdown v10+ sanitizes data URLs → `<img src="" alt="Map Title">`
- Browser error: "Empty string passed to src attribute"

## Solution Options Considered

### Option 1: Downgrade ReactMarkdown ❌
```json
"react-markdown": "^9.0.0"  // Older version allows data URLs
```
**Rejected because:**
- Security vulnerabilities
- Missing bug fixes
- Technical debt

### Option 2: Custom Map Component ✅ **IMPLEMENTED**
Created dedicated `Map` component that:
- Bypasses ReactMarkdown's restrictions
- Validates base64 SVG data
- Provides loading states
- Handles errors gracefully
- Allows future enhancements (zoom, pan)

## Implementation

### Files Changed
1. **Created:** `web/src/components/ui/map.tsx`
   - Dedicated Map component
   - Base64 validation
   - Error handling
   - Loading states

2. **Updated:** `web/src/components/ui/mermaid.tsx`
   - Import Map component
   - Use `<Map>` for base64 SVG images
   - Return `null` for empty src (fixes browser warning)

### Code Flow
```
Backend generates markdown:
![Title](data:image/svg+xml;base64,...)
         ↓
ReactMarkdown parses:
img({ src: "data:image/svg+xml;base64,...", alt: "Title" })
         ↓
Custom img handler detects base64:
if (src.startsWith('data:image/svg+xml;base64,'))
         ↓
Renders Map component:
<Map src={base64Data} alt={title} />
         ↓
Map component validates & displays SVG
```

## Testing
Run the integration test:
```bash
cd backend
python3 test_map_integration.py
```

Expected output:
```
✅ PASS: Health Check
✅ PASS: Direct Generation
✅ PASS: Parsing & Replacement
✅ PASS: Error Handling
```

## Next Steps
1. Start map service: `cd map-service && npm start`
2. Start backend: `cd backend && uvicorn app.main:app --reload`
3. Start frontend: `cd web && npm run dev`
4. Generate a geography answer
5. Verify maps render correctly

## Why This Approach is Better
- ✅ Security: Keeps ReactMarkdown v10+ security features
- ✅ Maintainability: Clear separation of concerns
- ✅ Extensibility: Can add zoom, pan, download later
- ✅ UX: Better error handling and loading states
- ✅ Future-proof: No technical debt
