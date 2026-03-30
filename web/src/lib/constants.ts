/**
 * C2 — Named constants replacing magic numbers scattered across the codebase.
 * Single source of truth for all tuneable values.
 */

/** Max messages persisted in localStorage by the chat store. */
export const CHAT_MAX_PERSISTED_MESSAGES = 50;

/** Milliseconds between job-status poll requests. */
export const POLL_INTERVAL_MS = 2000;

/** Milliseconds before retrying after a failed poll. */
export const POLL_RETRY_INTERVAL_MS = 3000;

/** Max times AuthContext will retry API-key verification before giving up. */
export const MAX_API_KEY_VERIFY_RETRIES = 2;

/** Max times ApiKeyBanner will retry /api-key/status before stopping. */
export const MAX_API_KEY_STATUS_RETRIES = 2;

// ─── Zustand Persist Keys (C3) ────────────────────────────────────────────────
/** LocalStorage key used by the mains-answer Zustand store. */
export const MAINS_ANSWER_STORE_KEY = 'geography-mains-answer-storage';

/** LocalStorage key used by the evaluate-answer Zustand store. */
export const EVALUATE_ANSWER_STORE_KEY = 'geography-evaluate-answer-storage';

/** LocalStorage key used by the mock-test Zustand store. */
export const MOCK_TEST_STORE_KEY = 'geography-mock-test-storage';

/** LocalStorage key used by the chat Zustand store. */
export const CHAT_STORE_KEY = 'geography-chat-storage';

/** LocalStorage key used for the no-auth Gemini API key. */
export const LOCAL_GEMINI_API_KEY = 'gemini_api_key';
