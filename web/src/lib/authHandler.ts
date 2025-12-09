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
    return "/dashboard";
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
export function handle401Error(currentPath?: string) {
  // Prevent multiple redirects/notifications
  if (isRedirecting) {
    return;
  }
  
  isRedirecting = true;
  
  // Store current path for return after login
  if (currentPath) {
    storeReturnUrl(currentPath);
  }

  // Show toast notification if available, otherwise fallback to console
  if (globalToastHandler) {
    globalToastHandler("Session expired, redirecting to login...", "error");
  } else {
    console.warn("Session expired, redirecting to login...");
  }
  
  // Redirect after 3 seconds
  setTimeout(() => {
    window.location.href = "/login";
  }, 3000);
}

/**
 * Custom fetch wrapper that automatically handles 401 responses
 * Use this instead of regular fetch for authenticated API calls
 */
export async function authFetch(
  input: RequestInfo | URL,
  init?: RequestInit
): Promise<Response> {
  try {
    const response = await fetch(input, init);

    // Check for 401 Unauthorized
    if (response.status === 401) {
      // Get current path from window location
      const currentPath = window.location.pathname;
      handle401Error(currentPath);
      
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
