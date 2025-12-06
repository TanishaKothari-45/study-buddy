"use client";

import React, { useState } from "react";
import { AlertCircle, Key, X } from "lucide-react";
import { API_URL } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";

interface DeleteApiKeyModalProps {
    isOpen: boolean;
    onClose: () => void;
    onSuccess: () => void;
}

export function DeleteApiKeyModal({ isOpen, onClose, onSuccess }: DeleteApiKeyModalProps) {
    const { token } = useAuth();
    const [isDeleting, setIsDeleting] = useState(false);
    const [error, setError] = useState<string | null>(null);

    if (!isOpen) return null;

    const handleDelete = async () => {
        setIsDeleting(true);
        setError(null);

        try {
            const response = await fetch(`${API_URL}/api-key/delete`, {
                method: "DELETE",
                headers: {
                    Authorization: `Bearer ${token}`,
                },
            });

            if (response.ok) {
                onSuccess();
                onClose();
            } else {
                const errorData = await response.json();
                setError(errorData.detail || "Failed to delete API key");
            }
        } catch (error) {
            setError("Network error. Please try again.");
            console.error("Delete API key error:", error);
        } finally {
            setIsDeleting(false);
        }
    };

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-[hsl(var(--modal-overlay))] backdrop-blur-sm">
            <div className="bg-[hsl(var(--modal-bg))] border border-[hsl(var(--card-border))] rounded-lg shadow-2xl w-full max-w-md mx-4">
                <div className="flex items-center justify-between p-6 border-b border-[hsl(var(--card-border))]">
                    <div className="flex items-center gap-3">
                        <div className="p-2 bg-red-100 dark:bg-red-900/20 rounded-full">
                            <Key className="h-5 w-5 text-red-600 dark:text-red-400" />
                        </div>
                        <h2 className="text-lg font-semibold">Delete API Key</h2>
                    </div>
                    <button
                        onClick={onClose}
                        className="text-muted-foreground hover:text-foreground transition-colors"
                    >
                        <X className="h-5 w-5" />
                    </button>
                </div>

                <div className="p-6">
                    <div className="space-y-3 mb-6">
                        <p className="text-sm font-semibold text-red-600 dark:text-red-500">
                            ⚠️ Warning: This action cannot be undone
                        </p>
                        <p className="text-sm text-muted-foreground">
                            If you delete your API key, you will lose access to all AI-powered features including:
                        </p>
                        <ul className="list-disc list-inside space-y-1.5 text-sm text-muted-foreground ml-4">
                            <li>Chat functionality</li>
                            <li>Answer generation</li>
                            <li>Question generation</li>
                            <li>Mock tests</li>
                        </ul>
                        <p className="text-sm text-muted-foreground">
                            You can always set a new API key later to regain access.
                        </p>
                    </div>

                    {error && (
                        <div className="flex items-center gap-2 text-sm text-red-600 dark:text-red-400 bg-red-50 dark:bg-red-900/20 p-3 rounded-md border border-red-200 dark:border-red-900/30">
                            <AlertCircle className="h-4 w-4 shrink-0" />
                            <span>{error}</span>
                        </div>
                    )}
                </div>

                <div className="flex items-center justify-end gap-3 p-6 border-t border-[hsl(var(--card-border))]">
                    <button
                        onClick={onClose}
                        disabled={isDeleting}
                        className="px-4 py-2 text-sm font-medium text-foreground hover:bg-accent rounded-md transition-colors disabled:opacity-50"
                    >
                        Cancel
                    </button>
                    <button
                        onClick={handleDelete}
                        disabled={isDeleting}
                        className="px-4 py-2 text-sm font-medium bg-red-600 hover:bg-red-700 text-white rounded-md transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                        {isDeleting ? "Deleting..." : "Delete API Key"}
                    </button>
                </div>
            </div>
        </div>
    );
}
