/**
 * Authentication Handler Utility
 * 
 * Provides centralized 401 error handling with automatic redirect to login.
 * Includes sessionStorage management for return URL with 30-minute expiry.
 */

const RETURN_URL_KEY = "returnUrl";
const RETURN_URL_TIMESTAMP_KEY = "returnUrlTimestamp";
const RETURN_URL_EXPIRY_MS = 30 * 60 * 1000; // 30 minutes

// Auth pages that should not be stored as return URLs
const AUTH_PAGES = ["/login", "/register", "/signup", "/auth"];

// Global toast notification handler (will be set by ToastProvider)
let globalToastHandler: ((message: string, type: "error" | "info" | "success" | "warning") => void) | null = null;

// Flag to prevent multiple session expired notifications
let isRedirecting = false;

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
 * Handle 401 Unauthorized responses
 * Shows toast notification and redirects to login after 3 seconds
 * Only triggers once to prevent multiple toast notifications
 */
/**
 * Handle 401 Unauthorized responses
 * Shows toast notification and redirects to login after 3 seconds
 * Only triggers once to prevent multiple toast notifications
 */
export async function handle401Error(url: string, response?: Response) {
  // Prevent multiple redirects/notifications
  if (isRedirecting) {
    return;
  }

  let errorMessage = "Session expired";
  let isExternalError = false;

  if (response) {
    try {
      // Clone response to read it safely
      const data = await response.clone().json();
      errorMessage = data.detail || data.message || JSON.stringify(data);

      // Heuristic for Gemini API errors
      if (errorMessage.toLowerCase().includes("api key") ||
        errorMessage.toLowerCase().includes("gemini") ||
        errorMessage.toLowerCase().includes("quota")) {
        isExternalError = true;
      }
    } catch (e) {
      console.error("Failed to parse 401 response body:", e);
    }
  }

  console.error(`🚨 [AUTH_HANDLER] 401 Unauthorized at: ${url}`);
  console.error(`🚨 [AUTH_HANDLER] Message: ${errorMessage}`);
  console.error(`🚨 [AUTH_HANDLER] External Error: ${isExternalError}`);

  // If it's an external error (e.g. invalid Gemini key), don't logout!
  if (isExternalError) {
    console.warn("⚠️ [AUTH_HANDLER] 401 identified as external error, skipping logout.");
    // Show error toast if available
    if (globalToastHandler) {
      globalToastHandler(errorMessage, "error");
    }
    return;
  }

  isRedirecting = true;

  // Store current path for return after login
  const currentPath = window.location.pathname + window.location.search;
  storeReturnUrl(currentPath);

  // Show toast notification if available, otherwise fallback to console
  if (globalToastHandler) {
    globalToastHandler("Session expired, redirecting to login...", "error");
  } else {
    console.warn("Session expired, redirecting to login...");
  }

  // Clear token
  localStorage.removeItem("token");

  // Redirect after 3 seconds
  setTimeout(() => {
    window.location.href = "/login";
    setTimeout(() => { isRedirecting = false; }, 1000);
  }, 3000);
}

/**
 * Custom fetch wrapper that automatically handles 401 responses
 * and automatically injects the Authorization header if a token exists.
 * Use this instead of regular fetch for authenticated API calls.
 */
export async function authFetch(
  input: RequestInfo | URL,
  init?: RequestInit
): Promise<Response> {
  const token = localStorage.getItem("token");
  const authenticatedInit = { ...init };

  if (token) {
    const headers = new Headers(init?.headers);
    if (!headers.has("Authorization")) {
      headers.set("Authorization", `Bearer ${token}`);
      authenticatedInit.headers = headers;
    }
  }

  try {
    const response = await fetch(input, authenticatedInit);

    // Check for 401 Unauthorized
    if (response.status === 401) {
      // Get current path from window location
      const url = typeof input === 'string' ? input : (input instanceof URL ? input.toString() : 'Request object');
      await handle401Error(url, response);

      // Return the response for caller to handle if needed
      return response;
    }

    return response;
  } catch (error) {
    // Re-throw network errors
    throw error;
  }
}

/**
 * Check if user is authenticated by validating token exists
 * Does not validate token correctness - that's done server-side
 */
export function isAuthenticated(): boolean {
  const token = localStorage.getItem("token");
  return !!token;
}

/**
 * Clear authentication state (used on logout)
 */
export function clearAuthState() {
  localStorage.removeItem("token");
  localStorage.removeItem("user");
  clearReturnUrl();
  isRedirecting = false; // Reset redirect flag
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
