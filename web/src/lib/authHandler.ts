/**
 * Authentication Handler Utility
 * 
 * Provides centralized 401 error handling with automatic redirect to login.
 * Includes sessionStorage management for return URL with 30-minute expiry.
 *
 * Updated to work with Supabase Auth - uses getSessionToken() from supabase.ts
 */

import { getSessionToken } from "./supabase";
import { handle401Error } from "./apiClient"; // C4: single source of truth — no duplicate isRedirecting
import { LOCAL_GEMINI_API_KEY } from "./constants"; // C2+C3

const RETURN_URL_KEY = "returnUrl";
const RETURN_URL_TIMESTAMP_KEY = "returnUrlTimestamp";
const RETURN_URL_EXPIRY_MS = 30 * 60 * 1000; // 30 minutes

// Auth pages that should not be stored as return URLs
const AUTH_PAGES = ["/login", "/register", "/signup", "/auth"];

// Global toast notification handler (will be set by ToastProvider)
let globalToastHandler: ((message: string, type: "error" | "info" | "success" | "warning") => void) | null = null;

// C4: isRedirecting flag lives only in apiClient.ts — removed from here

export function setGlobalToastHandler(handler: typeof globalToastHandler) {
  globalToastHandler = handler;
}

/**
 * Store the current URL for return after login (excludes auth pages)
 * URL expires after 30 minutes
 */
export function storeReturnUrl(currentPath: string) {
  // Don't store auth pages as return URLs
  const isAuthPage = AUTH_PAGES.some(page => currentPath.startsWith(page));

  if (isAuthPage) {
    return;
  }

  sessionStorage.setItem(RETURN_URL_KEY, currentPath);
  sessionStorage.setItem(RETURN_URL_TIMESTAMP_KEY, Date.now().toString());
}

/**
 * Get the stored return URL if it exists and hasn't expired
 * Returns null if expired or doesn't exist, defaults to /dashboard
 */
export function getReturnUrl(): string {
  const returnUrl = sessionStorage.getItem(RETURN_URL_KEY);
  const timestamp = sessionStorage.getItem(RETURN_URL_TIMESTAMP_KEY);

  if (!returnUrl || !timestamp) {
    return "/";
  }

  // Check if URL has expired (30 minutes)
  const age = Date.now() - parseInt(timestamp, 10);
  if (age > RETURN_URL_EXPIRY_MS) {
    clearReturnUrl();
    return "/dashboard";
  }

  return returnUrl;
}

/**
 * Clear the stored return URL from sessionStorage
 */
export function clearReturnUrl() {
  sessionStorage.removeItem(RETURN_URL_KEY);
  sessionStorage.removeItem(RETURN_URL_TIMESTAMP_KEY);
}


/**
 * Custom fetch wrapper that automatically handles 401 responses
 * and automatically injects the Authorization header using Supabase session token.
 * Use this instead of regular fetch for authenticated API calls.
 */
export async function authFetch(
  input: RequestInfo | URL,
  init?: RequestInit
): Promise<Response> {
  const token = await getSessionToken();
  const authenticatedInit = { ...init };

  const headers = new Headers(init?.headers);

  if (token && !headers.has("Authorization")) {
    headers.set("Authorization", `Bearer ${token}`);
  }

  // TODO: REVERT FOR PROD — the block below injects X-Gemini-API-Key from localStorage for no-auth mode.
  // When auth is restored this can be removed; the backend will retrieve the key from the Supabase user profile.
  // No-auth India mode: inject Gemini API key from localStorage
  if (typeof window !== "undefined") {
    const localKey = localStorage.getItem(LOCAL_GEMINI_API_KEY); // C2: named constant
    if (localKey && !headers.has("X-Gemini-API-Key")) {
      headers.set("X-Gemini-API-Key", localKey);
    }
  }


  authenticatedInit.headers = headers;

  try {
    const response = await fetch(input, authenticatedInit);

    // Check for 401 Unauthorized
    if (response.status === 401) {
      const url = typeof input === 'string' ? input : (input instanceof URL ? input.toString() : 'Request object');
      await handle401Error(url, response);
      return response;
    }

    return response;
  } catch (error) {
    throw error;
  }
}


/**
 * Check if user is authenticated by checking for Supabase session token
 * Does not validate token correctness - that's done server-side
 */
export async function isAuthenticated(): Promise<boolean> {
  const token = await getSessionToken();
  return !!token;
}

/**
 * Clear authentication state (used on logout)
 */
export function clearAuthState() {
  clearReturnUrl();
  // C4: isRedirecting flag now lives in apiClient.ts — no local flag to reset
}

/**
 * Show a toast notification (convenience wrapper for global toast handler)
 * Can be used anywhere in the app after ToastProvider is initialized
 */
export function showToast(message: string, type: "error" | "info" | "success" | "warning" = "info") {
  if (globalToastHandler) {
    globalToastHandler(message, type);
  } else {
    console.warn("Toast not available:", message);
  }
}
