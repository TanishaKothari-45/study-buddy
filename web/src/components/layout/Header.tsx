"use client";

import { useState } from "react";
import { User, LogOut } from "lucide-react";
import { ThemeToggle } from "@/components/theme-toggle";
import { Button } from "@/components/ui/button";
import { AuthModal } from "@/components/layout/AuthModal";
import { useAuth } from "@/context/AuthContext";

export function Header() {
    const [isAuthModalOpen, setIsAuthModalOpen] = useState(false);
    const { user, logout, isLoading } = useAuth();

    return (
        <>
            <header className="sticky top-0 z-30 w-full border-b border-border bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
                <div className="flex h-16 items-center justify-end gap-2 px-6">
                    <ThemeToggle />
                    
                    {!isLoading && (
                        <>
                            {user ? (
                                <div className="flex items-center gap-2">
                                    <span className="text-sm text-muted-foreground hidden sm:inline">
                                        {user.full_name || user.email}
                                    </span>
                                    <Button
                                        variant="ghost"
                                        size="icon"
                                        onClick={logout}
                                        title="Logout"
                                    >
                                        <LogOut className="h-5 w-5" />
                                        <span className="sr-only">Logout</span>
                                    </Button>
                                </div>
                            ) : (
                                <Button
                                    variant="ghost"
                                    size="icon"
                                    onClick={() => setIsAuthModalOpen(true)}
                                    title="Login / Sign up"
                                >
                                    <User className="h-5 w-5" />
                                    <span className="sr-only">Login / Sign up</span>
                                </Button>
                            )}
                        </>
                    )}
                </div>
            </header>

            <AuthModal
                isOpen={isAuthModalOpen}
                onClose={() => setIsAuthModalOpen(false)}
            />
        </>
    );
}
