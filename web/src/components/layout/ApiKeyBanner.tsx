"use client";

import React, { useState, useEffect } from "react";
import { X, Key, ExternalLink, AlertCircle, CheckCircle2, Eye, EyeOff } from "lucide-react";
import { API_URL } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { useTheme } from "next-themes";

interface ApiKeyBannerProps {
    onKeySet?: () => void;
    showBanner?: boolean;
}

export default function ApiKeyBanner({ onKeySet, showBanner = true }: ApiKeyBannerProps) {
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
    const [fadeOutSuccess, setFadeOutSuccess] = useState(false);

    // Session-based dismissal (resets on page refresh/logout)
    const [bannerDismissed, setBannerDismissed] = useState<boolean>(false);

    // Track previous hasApiKey value to detect changes
    const prevHasApiKeyRef = React.useRef(hasApiKey);

    // Track previous showBanner value to detect transitions
    const prevShowBannerRef = React.useRef(showBanner);

    // Reset dismissal only when showBanner changes from false to true (page navigation)
    useEffect(() => {
        if (showBanner && !prevShowBannerRef.current && bannerDismissed) {
            setBannerDismissed(false);
        }
        prevShowBannerRef.current = showBanner;
    }, [showBanner, bannerDismissed]);

    // Debug: log theme
    useEffect(() => {
        console.log('🎨 ApiKeyBanner Theme:', { theme, resolvedTheme, isDark: document.documentElement.classList.contains('dark') });
    }, [theme, resolvedTheme]);

    // Load API key status
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
                    const hadKey = prevHasApiKeyRef.current;
                    setHasApiKey(data.has_api_key);
                    prevHasApiKeyRef.current = data.has_api_key;
                    
                    // If API key was just added, notify parent
                    if (!hadKey && data.has_api_key && onKeySet) {
                        onKeySet();
                    }
                }
            } catch (error) {
                console.error("Failed to check API key status:", error);
            } finally {
                setIsLoading(false);
            }
        };

        loadStatus();
    }, [token, onKeySet]);

    // Success banner auto-hide - show message for 3 seconds before fading
    useEffect(() => {
        if (showSuccessBanner) {
            const fadeTimer = setTimeout(() => setFadeOutSuccess(true), 3000);
            const removeTimer = setTimeout(() => {
                setShowSuccessBanner(false);
                setFadeOutSuccess(false);
            }, 3500);
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
    
    // Don't show if showBanner prop is false (for mains/evaluate pages initially)
    if (!showBanner) return null;
    
    // Don't show if API key exists
    if (hasApiKey) return null;
    
    // Don't show if user dismissed it (session-based, resets on refresh/logout)
    if (bannerDismissed && !showInput) return null;

    // Success toast (unchanged)
    if (showSuccessBanner) {
        return (
            <div
                className={`bg-gradient-to-r from-green-50 to-emerald-50 dark:from-green-900/20 dark:to-emerald-900/20 border-l-4 border-green-500 p-3 mb-4 rounded-md shadow-sm transition-opacity duration-500 ${
                    fadeOutSuccess ? 'opacity-0' : 'opacity-100'
                }`}
            >
                <div className="flex items-start gap-3">
                    <CheckCircle2 className="h-5 w-5 text-green-600 dark:text-green-400 shrink-0" />
                    <div>
                        <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100 mb-0.5">
                            Its Okay!! You can configure it anytime from your profile.
                        </h3>
                        <p className="text-xs text-gray-700 dark:text-gray-300">
                            Your Gemini API key is set and all AI features are now enabled.
                        </p>
                    </div>
                </div>
            </div>
        );
    }

    // Determine theme colors (same values as you had)
    const lightBg = "#FBF7FF";
    const lightBorder = "#EDE6FF";
    const darkBg = "#151225";
    const darkBorder = "rgba(255,255,255,0.06)";
    const titleColorLight = "#3B2B55";
    const bodyColorLight = "#5A3FB5";
    const titleColorDark = "#EDE7FF";
    const bodyColorDark = "#D9C7FF";

    // Slim banner (or the input variant)
    if (!hasApiKey && !showInput) {
        return (
            <div
                className="mb-4 rounded-lg shadow-sm border p-3 flex items-center gap-4"
                style={{
                    backgroundColor: theme === 'dark' ? darkBg : lightBg,
                    borderColor: theme === 'dark' ? darkBorder : lightBorder,
                    alignItems: 'center'
                }}
            >
                <div style={{ flexShrink: 0 }}>
                    <div
                        style={{
                            width: 36,
                            height: 36,
                            borderRadius: 10,
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'center',
                            background: theme === 'dark' ? 'linear-gradient(180deg,#6f2ad6,#a14bf2)' : 'linear-gradient(180deg,#9b6bff,#6f2ad6)',
                            boxShadow: theme === 'dark' ? '0 1px 4px rgba(0,0,0,0.4)' : '0 1px 6px rgba(107,70,193,0.12)'
                        }}
                    >
                        <Key className="h-4 w-4 text-white" />
                    </div>
                </div>

                <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', gap: 12 }}>
                        <div style={{ minWidth: 0 }}>
                            <div style={{ fontSize: 15, fontWeight: 700, color: theme === 'dark' ? titleColorDark : titleColorLight, lineHeight: '1.05' }}>
                                Set up your Gemini API key
                            </div>
                            <div style={{ fontSize: 13, color: theme === 'dark' ? bodyColorDark : 'rgb(100, 67, 155)', marginTop: 6, opacity: 0.95 }}>
                                Connect your free Gemini API key to unlock AI features — answers, generation, and mock tests.
                            </div>
                        </div>

                        <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginLeft: 8 }}>
                            <button
                                onClick={() => setShowInput(true)}
                                className="inline-flex items-center px-3 py-1.5 rounded-md text-sm font-semibold"
                                style={{
                                    background: theme === 'dark' ? 'linear-gradient(90deg,#7B3BFF,#5C20D6)' : 'linear-gradient(90deg,#8E5CFF,#6F2AD6)',
                                    color: '#fff',
                                    border: 'none',
                                    boxShadow: theme === 'dark' ? '0 2px 8px rgba(96, 65, 189, 0.25)' : '0 2px 10px rgba(111, 42, 214, 0.12)'
                                }}
                            >
                                <Key className="h-3.5 w-3.5 mr-2" />
                                Configure
                            </button>
                        </div>
                    </div>

                    <div style={{ marginTop: 8, display: 'flex', gap: 12, alignItems: 'center' }}>
                        <a
                            href="https://aistudio.google.com/app/apikey"
                            target="_blank"
                            rel="noopener noreferrer"
                            style={{ fontSize: 13, color: theme === 'dark' ? bodyColorDark : bodyColorLight, textDecoration: 'none', fontWeight: 600 }}
                        >
                            Get free API key <ExternalLink className="inline-block ml-1" />
                        </a>

                        <div style={{ fontSize: 13, color: theme === 'dark' ? 'rgba(255,255,255,0.65)' : 'rgba(59,43,85,0.8)', fontWeight: 600 }}>
                            💡 Free forever — no credit card required
                        </div>
                    </div>
                </div>
            </div>
        );
    }

    // Input form (kept compact)
    if (showInput) {
        return (
            <div className="mb-4 rounded-lg border p-3 shadow-sm" style={{ backgroundColor: theme === 'dark' ? darkBg : lightBg, borderColor: theme === 'dark' ? darkBorder : lightBorder }}>
                <div className="flex items-center justify-between mb-3">
                    <div className="flex items-center gap-3">
                        <div style={{ width: 36, height: 36, borderRadius: 10, display: 'flex', alignItems: 'center', justifyContent: 'center', background: theme === 'dark' ? 'linear-gradient(180deg,#6f2ad6,#a14bf2)' : 'linear-gradient(180deg,#9b6bff,#6f2ad6)' }}>
                            <Key className="h-4 w-4 text-white" />
                        </div>
                        <div style={{ fontSize: 15, fontWeight: 700, color: theme === 'dark' ? '#EDE7FF' : '#3B2B55' }}>
                            Enter your Gemini API key
                        </div>
                    </div>

                    <button
                        onClick={() => {
                            setShowInput(false);
                            setApiKey("");
                            setError(null);
                            setShowKey(false);
                        }}
                        className="text-sm"
                        style={{ color: theme === 'dark' ? 'rgba(255,255,255,0.7)' : '#6B5B86' }}
                    >
                        <X className="h-4 w-4" />
                    </button>
                </div>

                <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                    <label style={{ fontSize: 13, fontWeight: 700, color: theme === 'dark' ? '#EDE7FF' : '#3B2B55' }}>API Key</label>
                    <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                        <input
                            type={showKey ? "text" : "password"}
                            value={apiKey}
                            onChange={(e) => {
                                setApiKey(e.target.value);
                                setError(null);
                            }}
                            placeholder="AIza..."
                            style={{
                                flex: 1,
                                padding: '10px 12px',
                                borderRadius: 10,
                                border: `1px solid ${theme === 'dark' ? '#4B2F78' : '#EADFFF'}`,
                                backgroundColor: theme === 'dark' ? '#0F0C16' : '#FFFFFF',
                                color: theme === 'dark' ? '#F3F4F6' : '#2D1B4E',
                                fontFamily: 'monospace',
                                fontSize: 13
                            }}
                        />
                        <button onClick={() => setShowKey(!showKey)} style={{ background: 'transparent', border: 'none', color: theme === 'dark' ? '#CDBEF8' : '#7B52D3', cursor: 'pointer' }}>
                            {showKey ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                        </button>
                    </div>

                    {error && (
                        <div style={{ padding: 8, borderRadius: 8, backgroundColor: theme === 'dark' ? 'rgba(255,0,0,0.06)' : '#FFF5F5', color: theme === 'dark' ? '#FFB4B4' : '#C53030', fontSize: 13 }}>
                            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                                <AlertCircle className="h-4 w-4" />
                                <span>{error}</span>
                            </div>
                        </div>
                    )}

                    {success && (
                        <div style={{ padding: 8, borderRadius: 8, backgroundColor: '#ECFDF5', color: '#065F46', fontSize: 13 }}>
                            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                                <CheckCircle2 className="h-4 w-4" />
                                <span>{success}</span>
                            </div>
                        </div>
                    )}

                    <div style={{ display: 'flex', gap: 8 }}>
                        <button
                            onClick={handleSaveApiKey}
                            disabled={isSaving || !apiKey.trim()}
                            style={{
                                flex: 1,
                                padding: '8px 12px',
                                borderRadius: 10,
                                background: (isSaving || !apiKey.trim())
                                    ? (theme === 'dark' ? '#374151' : '#E5E7EB')
                                    : (theme === 'dark' ? 'linear-gradient(90deg,#7B3BFF,#5C20D6)' : 'linear-gradient(90deg,#8E5CFF,#6F2AD6)'),
                                color: '#fff',
                                fontWeight: 700,
                                border: 'none',
                                cursor: isSaving || !apiKey.trim() ? 'not-allowed' : 'pointer'
                            }}
                        >
                            {isSaving ? "Saving..." : "Save"}
                        </button>

                        <button
                            onClick={() => {
                                setShowInput(false);
                                setApiKey("");
                                setError(null);
                                setShowKey(false);
                            }}
                            style={{
                                padding: '8px 12px',
                                borderRadius: 10,
                                background: theme === 'dark' ? '#0F1724' : '#F3F4F6',
                                color: theme === 'dark' ? '#E5E7EB' : '#374151',
                                border: 'none',
                                cursor: 'pointer'
                            }}
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
