"use client";

import React, { useState, useEffect } from "react";
import { Key, ExternalLink, AlertCircle, CheckCircle2, Eye, EyeOff } from "lucide-react";
import { API_URL } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { showToast } from "@/lib/authHandler";
import {
    Dialog,
    DialogContent,
    DialogHeader,
    DialogTitle,
} from "@/components/ui/dialog";

interface ApiKeyModalProps {
    isOpen: boolean;
    onClose: () => void;
    onApiKeyChange?: () => void;
}

export function ApiKeyModal({ isOpen, onClose, onApiKeyChange }: ApiKeyModalProps) {
    const { getToken, isApiKeyValid, setIsApiKeyValid, refreshUser } = useAuth();
    const [isUpdating, setIsUpdating] = useState(false);
    const [hasApiKey, setHasApiKey] = useState(false);
    const [apiKey, setApiKey] = useState("");
    const [showKey, setShowKey] = useState(false);
    const [isSaving, setIsSaving] = useState(false);
    const [isDeleting, setIsDeleting] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [success, setSuccess] = useState<string | null>(null);

    const checkApiKeyStatus = React.useCallback(async () => {
        try {
            const token = await getToken();
            if (!token) return;
            
            const response = await fetch(`${API_URL}/api-key/status`, {
                headers: { Authorization: `Bearer ${token}` },
            });

            if (response.ok) {
                const data = await response.json();
                setHasApiKey(data.has_api_key);
            }
        } catch {
            showToast("Failed to check API key status", "error");
        }
    }, [getToken]);

    useEffect(() => {
        if (isOpen) {
            checkApiKeyStatus();
        }
    }, [isOpen, checkApiKeyStatus]);

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
            const token = await getToken();
            if (!token) {
                setError("Please log in to save your API key");
                return;
            }

            const response = await fetch(`${API_URL}/api-key/set`, {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    Authorization: `Bearer ${token}`,
                },
                body: JSON.stringify({ api_key: apiKey }),
            });

            if (response.ok) {
                setHasApiKey(true);
                setIsApiKeyValid('valid');
                setApiKey("");
                setShowKey(false);
                setIsUpdating(false);
                refreshUser();
                if (onApiKeyChange) onApiKeyChange();
                // Only close if it was a fresh key setup, otherwise keep open to show success
                if (!hasApiKey) onClose();
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

    const handleDeleteApiKey = async () => {
        if (!window.confirm("Are you sure you want to delete your API key? All AI features will be disabled.")) {
            return;
        }

        setIsDeleting(true);
        setError(null);

        try {
            const token = await getToken();
            if (!token) {
                setError("Please log in to delete your API key");
                return;
            }

            const response = await fetch(`${API_URL}/api-key/delete`, {
                method: "DELETE",
                headers: { Authorization: `Bearer ${token}` },
            });

            if (response.ok) {
                setHasApiKey(false);
                setIsApiKeyValid('unknown');
                refreshUser();
                if (onApiKeyChange) onApiKeyChange();
                // Don't close, just show the set view
                setIsUpdating(false);
                setApiKey("");
            } else {
                const errorData = await response.json();
                setError(errorData.detail || "Failed to delete API key");
            }
        } catch {
            setError("Network error. Please try again.");
        } finally {
            setIsDeleting(false);
        }
    };

    if (!isOpen) return null;

    return (
        <Dialog open={isOpen} onOpenChange={onClose}>
            <DialogContent className="sm:max-w-md">
                <DialogHeader>
                    <div className="flex items-center gap-3">
                        <div className="p-2 bg-purple-500 rounded-xl">
                            <Key className="h-5 w-5 text-white" />
                        </div>
                        <DialogTitle>
                            {hasApiKey ? "Manage API Key" : "Set API Key"}
                        </DialogTitle>
                    </div>
                </DialogHeader>

                {/* Body */}
                <div className="space-y-4">
                    {hasApiKey ? (
                        <>
                            <div className="p-4 rounded-lg border border-green-200 dark:border-green-900/30">
                                <div className="flex items-center gap-2 text-green-600 dark:text-green-400">
                                    {isApiKeyValid === 'valid' ? (
                                        <>
                                            <CheckCircle2 className="h-5 w-5 shrink-0" />
                                            <span className="text-sm font-semibold">API Key is configured</span>
                                        </>
                                    ) : (
                                        <>
                                            <AlertCircle className="h-5 w-5 shrink-0 text-red-500" />
                                            <span className="text-sm font-semibold text-red-500">API Key is invalid</span>
                                        </>
                                    )}
                                </div>
                                <p className="text-sm text-green-600 dark:text-green-500 mt-2">
                                    {isApiKeyValid === 'valid' ? "All AI features are enabled and working." : "Please update your API key to enable AI features."}
                                </p>
                            </div>

                            {isUpdating ? (
                                <div className="space-y-4 animate-in fade-in slide-in-from-top-2 duration-300">
                                    <div className="space-y-2">
                                        <label className="block text-sm font-semibold">
                                            New Gemini API Key
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
                                                className="w-full px-4 py-2.5 pr-12 border border-input bg-background rounded-xl focus:ring-2 focus:ring-purple-500 focus:border-transparent font-mono text-sm"
                                            />
                                            <button
                                                onClick={() => setShowKey(!showKey)}
                                                className="absolute right-3 top-1/2 -translate-y-1/2 text-purple-600 dark:text-purple-400"
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

                                    <div className="flex gap-3">
                                        <button
                                            onClick={handleSaveApiKey}
                                            disabled={isSaving || !apiKey.trim()}
                                            className="flex-1 px-4 py-2.5 bg-purple-600 hover:bg-purple-700 disabled:bg-gray-300 text-white text-sm font-semibold rounded-xl transition-colors"
                                        >
                                            {isSaving ? "Validating..." : "Save New Key"}
                                        </button>
                                        <button
                                            onClick={() => {
                                                setIsUpdating(false);
                                                setApiKey("");
                                                setError(null);
                                            }}
                                            className="px-4 py-2.5 bg-gray-100 dark:bg-gray-800 text-sm font-semibold rounded-xl"
                                        >
                                            Cancel
                                        </button>
                                    </div>
                                </div>
                            ) : (
                                <div className="flex gap-3">
                                    <button
                                        onClick={() => setIsUpdating(true)}
                                        className="flex-1 px-4 py-2.5 bg-purple-600 hover:bg-purple-700 text-white text-sm font-semibold rounded-xl transition-colors"
                                    >
                                        Update Key
                                    </button>
                                    <button
                                        onClick={handleDeleteApiKey}
                                        disabled={isDeleting}
                                        className="flex-1 px-4 py-2.5 bg-red-600 hover:bg-red-700 disabled:bg-red-300 text-white text-sm font-semibold rounded-xl transition-colors"
                                    >
                                        {isDeleting ? "Deleting..." : "Delete Key"}
                                    </button>
                                </div>
                            )}

                            {!isUpdating && isApiKeyValid !== 'valid' && (
                                <div className="p-4 rounded-lg border border-red-200 dark:border-red-900/30">
                                    <div className="flex items-start gap-2">
                                        <AlertCircle className="h-5 w-5 text-red-400 shrink-0 mt-0.5" />
                                        <div className="text-sm">
                                            <p className="font-semibold text-red-400">Your key is invalid</p>
                                            <p className="text-red-400 mt-1">
                                                Please update your key to continue using AI features. You can get a new one from Google AI Studio.
                                            </p>
                                        </div>
                                    </div>
                                </div>
                            )}
                        </>
                    ) : (
                        <>
                            <div className="space-y-2">
                                <label className="block text-sm font-semibold">
                                    Gemini API Key
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
                                        className="w-full px-4 py-2.5 pr-12 border border-input bg-background rounded-xl focus:ring-2 focus:ring-purple-500 focus:border-transparent font-mono text-sm"
                                    />
                                    <button
                                        onClick={() => setShowKey(!showKey)}
                                        className="absolute right-3 top-1/2 -translate-y-1/2 text-purple-600 dark:text-purple-400"
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

                            <div className="p-4 rounded-lg border border-purple-100 dark:border-purple-900/30">
                                <div className="flex items-start gap-2">
                                    <AlertCircle className="h-5 w-5 text-purple-600 dark:text-purple-400 shrink-0 mt-0.5" />
                                    <div className="text-sm">
                                        <p className="font-semibold mb-1 text-purple-400">🔒 Your key is encrypted</p>
                                        <p className="text-purple-400">
                                            We encrypt your API key before storage. It&apos;s never stored in plain text.
                                        </p>
                                        <a
                                            href="https://aistudio.google.com/app/apikey"
                                            target="_blank"
                                            rel="noopener noreferrer"
                                            className="inline-flex items-center text-purple-600 dark:text-purple-300 hover:text-purple-700 dark:hover:text-purple-200 mt-2 font-semibold"
                                        >
                                            Get your free API key
                                            <ExternalLink className="h-3.5 w-3.5 ml-1" />
                                        </a>
                                    </div>
                                </div>
                            </div>

                            <button
                                onClick={handleSaveApiKey}
                                disabled={isSaving || !apiKey.trim()}
                                className="w-full px-4 py-2.5 bg-purple-600 hover:bg-purple-700 disabled:bg-gray-300 dark:disabled:bg-gray-700 text-white text-sm font-semibold rounded-xl transition-colors"
                            >
                                {isSaving ? "Saving..." : "Save API Key"}
                            </button>
                        </>
                    )}
                </div>
            </DialogContent>
        </Dialog>
    );
}
