"use client";

import React, { useState, useEffect } from "react";
import { X, Key, ExternalLink, AlertCircle, CheckCircle2, Eye, EyeOff } from "lucide-react";
import { API_URL } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { useTheme } from "next-themes";

interface ApiKeyBannerProps {
    onKeySet?: () => void;
}

export default function ApiKeyBanner({ onKeySet }: ApiKeyBannerProps) {
    const { token } = useAuth();
    const { theme, resolvedTheme } = useTheme();
    const [hasApiKey, setHasApiKey] = useState<boolean>(false);
    const [isLoading, setIsLoading] = useState(true);
    const [showInput, setShowInput] = useState(false);
    const [apiKey, setApiKey] = useState("");
    const [showKey, setShowKey] = useState(false);
    const [isSaving, setIsSaving] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [success, setSuccess] = useState<string | null>(null);
    const [showSuccessBanner, setShowSuccessBanner] = useState(false);
    const [fadeOut, setFadeOut] = useState(false);

    // Debug: Log the current theme
    useEffect(() => {
        console.log('🎨 ApiKeyBanner Theme:', { theme, resolvedTheme, isDark: document.documentElement.classList.contains('dark') });
    }, [theme, resolvedTheme]);

    useEffect(() => {
        const loadStatus = async () => {
            if (!token) {
                setIsLoading(false);
                return;
            }

            try {
                const response = await fetch(`${API_URL}/api-key/status`, {
                    headers: { Authorization: `Bearer ${token}` },
                });

                if (response.ok) {
                    const data = await response.json();
                    setHasApiKey(data.has_api_key);
                }
            } catch (error) {
                console.error("Failed to check API key status:", error);
            } finally {
                setIsLoading(false);
            }
        };

        loadStatus();
    }, [token]);

    useEffect(() => {
        if (showSuccessBanner) {
            const fadeTimer = setTimeout(() => setFadeOut(true), 2000);
            const removeTimer = setTimeout(() => {
                setShowSuccessBanner(false);
                setFadeOut(false);
            }, 2500);
            return () => {
                clearTimeout(fadeTimer);
                clearTimeout(removeTimer);
            };
        }
    }, [showSuccessBanner]);

    const handleSaveApiKey = async () => {
        if (!apiKey.trim()) {
            setError("Please enter your Gemini API key");
            return;
        }

        if (!apiKey.startsWith("AI")) {
            setError("Invalid API key format. Gemini API keys typically start with 'AI'");
            return;
        }

        setIsSaving(true);
        setError(null);
        setSuccess(null);

        try {
            const response = await fetch(`${API_URL}/api-key/set`, {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    Authorization: `Bearer ${token}`,
                },
                body: JSON.stringify({ api_key: apiKey }),
            });

            if (response.ok) {
                setSuccess("API key saved successfully! 🎉");
                setHasApiKey(true);
                setShowInput(false);
                setApiKey("");
                setShowKey(false);
                setShowSuccessBanner(true);
                if (onKeySet) onKeySet();
            } else {
                const errorData = await response.json();
                setError(errorData.detail || "Failed to save API key");
            }
        } catch {
            setError("Network error. Please try again.");
        } finally {
            setIsSaving(false);
        }
    };

    if (isLoading) return null;

    if (showSuccessBanner) {
        return (
            <div 
                className={`bg-gradient-to-r from-green-50 to-emerald-50 dark:from-green-900/20 dark:to-emerald-900/20 border-l-4 border-green-500 p-4 mb-6 rounded-lg shadow-sm transition-opacity duration-500 ${
                    fadeOut ? 'opacity-0' : 'opacity-100'
                }`}
            >
                <div className="flex items-start gap-3">
                    <CheckCircle2 className="h-6 w-6 text-green-600 dark:text-green-400 shrink-0" />
                    <div>
                        <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100 mb-1">
                            API Key Configured Successfully! 🎉
                        </h3>
                        <p className="text-sm text-gray-700 dark:text-gray-300">
                            Your Gemini API key is set and all AI features are now enabled.
                        </p>
                    </div>
                </div>
            </div>
        );
    }

    if (!hasApiKey && !showInput) {
        return (
            <div className="bg-[#F7F2FF] dark:bg-[#1A162B] border border-[#E7DAFF] dark:border-white/10 p-6 mb-6 rounded-2xl shadow-sm" style={{ backgroundColor: theme === 'dark' ? '#1A162B' : '#F7F2FF', borderColor: theme === 'dark' ? 'rgba(255,255,255,0.1)' : '#E7DAFF' }}>
                <div className="flex items-start gap-4">
                    <div className="shrink-0">
                        <div className="p-2.5 bg-purple-500 rounded-xl shadow-sm">
                            <Key className="h-5 w-5 text-white" />
                        </div>
                    </div>

                    <div className="flex-1">
                        <h3 className="text-base font-semibold text-[#2D1B4E] dark:text-[#E8DAFF] mb-2">
                            Set Up Your Gemini API Key
                        </h3>

                        <p className="text-sm text-[#3D2A62] dark:text-purple-400 mb-4 leading-relaxed" style={{ color: theme === 'dark' ? 'rgb(192, 132, 252)' : 'rgb(192, 132, 252)' }}>
                            Connect your free Gemini API key to unlock powerful AI features including chat, answer generation, question creation, and mock tests.
                        </p>

                        <div className="flex flex-wrap items-center gap-3">
                            <button
                                onClick={() => setShowInput(true)}
                                className="inline-flex items-center px-5 py-2.5 bg-purple-600 hover:bg-purple-700 text-white text-sm font-semibold rounded-xl transition-colors shadow cursor-pointer"
                            >
                                <Key className="h-4 w-4 mr-2" />
                                Configure API Key
                            </button>

                            <a
                                href="https://aistudio.google.com/app/apikey"
                                target="_blank"
                                rel="noopener noreferrer"
                                className="inline-flex items-center text-sm text-[#5A3FB5] dark:text-purple-400 hover:text-[#452ea0]"
                            >
                                Get Free API Key
                                <ExternalLink className="h-4 w-4 ml-1.5" />
                            </a>
                        </div>

                        <p className="text-sm text-[#3D2A62] dark:text-purple-300 mt-3 font-semibold" style={{ color: theme === 'dark' ? 'rgb(216, 180, 254)' : 'rgb(109, 40, 217)' }}>
                            💡 Free forever — No credit card required
                        </p>
                    </div>
                </div>
            </div>
        );
    }

    if (showInput) {
        return (
            <div className="bg-[#F7F2FF] dark:bg-[#1A162B] border border-[#E7DAFF] dark:border-white/10 p-6 mb-6 rounded-2xl shadow-sm" style={{ backgroundColor: theme === 'dark' ? '#1A162B' : '#F7F2FF', borderColor: theme === 'dark' ? 'rgba(255,255,255,0.1)' : '#E7DAFF' }}>
                <div className="flex items-start justify-between mb-5">
                    <div className="flex items-center gap-3">
                        <div className="p-2 bg-purple-500 rounded-xl shadow-sm">
                            <Key className="h-5 w-5 text-white" />
                        </div>
                        <h3 className="text-lg font-semibold text-[#3D2A62] dark:text-[#E8DAFF]">
                            Enter Your Gemini API Key
                        </h3>
                    </div>

                    <button
                        onClick={() => {
                            setShowInput(false);
                            setApiKey("");
                            setError(null);
                            setShowKey(false);
                        }}
                        className="text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-300"
                    >
                        <X className="h-5 w-5" />
                    </button>
                </div>

                <div className="space-y-4">
                    <div>
                        <label className="block text-sm font-semibold text-[#3D2A62] dark:text-purple-200 mb-2">
                            API Key
                        </label>

                        <div className="relative">
                            <input
                                type={showKey ? "text" : "password"}
                                value={apiKey}
                                onChange={(e) => {
                                    setApiKey(e.target.value);
                                    setError(null);
                                }}
                                placeholder="AIza..."
                                className="w-full px-4 py-2.5 pr-12 border border-[#DCCBFF] dark:border-purple-800 bg-[#FAF8FF] dark:bg-[#151228] text-[#2D1B4E] dark:text-gray-100 placeholder-[#9B8BC7] rounded-xl focus:ring-2 focus:ring-purple-500 focus:border-transparent font-mono text-sm"
                                style={{ backgroundColor: theme === 'dark' ? '#151228' : '#FAF8FF', borderColor: theme === 'dark' ? 'rgb(126, 58, 183)' : '#DCCBFF', color: theme === 'dark' ? 'rgb(243, 244, 246)' : '#2D1B4E' }}
                            />

                            <button
                                onClick={() => setShowKey(!showKey)}
                                className="absolute right-3 top-1/2 -translate-y-1/2 text-purple-600 dark:text-purple-300 hover:text-purple-700"
                            >
                                {showKey ? <EyeOff className="h-5 w-5" /> : <Eye className="h-5 w-5" />}
                            </button>
                        </div>
                    </div>

                    {error && (
                        <div className="flex items-center gap-2 text-sm text-red-700 dark:text-red-400 bg-red-50 dark:bg-red-900/20 p-3 rounded-lg border border-red-200 dark:border-red-900/30">
                            <AlertCircle className="h-4 w-4 shrink-0" />
                            <span>{error}</span>
                        </div>
                    )}

                    {success && (
                        <div className="flex items-center gap-2 text-sm text-green-700 dark:text-green-400 bg-green-50 dark:bg-green-900/20 p-3 rounded-lg border border-green-200 dark:border-green-900/30">
                            <CheckCircle2 className="h-4 w-4 shrink-0" />
                            <span>{success}</span>
                        </div>
                    )}

                    <div className="flex items-start gap-3 bg-[#F5F0FF] dark:bg-[#161327] p-4 rounded-xl border border-[#E7DAFF] dark:border-purple-900/40" style={{ backgroundColor: theme === 'dark' ? '#161327' : '#F5F0FF', borderColor: theme === 'dark' ? 'rgba(126, 34, 206, 0.4)' : '#E7DAFF' }}>
                        <AlertCircle className="h-5 w-5 text-purple-600 dark:text-purple-300 shrink-0" />
                        <div className="text-sm text-purple-400 dark:text-purple-100" style={{ color: theme === 'dark' ? 'rgb(216, 180, 254)' : 'rgb(192, 132, 252)' }}>
                            <p className="font-semibold mb-1.5">🔒 Your API key is encrypted and secure</p>
                            <p className="leading-relaxed">
                                We encrypt your API key before storage. It&apos;s never stored in plain text and can only be decrypted by you.
                            </p>
                            <a
                                href="https://aistudio.google.com/app/apikey"
                                target="_blank"
                                rel="noopener noreferrer"
                                className="inline-flex items-center text-[#5A3FB5] dark:text-purple-200 hover:text-[#452ea0] mt-2.5"
                                style={{ color: theme === 'dark' ? 'rgb(233, 213, 255)' : 'rgb(109, 40, 217)' }}
                            >
                                Get your free API key from Google AI Studio
                                <ExternalLink className="h-3.5 w-3.5 ml-1.5" style={{ color: theme === 'dark' ? 'rgb(233, 213, 255)' : 'rgb(109, 40, 217)' }} />
                            </a>
                        </div>
                    </div>

                    <div className="flex gap-3 pt-2">
                        <button
                            onClick={handleSaveApiKey}
                            disabled={isSaving || !apiKey.trim()}
                            className="flex-1 px-4 py-2.5 bg-purple-600 hover:bg-purple-700 disabled:bg-gray-300 dark:disabled:bg-gray-700 text-white text-sm font-semibold rounded-xl shadow transition-colors cursor-pointer"
                            style={{ backgroundColor: (isSaving || !apiKey.trim()) ? (theme === 'dark' ? 'rgb(55, 65, 81)' : 'rgb(209, 213, 219)') : undefined }}
                        >
                            {isSaving ? "Saving..." : "Save API Key"}
                        </button>

                        <button
                            onClick={() => {
                                setShowInput(false);
                                setApiKey("");
                                setError(null);
                                setShowKey(false);
                            }}
                            className="px-6 py-2.5 bg-gray-100 hover:bg-gray-200 dark:bg-gray-800 dark:hover:bg-gray-700 text-gray-700 dark:text-gray-300 text-sm font-medium rounded-lg cursor-pointer"
                            style={{ backgroundColor: theme === 'dark' ? 'rgb(31, 41, 55)' : 'rgb(243, 244, 246)', color: theme === 'dark' ? 'rgb(209, 213, 219)' : 'rgb(55, 65, 81)' }}
                        >
                            Cancel
                        </button>
                    </div>
                </div>
            </div>
        );
    }

    return null;
}
