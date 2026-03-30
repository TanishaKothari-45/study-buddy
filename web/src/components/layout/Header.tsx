"use client";

import { useState } from "react";
import { User, LogOut, Key } from "lucide-react";
import { ThemeToggle } from "@/components/theme-toggle";
import { Button } from "@/components/ui/button";
import { ApiKeyModal } from "@/components/layout/ApiKeyModal";
import { useAuth } from "@/context/AuthContext";
import { Select, SelectContent, SelectItem, SelectTrigger } from "@/components/ui/select";

export function Header() {
    const [isApiKeyModalOpen, setIsApiKeyModalOpen] = useState(false);
    const [selectValue, setSelectValue] = useState<string>("");
    const { user, logout, isLoading } = useAuth();

    const handleProfileAction = (value: string) => {
        if (value === "api-key") {
            setIsApiKeyModalOpen(true);
            setTimeout(() => setSelectValue(""), 100);
        } else if (value === "logout") {
            logout();
        }
    };

    const handleLoginClick = () => {
        setIsApiKeyModalOpen(true);
    };

    return (
        <>
            <header className="sticky top-0 z-30 w-full border-b border-[var(--card-border)] bg-[var(--bg)]/95 backdrop-blur-sm">
                <div className="flex h-14 items-center justify-end gap-3 px-6">
                    <ThemeToggle />

                    {!isLoading && (
                        <>
                            {user ? (
                                <Select value={selectValue} onValueChange={handleProfileAction}>
                                    <SelectTrigger className="w-auto h-9 gap-2 px-3 border-[var(--card-border)] bg-[var(--bg-secondary)] hover:bg-[var(--bg-tertiary)] text-[var(--text)] rounded-lg transition-colors duration-150 text-sm font-medium">
                                        <div className="flex items-center gap-2">
                                            <div className="h-6 w-6 rounded-full bg-amber-100 dark:bg-amber-900/40 flex items-center justify-center flex-shrink-0">
                                                <User className="h-3.5 w-3.5 text-amber-700 dark:text-amber-400" />
                                            </div>
                                            <span className="text-sm font-medium truncate max-w-[160px]">
                                                {user.full_name || user.email}
                                            </span>
                                        </div>
                                    </SelectTrigger>
                                    <SelectContent className="bg-[var(--card)] border-[var(--card-border)] z-50">
                                        <SelectItem value="info" disabled>
                                            <div className="flex flex-col space-y-0.5 py-1">
                                                <p className="text-sm font-medium leading-none text-[var(--text)]">
                                                    {user.full_name || "Account"}
                                                </p>
                                                <p className="text-xs leading-none text-[var(--text-muted)]">
                                                    {user.email}
                                                </p>
                                            </div>
                                        </SelectItem>
                                        <SelectItem value="api-key">
                                            <div className="flex items-center gap-2 text-[var(--text)]">
                                                <Key className="h-4 w-4 text-[var(--text-muted)]" />
                                                <span>Manage API key</span>
                                            </div>
                                        </SelectItem>
                                        <SelectItem value="logout">
                                            <div className="flex items-center gap-2 text-red-600 dark:text-red-400">
                                                <LogOut className="h-4 w-4" />
                                                <span>Sign out</span>
                                            </div>
                                        </SelectItem>
                                    </SelectContent>
                                </Select>
                            ) : (
                                <button
                                    onClick={handleLoginClick}
                                    title="Sign in"
                                    className="h-9 w-9 rounded-lg border border-[var(--card-border)] bg-[var(--bg-secondary)] flex items-center justify-center text-[var(--text-muted)] hover:text-[var(--accent)] hover:border-[var(--accent)] transition-all duration-150"
                                >
                                    <User className="h-4 w-4" />
                                    <span className="sr-only">Sign in</span>
                                </button>
                            )}
                        </>
                    )}
                </div>
            </header>

            <ApiKeyModal
                isOpen={isApiKeyModalOpen}
                onClose={() => setIsApiKeyModalOpen(false)}
            />
        </>
    );
}
