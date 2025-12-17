/**
 * API Client - Centralized HTTP client with error handling, retry logic, and authentication
 * 
 * Features:
 * - Automatic authentication token injection
 * - Smart error message extraction from FastAPI responses
 * - Retry logic for transient failures
 * - 401 handling with redirect to login
 * - Toast notifications for errors
 * - Request/response logging
 */

import { storeReturnUrl } from './authHandler';
import { API_URL } from './api';  // Import the versioned API_URL from api.ts

// Global toast handler (set by ToastProvider)
let globalToastHandler: ((message: string, type?: 'info' | 'success' | 'warning' | 'error') => void) | null = null;

export function setGlobalToastHandler(handler: (message: string, type?: 'info' | 'success' | 'warning' | 'error') => void) {
    globalToastHandler = handler;
}

// Flag to prevent multiple simultaneous redirects
let isRedirecting = false;

/**
 * Error types for better error handling
 */
export class ApiError extends Error {
    constructor(
        message: string,
        public statusCode: number,
        public response?: Response
    ) {
        super(message);
        this.name = 'ApiError';
    }
}

export class NetworkError extends Error {
    constructor(message: string) {
        super(message);
        this.name = 'NetworkError';
    }
}

export class AuthenticationError extends ApiError {
    constructor(message: string) {
        super(message, 401);
        this.name = 'AuthenticationError';
    }
}

export class ValidationError extends ApiError {
    constructor(message: string, public errors?: unknown) {
        super(message, 422);
        this.name = 'ValidationError';
    }
}

/**
 * Clean up technical error messages for user-friendly display
 */
function cleanErrorMessage(message: string, statusCode: number): string {
    // If message already starts with "Failed to generate answer:", return as-is (already cleaned by backend)
    if (message.startsWith('Failed to generate answer:') || message.startsWith('Failed to ')) {
        return message;
    }

    // Gemini API quota errors (429)
    if (statusCode === 429) {
        if (message.includes('quota') || message.includes('Quota exceeded')) {
            return 'Failed to generate answer: You have exceeded your Gemini API quota. Please check your usage at https://aistudio.google.com/app/apikey and upgrade your plan if needed, or try again after some time.';
        }
        if (message.includes('rate limit') || message.includes('Rate limit')) {
            return 'Failed to generate answer: Too many requests to Gemini API. Please wait a few minutes and try again.';
        }
        return 'Failed to generate answer: API quota exceeded. Please check your usage and try again later.';
    }

    // Gemini API authentication errors (401, 403)
    if (statusCode === 401 || statusCode === 403) {
        if (message.includes('API key')) {
            return 'Failed to generate answer: Invalid Gemini API key. Please update your API key in Settings. You can get a new key from https://aistudio.google.com/app/apikey';
        }
        return 'Authentication failed. Please log in again or check your API key in Settings.';
    }

    // Server errors (500+)
    if (statusCode >= 500) {
        // Service unavailable
        if (statusCode === 503) {
            return 'Failed to generate answer: Service is temporarily unavailable. Please try again in a few minutes.';
        }

        // Gateway errors
        if (statusCode === 502 || statusCode === 504) {
            return 'Failed to generate answer: Gateway error occurred. Please try again in a moment.';
        }

        // Extract first sentence before technical details
        const firstSentence = message.split(/[.\n]/)[0];
        if (firstSentence && firstSentence.length < 120) {
            return `Failed to generate answer: ${firstSentence}. Please try again or contact support if the issue persists.`;
        }
        return 'Failed to generate answer: Server error occurred. Please try again or contact support if the issue persists.';
    }

    // For other errors, extract first meaningful sentence
    // Remove technical stack traces, URLs, and excessive details
    const cleanedMessage = message
        .split(/\n/)[0] // Take first line only
        .replace(/\[.*?\]/g, '') // Remove bracketed content
        .replace(/https?:\/\/[^\s]+/g, '') // Remove URLs  
        .replace(/\*\s*/g, '') // Remove bullet points
        .trim();

    // Limit length to first 150 characters
    if (cleanedMessage.length > 150) {
        const truncated = cleanedMessage.substring(0, 147);
        return truncated.substring(0, truncated.lastIndexOf(' ')) + '...';
    }

    return cleanedMessage || 'An error occurred. Please try again or contact support if the issue persists.';
}

/**
 * Extract error message from various response formats
 */
