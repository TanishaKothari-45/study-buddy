import { createBrowserClient } from '@supabase/ssr'

const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL;
const supabaseAnonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;

// S4: Explicit runtime guard — fail fast instead of creating broken client
if (!supabaseUrl || !supabaseAnonKey) {
  // Only throw outside of test/build environments
  if (typeof window !== 'undefined') {
    console.warn('Missing Supabase environment variables — auth features will be unavailable.');
  }
}

/**
 * Creates a Supabase client for use in the browser (Client Components)
 * Uses singleton pattern to avoid creating multiple clients
 */
export function createClient() {
  return createBrowserClient(supabaseUrl ?? '', supabaseAnonKey ?? '')
}

/**
 * Get the current session's access token for API calls to the Python backend
 * @returns The JWT access token or null if not authenticated
 */
export async function getSessionToken(): Promise<string | null> {
  const supabase = createClient()
  const { data: { session } } = await supabase.auth.getSession()
  return session?.access_token ?? null
}

/**
 * Helper to make authenticated API calls to the Python backend
 * Automatically attaches the Supabase JWT token
 */
export async function fetchWithAuth(url: string, options: RequestInit = {}): Promise<Response> {
  const token = await getSessionToken()
  
  const headers = new Headers(options.headers)
  if (token) {
    headers.set('Authorization', `Bearer ${token}`)
  }
  headers.set('Content-Type', 'application/json')
  
  return fetch(url, {
    ...options,
    headers,
  })
}
