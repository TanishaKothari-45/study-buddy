"use client";

import { useState } from "react";
import { User, LogOut, Key, ChevronDown } from "lucide-react";
import { ThemeToggle } from "@/components/theme-toggle";
import { Button } from "@/components/ui/button";
import { AuthModal } from "@/components/layout/AuthModal";
import { DeleteApiKeyModal } from "@/components/layout/DeleteApiKeyModal";
import { useAuth } from "@/context/AuthContext";
import {
    DropdownMenu,
    DropdownMenuContent,
    DropdownMenuItem,
    DropdownMenuLabel,
    DropdownMenuSeparator,
    DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

export function Header() {
    const [isAuthModalOpen, setIsAuthModalOpen] = useState(false);
    const [isDeleteApiKeyModalOpen, setIsDeleteApiKeyModalOpen] = useState(false);
    const { user, logout, isLoading } = useAuth();

    const handleApiKeyDeleted = () => {
        // Refresh the page to update the API key status
        window.location.reload();
    };

    return (
        <>
            <header className="sticky top-0 z-30 w-full border-b border-border bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
                <div className="flex h-16 items-center justify-end gap-2 px-6">
                    <ThemeToggle />
                    
                    {!isLoading && (
                        <>
                            {user ? (
                                <DropdownMenu>
                                    <DropdownMenuTrigger asChild>
                                        <Button
                                            variant="ghost"
                                            className="flex items-center gap-2"
                                        >
                                            <div className="h-8 w-8 rounded-full bg-primary/10 flex items-center justify-center">
                                                <User className="h-5 w-5 text-primary" />
                                            </div>
                                            <span className="text-sm font-medium hidden sm:inline">
                                                {user.full_name || user.email}
                                            </span>
                                            <ChevronDown className="h-4 w-4 text-muted-foreground" />
                                        </Button>
                                    </DropdownMenuTrigger>
                                    <DropdownMenuContent align="end" className="w-56" style={{ zIndex: 9999 }}>
                                        <DropdownMenuLabel>
                                            <div className="flex flex-col space-y-1">
                                                <p className="text-sm font-medium leading-none">
                                                    {user.full_name || "Account"}
                                                </p>
                                                <p className="text-xs leading-none text-muted-foreground">
                                                    {user.email}
                                                </p>
                                            </div>
                                        </DropdownMenuLabel>
                                        <DropdownMenuSeparator />
                                        <DropdownMenuItem
                                            onClick={() => setIsDeleteApiKeyModalOpen(true)}
                                            className="cursor-pointer"
                                        >
                                            <Key className="mr-2 h-4 w-4" />
                                            <span>Manage API Key</span>
                                        </DropdownMenuItem>
                                        <DropdownMenuSeparator />
                                        <DropdownMenuItem
                                            onClick={logout}
                                            className="cursor-pointer text-red-600 focus:text-red-600 dark:text-red-400 dark:focus:text-red-400"
                                        >
                                            <LogOut className="mr-2 h-4 w-4" />
                                            <span>Logout</span>
                                        </DropdownMenuItem>
                                    </DropdownMenuContent>
                                </DropdownMenu>
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
            
            <DeleteApiKeyModal
                isOpen={isDeleteApiKeyModalOpen}
                onClose={() => setIsDeleteApiKeyModalOpen(false)}
                onSuccess={handleApiKeyDeleted}
            />
        </>
    );
}
