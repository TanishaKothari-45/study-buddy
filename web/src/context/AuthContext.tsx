"use client";

import React, { createContext, useContext, useState, useEffect, useRef } from "react";
import { useRouter } from "next/navigation";
import { createClient, getSessionToken } from "@/lib/supabase";
import { API_URL } from "@/lib/api";
import { useMainsAnswerStore, useChatStore, useMockTestStore, useEvaluateAnswerStore } from "@/stores";
import { getReturnUrl, clearReturnUrl } from "@/lib/authHandler";
import type { User as SupabaseUser, Session } from "@supabase/supabase-js";

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
    refreshUser: () => Promise<void>;
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
    const [isApiKeyValid, setIsApiKeyValid] = useState<'unknown' | 'valid' | 'invalid'>('unknown');
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
                setSession(newSession);
                
                if (event === 'SIGNED_IN' && newSession) {
                    // Check if this is a duplicate SIGNED_IN event for the same user
                    // (happens on tab focus due to Supabase's visibility detection)
                    const isAlreadyHandled = handledUserIdRef.current === newSession.user.id;
                    
                    if (isAlreadyHandled) return;
                    
                    // Mark this user as handled
                    handledUserIdRef.current = newSession.user.id;
                    
                    await fetchUserProfile(newSession.user, newSession.access_token);
                    
                    // Get return URL and redirect
                    const returnUrl = getReturnUrl();
                    clearReturnUrl();
                    
                    // Clear stores on new login
                    useMainsAnswerStore.getState().clear();
                    useMainsAnswerStore.getState().clearHistory?.();
                    useChatStore.getState().startNewChat();
                    useMockTestStore.getState().resetTest();
                    useEvaluateAnswerStore.getState().reset();
                    
                    router.push(returnUrl);
                } else if (event === 'SIGNED_OUT') {
                    setUser(null);
                    setIsApiKeyValid('unknown');
                    // Reset the handled user so next sign-in is processed
                    handledUserIdRef.current = null;
                }
            }
        );

        return () => {
            subscription.unsubscribe();
        };
    }, []);

    const fetchUserProfile = async (supabaseUser: SupabaseUser, token: string) => {
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

                // Verify API key if exists
                if (profileData.has_gemini_api_key) {
                    verifyApiKey();
                } else {
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
        // Clear all persisted store data
        localStorage.removeItem("geography-mains-answer-storage");
        localStorage.removeItem("geography-mock-test-storage");
        localStorage.removeItem("geography-chat-storage");
        localStorage.removeItem("geography-evaluate-answer-storage");

        // Reset stores to initial state
        useMainsAnswerStore.getState().clear();
        useMainsAnswerStore.getState().clearHistory();
        useChatStore.getState().startNewChat();
        useMockTestStore.getState().resetTest();
        useEvaluateAnswerStore.getState().reset();

        await supabase.auth.signOut();
        setUser(null);
        setSession(null);
        router.push("/login");
    };

    const refreshUser = async () => {
        const { data: { session: currentSession } } = await supabase.auth.getSession();
        if (currentSession?.user) {
            await fetchUserProfile(currentSession.user, currentSession.access_token);
        }
    };

    const verifyApiKey = async (): Promise<boolean> => {
        const token = await getSessionToken();
        if (!token) return false;
        
        try {
            const response = await fetch(`${API_URL}/api-key/verify`, {
                headers: {
                    Authorization: `Bearer ${token}`,
                },
            });

            if (response.ok) {
                setIsApiKeyValid('valid');
                return true;
            } else {
                setIsApiKeyValid('invalid');
                return false;
            }
        } catch (error) {
            console.error("Failed to verify API key:", error);
            return false;
        }
    };

    const getToken = async (): Promise<string | null> => {
        return getSessionToken();
    };

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
