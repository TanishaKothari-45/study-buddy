"use client";

import React, { createContext, useContext, useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { API_URL } from "@/lib/api";
import { useMainsAnswerStore, useChatStore, useMockTestStore, useEvaluateAnswerStore } from "@/stores";
import { getReturnUrl, clearReturnUrl } from "@/lib/authHandler";

interface User {
    email: string;
    full_name?: string;
    has_gemini_api_key?: boolean;
}

interface AuthContextType {
    user: User | null;
    token: string | null;
    login: (token: string) => void;
    logout: () => void;
    isLoading: boolean;
    refreshUser: () => Promise<void>;
    verifyApiKey: () => Promise<boolean>;
    isApiKeyValid: 'unknown' | 'valid' | 'invalid';
    setIsApiKeyValid: (valid: 'unknown' | 'valid' | 'invalid') => void;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: React.ReactNode }) {
    const [user, setUser] = useState<User | null>(null);
    const [token, setToken] = useState<string | null>(null);
    const [isLoading, setIsLoading] = useState(true);
    const [isApiKeyValid, setIsApiKeyValid] = useState<'unknown' | 'valid' | 'invalid'>('unknown');
    const router = useRouter();

    useEffect(() => {
        // Check for token in localStorage on mount
        const storedToken = localStorage.getItem("token");
        if (storedToken) {
            setToken(storedToken);
            fetchUser(storedToken);
        } else {
            setIsLoading(false);
        }
    }, []);

    const fetchUser = async (authToken: string) => {
        try {
            const response = await fetch(`${API_URL}/auth/me`, {
                headers: {
                    Authorization: `Bearer ${authToken}`,
                },
            });

            if (response.ok) {
                const userData = await response.json();
                setUser(userData);

                // Proactively verify API key if it exists
                if (userData.has_gemini_api_key) {
                    verifyApiKey();
                } else {
                    setIsApiKeyValid('unknown');
                }
            } else if (response.status === 401) {
                // Diagnostic logging for 401
                const errorData = await response.clone().json().catch(() => ({}));
                console.error("🚨 [AUTH_CONTEXT] 401 Unauthorized at /auth/me");
                console.error("🚨 [AUTH_CONTEXT] Response:", errorData);

                // Only logout on explicit 401 Unauthorized (token expired/invalid)
                console.log("Token invalid or expired, logging out");
                logout();
            } else {
                // Other errors (500, etc.) - keep token, just don't set user
                console.warn("Failed to fetch user, status:", response.status);
            }
        } catch (error) {
            // Network errors - keep token, user can retry
            // This prevents logout on page refresh when API is temporarily unavailable
            console.error("Network error fetching user, keeping session:", error);
        } finally {
            setIsLoading(false);
        }
    };

    const login = (newToken: string) => {
        localStorage.setItem("token", newToken);
        setToken(newToken);
        fetchUser(newToken);

        // Get return URL from session storage (defaults to /dashboard if not set or expired)
        const returnUrl = getReturnUrl();
        clearReturnUrl();

        // Clear any leftover state on login to ensure a fresh experience
        useMainsAnswerStore.getState().clear();
        useMainsAnswerStore.getState().clearHistory?.();
        useChatStore.getState().startNewChat();
        useMockTestStore.getState().resetTest();
        useEvaluateAnswerStore.getState().reset();

        router.push(returnUrl);
    };

    const logout = () => {
        localStorage.removeItem("token");
        // Clear all persisted store data on logout
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

        setToken(null);
        setUser(null);
        router.push("/login");
    };

    const refreshUser = async () => {
        if (token) {
            await fetchUser(token);
        }
    };

    const verifyApiKey = async (): Promise<boolean> => {
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

    return (
        <AuthContext.Provider value={{ user, token, login, logout, isLoading, refreshUser, verifyApiKey, isApiKeyValid, setIsApiKeyValid }}>
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
