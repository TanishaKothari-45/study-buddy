"use client";

import React, { useState, useEffect } from "react";
import { Key, ExternalLink, AlertCircle, CheckCircle2, Eye, EyeOff } from "lucide-react";
import { API_URL } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import {
    Dialog,
    DialogContent,
    DialogHeader,
    DialogTitle,
} from "@/components/ui/dialog";

// localStorage key for the API key in no-auth (India) mode
export const LOCAL_API_KEY_STORAGE_KEY = "gemini_api_key";

/** Read the stored API key from localStorage (no-auth mode). */
export function getLocalApiKey(): string | null {
    if (typeof window === "undefined") return null;
    return localStorage.getItem(LOCAL_API_KEY_STORAGE_KEY) || null;
}

/** Save the API key to localStorage (no-auth mode). */
export function setLocalApiKey(key: string) {
    localStorage.setItem(LOCAL_API_KEY_STORAGE_KEY, key);
}

/** Remove the API key from localStorage (no-auth mode). */
export function clearLocalApiKey() {
    localStorage.removeItem(LOCAL_API_KEY_STORAGE_KEY);
}

interface ApiKeyModalProps {
    isOpen: boolean;
    onClose: () => void;
    onApiKeyChange?: () => void;
}

export function ApiKeyModal({ isOpen, onClose, onApiKeyChange }: ApiKeyModalProps) {
    const { setIsApiKeyValid } = useAuth();
    const [apiKey, setApiKey] = useState("");
    const [showKey, setShowKey] = useState(false);
    const [isSaving, setIsSaving] = useState(false);
    const [isDeleting, setIsDeleting] = useState(false);
    const [hasApiKey, setHasApiKey] = useState(false);
    const [isUpdating, setIsUpdating] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [success, setSuccess] = useState<string | null>(null);

    // Check localStorage on open
    useEffect(() => {
        if (isOpen) {
            const stored = getLocalApiKey();
            setHasApiKey(!!stored);
        }
    }, [isOpen]);

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
            // Use no-auth validate endpoint — key is stored in localStorage, not server-side
            const response = await fetch(`${API_URL}/api-key/validate-no-auth`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ api_key: apiKey }),
            });

            if (response.ok) {
                // Store in localStorage for no-auth mode
                setLocalApiKey(apiKey);
                setHasApiKey(true);
                setIsApiKeyValid("valid");
                setApiKey("");
                setShowKey(false);
                setIsUpdating(false);
                if (onApiKeyChange) onApiKeyChange();
                if (!hasApiKey) onClose();
            } else {
                const errorData = await response.json();
                setError(errorData.detail || "Failed to validate API key");
            }
        } catch {
            setError("Network error. Please try again.");
        } finally {
            setIsSaving(false);
        }
    };

    const handleDeleteApiKey = () => {
        if (!window.confirm("Are you sure you want to delete your API key? All AI features will be disabled.")) {
            return;
        }
        clearLocalApiKey();
        setHasApiKey(false);
        setIsApiKeyValid("unknown");
        setIsUpdating(false);
        setApiKey("");
        if (onApiKeyChange) onApiKeyChange();
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
                                    <CheckCircle2 className="h-5 w-5 shrink-0" />
                                    <span className="text-sm font-semibold">API Key is configured</span>
                                </div>
                                <p className="text-sm text-green-600 dark:text-green-500 mt-2">
                                    All AI features are enabled and working.
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
                                        <p className="font-semibold mb-1 text-purple-400">Your key is stored locally</p>
                                        <p className="text-purple-400">
                                            Your API key is stored in your browser and sent directly with each request. It is never stored on our servers.
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
                                {isSaving ? "Validating..." : "Save API Key"}
                            </button>
                        </>
                    )}
                </div>
            </DialogContent>
        </Dialog>
    );
}