async function extractErrorMessage(response: Response): Promise<string> {
    const contentType = response.headers.get('content-type');
    let rawMessage = '';

    // Try JSON first (FastAPI standard)
    if (contentType && contentType.includes('application/json')) {
        try {
            const data = await response.json();

            // FastAPI standard error format: {"detail": "message"}
            if (data.detail) {
                // Handle both string and object detail
                if (typeof data.detail === 'string') {
                    rawMessage = data.detail;
                } else if (Array.isArray(data.detail)) {
                    // Validation errors might have array of error objects
                    rawMessage = data.detail.map((err: { msg?: string }) => err.msg || JSON.stringify(err)).join(', ');
                } else {
                    rawMessage = JSON.stringify(data.detail);
                }
            } else if (data.message) {
                rawMessage = data.message;
            } else if (data.error) {
                rawMessage = data.error;
            } else if (Object.keys(data).length > 0) {
                rawMessage = JSON.stringify(data);
            }
        } catch {
            // JSON parsing failed, fall through to text
        }
    }

    // Try plain text if no JSON message
    if (!rawMessage) {
        try {
            const text = await response.text();
            if (text && text.trim()) {
                rawMessage = text.trim();
            }
        } catch {
            // Text parsing failed
        }
    }

    // Fallback to HTTP status text
    if (!rawMessage) {
        rawMessage = `Request failed: ${response.status} ${response.statusText}`;
    }

    // Clean up the message for user display
    return cleanErrorMessage(rawMessage, response.status);
}

/**
 * Handle 401 Unauthorized errors
 */
function handle401Error() {
    if (isRedirecting) return;

    isRedirecting = true;

    // Store current path for redirect after login
    const currentPath = window.location.pathname + window.location.search;
    const excludedPaths = ['/login', '/signup', '/register', '/auth', '/forgot-password'];

    if (!excludedPaths.some(path => currentPath.startsWith(path))) {
        storeReturnUrl(currentPath);
    }

    // Show toast notification
    if (globalToastHandler) {
        globalToastHandler('Your session has expired. Redirecting to login...', 'warning');
    }

    // Clear token
    localStorage.removeItem('token');

    // Redirect after 3 seconds
    setTimeout(() => {
        window.location.href = '/login';
        // Reset flag after redirect starts
        setTimeout(() => { isRedirecting = false; }, 1000);
    }, 3000);
}

/**
 * Get authentication token from localStorage
 */
function getAuthToken(): string | null {
    if (typeof window === 'undefined') return null;
    return localStorage.getItem('token');
}

/**
 * Retry configuration
 */
interface RetryConfig {
    maxRetries: number;
    retryDelay: number; // milliseconds
    retryableStatuses: number[]; // HTTP status codes to retry
}

const DEFAULT_RETRY_CONFIG: RetryConfig = {
    maxRetries: 1,  // Only retry network errors (backend handles Gemini retries)
    retryDelay: 1000,
    retryableStatuses: [502, 503], // Only retry gateway/service unavailable (backend handles 500, Gemini handles transient errors)
};

/**
 * Sleep utility for retry delays
 */
function sleep(ms: number): Promise<void> {
    return new Promise(resolve => setTimeout(resolve, ms));
}

/**
 * API Client Options
 */
export interface ApiClientOptions extends RequestInit {
    skipAuth?: boolean; // Skip authentication header
    skipRetry?: boolean; // Skip retry logic
    skipErrorToast?: boolean; // Skip automatic error toast
    retryConfig?: Partial<RetryConfig>;
}

/**
 * Main API Client
 */
