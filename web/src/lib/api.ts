const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8001";
const API_VERSION = "v1";

// Export the full API URL for components that need direct fetch access
export const API_URL = `${API_BASE_URL}/api/${API_VERSION}`;

// TODO: REVERT FOR PROD — getLocalApiKeyHeader() and its usage below were added for no-auth India mode.
// When auth is restored, remove this function and the spread calls on lines ~19 and ~37.
// The X-Gemini-API-Key will then come from the Supabase-stored key via the backend.
/** Get the Gemini API key from localStorage (no-auth India mode). */
function getLocalApiKeyHeader(): Record<string, string> {
  if (typeof window === "undefined") return {};
  const key = localStorage.getItem("gemini_api_key");
  return key ? { "X-Gemini-API-Key": key } : {};
}

export async function fetchApi(endpoint: string, options: RequestInit = {}) {
  const res = await fetch(`${API_URL}${endpoint}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...getLocalApiKeyHeader(),
      ...options.headers,
    },
  });

  if (!res.ok) {
    const error = await res.json().catch(() => ({}));
    throw new Error(error.detail || error.message || "An error occurred");
  }

  return res.json();
}

// For FormData uploads (doesn't set Content-Type, letting browser set it with boundary)
export async function fetchApiFormData(endpoint: string, formData: FormData) {
  const res = await fetch(`${API_URL}${endpoint}`, {
    method: "POST",
    headers: {
      ...getLocalApiKeyHeader(),
    },
    body: formData,
  });

  if (!res.ok) {
    const error = await res.json().catch(() => ({}));
    throw new Error(error.detail || error.message || "An error occurred");
  }

  return res.json();
}
