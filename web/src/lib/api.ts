const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8001";
const API_VERSION = "v1";

// Export the full API URL for components that need direct fetch access
export const API_URL = `${API_BASE_URL}/api/${API_VERSION}`;

export async function fetchApi(endpoint: string, options: RequestInit = {}) {
  const res = await fetch(`${API_URL}${endpoint}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
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
    body: formData,
  });

  if (!res.ok) {
    const error = await res.json().catch(() => ({}));
    throw new Error(error.detail || error.message || "An error occurred");
  }

  return res.json();
}
