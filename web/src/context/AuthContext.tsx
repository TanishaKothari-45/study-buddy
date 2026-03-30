"use client";

import React, { createContext, useContext, useState, useEffect, useRef } from "react";
import { useRouter } from "next/navigation";
import { createClient, getSessionToken } from "@/lib/supabase";
import { API_URL } from "@/lib/api";
import { useMainsAnswerStore, useChatStore, useMockTestStore, useEvaluateAnswerStore } from "@/stores";
import { getReturnUrl, clearReturnUrl } from "@/lib/authHandler";
import type { User as SupabaseUser, Session } from "@supabase/supabase-js";
import {
    MAINS_ANSWER_STORE_KEY,
    MOCK_TEST_STORE_KEY,
    CHAT_STORE_KEY,
    EVALUATE_ANSWER_STORE_KEY,
    LOCAL_GEMINI_API_KEY,
} from "@/lib/constants"; // C2+C3: named constants


interface UserProfile {
    id: string;
    email: string;
    full_name?: string;
    has_gemini_api_key?: boolean;
}

interface AuthContextType {
    user: UserProfile | null;
    session: Session | null;
    login: (email: string, password: string) => Promise<{ error: string | null }>;
    loginWithGoogle: () => Promise<void>;
    signup: (email: string, password: string, fullName?: string) => Promise<{ error: string | null }>;
    logout: () => Promise<void>;
    isLoading: boolean;
    refreshUser: (skipVerification?: boolean) => Promise<void>;
    verifyApiKey: () => Promise<boolean>;
    isApiKeyValid: 'unknown' | 'valid' | 'invalid';
    setIsApiKeyValid: (valid: 'unknown' | 'valid' | 'invalid') => void;
    getToken: () => Promise<string | null>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: React.ReactNode }) {
    const [user, setUser] = useState<UserProfile | null>(null);
    const [session, setSession] = useState<Session | null>(null);
    const [isLoading, setIsLoading] = useState(true);
    // TODO: REVERT FOR PROD — remove the localStorage seed below; restore: useState<...>('unknown')
    // No-auth India mode: seed isApiKeyValid from localStorage so UI doesn't flash 'unknown' on load
    const [isApiKeyValid, setIsApiKeyValid] = useState<'unknown' | 'valid' | 'invalid'>(() => {
        // No-auth India mode: check localStorage for a pre-saved API key
        if (typeof window !== 'undefined') {
            return localStorage.getItem('gemini_api_key') ? 'valid' : 'unknown';
        }
        return 'unknown';
    });

    const verifyRetryCountRef = useRef(0); // Track verification retry attempts
    const router = useRouter();
    const supabase = createClient();

    // Track if we've already handled the initial sign-in for the current user
    // This prevents duplicate handling when SIGNED_IN fires on tab focus
    const handledUserIdRef = useRef<string | null>(null);

    useEffect(() => {
        // Get initial session
        const initializeAuth = async () => {
            try {
                const { data: { session: initialSession } } = await supabase.auth.getSession();
                if (initialSession) {
                    setSession(initialSession);
                    // Mark this user as already handled (they were already signed in)
                    handledUserIdRef.current = initialSession.user.id;
                    await fetchUserProfile(initialSession.user, initialSession.access_token);
                }
            } catch (error) {
                console.error("Error initializing auth:", error);
            } finally {
                setIsLoading(false);
            }
        };

        initializeAuth();

        // Listen for auth state changes
        const { data: { subscription } } = supabase.auth.onAuthStateChange(
            async (event, newSession) => {
                if (event === 'SIGNED_IN' && newSession) {
                    // Check if this is a duplicate SIGNED_IN event for the same user
                    // (happens on tab focus due to Supabase's visibility detection)
                    const isAlreadyHandled = handledUserIdRef.current === newSession.user.id;

                    if (isAlreadyHandled) return;

                    // Mark this user as handled
                    handledUserIdRef.current = newSession.user.id;

                    await fetchUserProfile(newSession.user, newSession.access_token);

                    // REDIRECT DISABLED — Supabase banned in India; API key check only
                    // const returnUrl = getReturnUrl();
                    // clearReturnUrl();

                    // Clear stores on new login
                    useMainsAnswerStore.getState().clear();
                    useMainsAnswerStore.getState().clearHistory?.();
                    useChatStore.getState().startNewChat();
                    useMockTestStore.getState().resetTest();
                    useEvaluateAnswerStore.getState().reset();

                    // router.push(returnUrl);
                } else if (event === 'SIGNED_OUT') {
                    setUser(null);
                    setIsApiKeyValid('unknown');
                    // Reset the handled user so next sign-in is processed
                    handledUserIdRef.current = null;
                }
                setSession(newSession);
            }
        );

        return () => {
            subscription.unsubscribe();
        };
    }, []);

    const fetchUserProfile = async (supabaseUser: SupabaseUser, token: string, skipVerification: boolean = false) => {
        try {
            // Fetch additional user profile data from backend
            const response = await fetch(`${API_URL}/auth/me`, {
                headers: {
                    Authorization: `Bearer ${token}`,
                },
            });

            if (response.ok) {
                const profileData = await response.json();
                setUser({
                    id: supabaseUser.id,
                    email: supabaseUser.email || '',
                    full_name: profileData.full_name || supabaseUser.user_metadata?.full_name,
                    has_gemini_api_key: profileData.has_gemini_api_key,
                });

                // Verify API key if exists (reset retry counter on new login)
                // Skip verification if we just saved the key (to avoid race condition with DB propagation)
                if (profileData.has_gemini_api_key && !skipVerification) {
                    verifyRetryCountRef.current = 0; // Reset retry counter
                    verifyApiKey();
                } else if (!profileData.has_gemini_api_key) {
                    setIsApiKeyValid('unknown');
                }
            } else {
                // Still set basic user info from Supabase
                setUser({
                    id: supabaseUser.id,
                    email: supabaseUser.email || '',
                    full_name: supabaseUser.user_metadata?.full_name,
                    has_gemini_api_key: false,
                });
            }
        } catch (error) {
            console.error("Error fetching user profile:", error);
            // Set basic user info on error
            setUser({
                id: supabaseUser.id,
                email: supabaseUser.email || '',
                full_name: supabaseUser.user_metadata?.full_name,
                has_gemini_api_key: false,
            });
        }
    };

    const login = async (email: string, password: string): Promise<{ error: string | null }> => {
        try {
            const { error } = await supabase.auth.signInWithPassword({
                email,
                password,
            });

            if (error) {
                return { error: error.message };
            }

            return { error: null };
        } catch (err) {
            return { error: "Network error. Please check your connection and try again." };
        }
    };

    const loginWithGoogle = async () => {
        const { error } = await supabase.auth.signInWithOAuth({
            provider: 'google',
            options: {
                redirectTo: `${window.location.origin}/auth/callback`,
            },
        });

        if (error) {
            console.error("Google login error:", error);
        }
    };

    const signup = async (email: string, password: string, fullName?: string): Promise<{ error: string | null }> => {
        try {
            const { error } = await supabase.auth.signUp({
                email,
                password,
                options: {
                    data: {
                        full_name: fullName,
                    },
                },
            });

            if (error) {
                return { error: error.message };
            }

            return { error: null };
        } catch (err) {
            return { error: "Network error. Please check your connection and try again." };
        }
    };

    const logout = async () => {
        // Clear all persisted store data (C3: use exported constants as source of truth)
        localStorage.removeItem(MAINS_ANSWER_STORE_KEY);
        localStorage.removeItem(MOCK_TEST_STORE_KEY);
        localStorage.removeItem(CHAT_STORE_KEY);
        localStorage.removeItem(EVALUATE_ANSWER_STORE_KEY);
        localStorage.removeItem(LOCAL_GEMINI_API_KEY);


        // Reset stores to initial state
        useMainsAnswerStore.getState().clear();
        useMainsAnswerStore.getState().clearHistory();
        useChatStore.getState().startNewChat();
        useMockTestStore.getState().resetTest();
        useEvaluateAnswerStore.getState().reset();

        await supabase.auth.signOut();
        setUser(null);
        setSession(null);
        // router.push("/login"); // REDIRECT DISABLED — Supabase banned in India
    };

    const refreshUser = React.useCallback(async (skipVerification: boolean = false) => {
        const { data: { session: currentSession } } = await supabase.auth.getSession();
        if (currentSession?.user) {
            await fetchUserProfile(currentSession.user, currentSession.access_token, skipVerification);
        }
    }, [supabase.auth]);

    const verifyApiKey = React.useCallback(async (): Promise<boolean> => {
        // No-auth India mode: if a local API key exists in localStorage, treat it as valid
        if (typeof window !== 'undefined' && localStorage.getItem('gemini_api_key')) {
            setIsApiKeyValid('valid');
            return true;
        }

        const token = await getSessionToken();
        if (!token) return false;

        // Limit retries to prevent infinite loops
        if (verifyRetryCountRef.current >= 2) {
            console.warn('API key verification failed after 2 attempts, stopping');
            setIsApiKeyValid('invalid');
            return false;
        }

        verifyRetryCountRef.current += 1;

        try {
            const response = await fetch(`${API_URL}/api-key/verify`, {
                headers: {
                    Authorization: `Bearer ${token}`,
                },
            });

            if (response.ok) {
                setIsApiKeyValid('valid');
                verifyRetryCountRef.current = 0; // Reset on success
                return true;
            } else {
                setIsApiKeyValid('invalid');
                return false;
            }
        } catch (error) {
            console.error(`Failed to verify API key (attempt ${verifyRetryCountRef.current}/2):`, error);
            setIsApiKeyValid('invalid');
            return false;
        }
    }, []);


    const getToken = React.useCallback(async (): Promise<string | null> => {
        return getSessionToken();
    }, []);

    return (
        <AuthContext.Provider value={{
            user,
            session,
            login,
            loginWithGoogle,
            signup,
            logout,
            isLoading,
            refreshUser,
            verifyApiKey,
            isApiKeyValid,
            setIsApiKeyValid,
            getToken,
        }}>
            {children}
        </AuthContext.Provider>
    );
}

export function useAuth() {
    const context = useContext(AuthContext);
    if (context === undefined) {
        throw new Error("useAuth must be used within an AuthProvider");
    }
    return context;
}
