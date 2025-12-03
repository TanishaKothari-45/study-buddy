# Zustand Store Architecture

This folder contains Zustand stores for state management with localStorage persistence across the application.

## Structure

```
stores/
├── index.ts              # Re-exports all stores and utilities
├── types.ts              # Shared types across stores
├── useHydration.ts       # Hydration utility for Next.js SSR
├── geography/            # Geography subject stores
│   ├── mainsAnswerStore.ts
│   ├── mockTestStore.ts
│   └── chatStore.ts
├── common/               # Shared stores (future)
│   └── uiStore.ts        # UI state (modals, notifications)
└── [future-subject]/     # Easy to add more subjects
```

## Usage

### Basic Store Usage

```typescript
import { useMainsAnswerStore } from '@/stores';

function MyComponent() {
  const { result, loading, generateAnswer } = useMainsAnswerStore();
  // ...
}
```

### Handling Hydration (Recommended for SSR)

To prevent hydration mismatches in Next.js:

```typescript
import { useMockTestStore, useHydration } from '@/stores';

function MyComponent() {
  const hasHydrated = useHydration();
  const store = useMockTestStore();
  
  // Show loading state during hydration
  if (!hasHydrated) {
    return <div>Loading...</div>;
  }
  
  // Now safe to use persisted state
  return <div>{store.testData ? 'Has data' : 'No data'}</div>;
}
```

## Persistence Strategy

### What We Persist
- **Mock Test Store**: Test data, user answers, scores, job state (for resume)
- **Mains Answer Store**: Generated answers and sources
- **Chat Store**: Last 50 messages and session ID

### What We DON'T Persist
- Loading states
- Form inputs (question text, word count)
- Error messages
- UI state (modals, tooltips)

This keeps localStorage lean and prevents stale UI states.

## Why Zustand?

- ✅ Minimal boilerplate
- ✅ No providers needed
- ✅ Works outside React components
- ✅ Easy async handling
- ✅ Built-in persist middleware
- ✅ Scales well for multi-subject architecture
- ✅ TypeScript-first design
- ✅ Tiny bundle size (~1KB)

## Storage Keys

- `geography-mock-test-storage`: Mock test state
- `geography-mains-answer-storage`: Mains answer results
- `geography-chat-storage`: Chat messages and session

## Best Practices

1. **Keep stores focused**: One store per feature/page
2. **Partition wisely**: Only persist what needs to survive page refreshes
3. **Limit chat history**: We keep last 50 messages to prevent localStorage bloat
4. **Use ISO strings for dates**: Dates don't serialize well in JSON
5. **Handle hydration**: Use `useHydration()` hook for SSR-safe components
6. **Clear on logout**: Remember to clear sensitive data when user logs out

## Future Enhancements

- [ ] Add `common/uiStore.ts` for global UI state (theme, notifications)
- [ ] Add store devtools integration for debugging
- [ ] Implement store reset on user logout
- [ ] Add versioning/migration for breaking schema changes
- [ ] Consider IndexedDB for larger datasets (if needed)