export async function apiClient<T = unknown>(
    endpoint: string,
    options: ApiClientOptions = {}
): Promise<T> {
    const {
        skipAuth = false,
        skipRetry = false,
        skipErrorToast = false,
        retryConfig = {},
        ...fetchOptions
    } = options;

    // Build full URL
    const url = endpoint.startsWith('http') ? endpoint : `${API_URL}${endpoint}`;

    // Merge retry config
    const retry = { ...DEFAULT_RETRY_CONFIG, ...retryConfig };

    // Build headers
    const headers: Record<string, string> = {};

    // Default to JSON unless body is FormData (let browser set content-type for FormData)
    if (!(fetchOptions.body instanceof FormData)) {
        headers['Content-Type'] = 'application/json';
    }

    // Merge custom headers
    if (fetchOptions.headers) {
        const customHeaders = fetchOptions.headers as Record<string, string>;
        Object.assign(headers, customHeaders);
    }

    // Add authentication token
    if (!skipAuth) {
        const token = getAuthToken();
        if (token) {
            headers['Authorization'] = `Bearer ${token}`;
        }
    }

    // Attempt request with retry logic
    let lastError: Error | null = null;
    const maxAttempts = skipRetry ? 1 : retry.maxRetries + 1;

    for (let attempt = 0; attempt < maxAttempts; attempt++) {
        try {
            // Add delay before retry (except first attempt)
            if (attempt > 0) {
                await sleep(retry.retryDelay * attempt); // Exponential backoff
            }

            // Make request
            const response = await fetch(url, {
                ...fetchOptions,
                headers,
            });

            // Handle 401 Unauthorized
            if (response.status === 401) {
                handle401Error();
                throw new AuthenticationError('Session expired. Please log in again.');
            }

            // Handle success (2xx)
            if (response.ok) {
                // Handle empty responses (204 No Content)
                if (response.status === 204) {
                    return null as T;
                }

                // Parse JSON response
                const contentType = response.headers.get('content-type');
                if (contentType && contentType.includes('application/json')) {
                    return await response.json();
                }

                // Return text for non-JSON responses
                return (await response.text()) as T;
            }

            // Check if we should retry this status code
            const shouldRetry = retry.retryableStatuses.includes(response.status) && attempt < maxAttempts - 1;

            if (shouldRetry) {
                console.warn(`Request failed with status ${response.status}, retrying... (attempt ${attempt + 1}/${maxAttempts})`);
                continue; // Retry
            }

            // Extract error message
            const errorMessage = await extractErrorMessage(response);

            // Create appropriate error type
            let error: ApiError;

            if (response.status === 422) {
                // Validation error
                try {
                    const data = await response.json();
                    error = new ValidationError(errorMessage, data.detail);
                } catch {
                    error = new ValidationError(errorMessage);
                }
            } else {
                error = new ApiError(errorMessage, response.status, response);
            }

            // Show error toast if not skipped
            if (!skipErrorToast && globalToastHandler) {
                // Choose toast type based on status code
                const toastType = response.status >= 500 ? 'error' : 'warning';
                globalToastHandler(errorMessage, toastType);
            }

            throw error;

        } catch (error) {
            // Network errors (no response received)
            if (error instanceof TypeError && error.message.includes('fetch')) {
                lastError = new NetworkError('Network error. Please check your internet connection.');

                // Retry network errors
                if (attempt < maxAttempts - 1) {
                    console.warn(`Network error, retrying... (attempt ${attempt + 1}/${maxAttempts})`);
                    continue;
                }
            } else {
                // Re-throw API errors and other errors
                throw error;
            }
        }
    }

    // All retries exhausted
    if (lastError) {
        if (!skipErrorToast && globalToastHandler) {
            globalToastHandler(lastError.message, 'error');
        }
        throw lastError;
    }

    // Should never reach here
    throw new Error('Unexpected error in API client');
}

/**
 * Convenience methods for common HTTP verbs
 */
export const api = {
    get: <T = unknown>(endpoint: string, options?: ApiClientOptions) =>
        apiClient<T>(endpoint, { ...options, method: 'GET' }),

    post: <T = unknown>(endpoint: string, data?: unknown, options?: ApiClientOptions) =>
        apiClient<T>(endpoint, {
            ...options,
            method: 'POST',
            body: data ? JSON.stringify(data) : undefined,
        }),

    put: <T = unknown>(endpoint: string, data?: unknown, options?: ApiClientOptions) =>
        apiClient<T>(endpoint, {
            ...options,
            method: 'PUT',
            body: data ? JSON.stringify(data) : undefined,
        }),

    patch: <T = unknown>(endpoint: string, data?: unknown, options?: ApiClientOptions) =>
        apiClient<T>(endpoint, {
            ...options,
            method: 'PATCH',
            body: data ? JSON.stringify(data) : undefined,
        }),

    delete: <T = unknown>(endpoint: string, options?: ApiClientOptions) =>
        apiClient<T>(endpoint, { ...options, method: 'DELETE' }),
};

/**
 * Helper to show toast messages
 */
export function showToast(message: string, type: 'info' | 'success' | 'warning' | 'error' = 'info') {
    if (globalToastHandler) {
        globalToastHandler(message, type);
    }
}

export default api;
