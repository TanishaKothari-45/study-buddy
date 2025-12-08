"use client";

import React, { createContext, useContext, useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { API_URL } from "@/lib/api";
import { useMainsAnswerStore, useChatStore, useMockTestStore } from "@/stores";
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
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: React.ReactNode }) {
    const [user, setUser] = useState<User | null>(null);
    const [token, setToken] = useState<string | null>(null);
    const [isLoading, setIsLoading] = useState(true);
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
            } else if (response.status === 401) {
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
        
        router.push(returnUrl);
    };

    const logout = () => {
        localStorage.removeItem("token");
        // Clear all persisted store data on logout
        localStorage.removeItem("geography-mains-answer-storage");
        localStorage.removeItem("mock-test-storage");
        localStorage.removeItem("geography-chat-storage");
        
        // Reset stores to initial state
        useMainsAnswerStore.getState().clear();
        useMainsAnswerStore.getState().clearHistory();
        useChatStore.getState().startNewChat();
        
        setToken(null);
        setUser(null);
        router.push("/login");
    };

    return (
        <AuthContext.Provider value={{ user, token, login, logout, isLoading }}>
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
