"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
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
    const router = useRouter();

    const handleProfileAction = (value: string) => {
        if (value === "api-key") {
            setIsApiKeyModalOpen(true);
            // Reset select value so it can be selected again
            setTimeout(() => setSelectValue(""), 100);
        } else if (value === "logout") {
            logout();
        }
    };

    const handleLoginClick = () => {
        router.push("/login");
    };

    return (
        <>
            <header className="sticky top-0 z-30 w-full border-b border-border bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
                <div className="flex h-16 items-center justify-end gap-2 px-6">
                    <ThemeToggle />
                    
                    {!isLoading && (
                        <>
                            {user ? (
                                <Select value={selectValue} onValueChange={handleProfileAction}>
                                    <SelectTrigger className="w-[200px]">
                                        <div className="flex items-center gap-2">
                                            <div className="h-6 w-6 rounded-full bg-primary/10 flex items-center justify-center">
                                                <User className="h-4 w-4 text-primary" />
                                            </div>
                                            <span className="text-sm font-medium truncate">
                                                {user.full_name || user.email}
                                            </span>
                                        </div>
                                    </SelectTrigger>
                                    <SelectContent className="bg-card z-50">
                                        <SelectItem value="info" disabled>
                                            <div className="flex flex-col space-y-1 py-1">
                                                <p className="text-sm font-medium leading-none">
                                                    {user.full_name || "Account"}
                                                </p>
                                                <p className="text-xs leading-none text-muted-foreground">
                                                    {user.email}
                                                </p>
                                            </div>
                                        </SelectItem>
                                        <SelectItem value="api-key">
                                            <div className="flex items-center">
                                                <Key className="mr-2 h-4 w-4" />
                                                <span>Manage API Key</span>
                                            </div>
                                        </SelectItem>
                                        <SelectItem value="logout">
                                            <div className="flex items-center text-red-600 dark:text-red-400">
                                                <LogOut className="mr-2 h-4 w-4" />
                                                <span>Logout</span>
                                            </div>
                                        </SelectItem>
                                    </SelectContent>
                                </Select>
                            ) : (
                                <Button
                                    variant="ghost"
                                    size="icon"
                                    onClick={handleLoginClick}
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
            
            <ApiKeyModal
                isOpen={isApiKeyModalOpen}
                onClose={() => setIsApiKeyModalOpen(false)}
            />
        </>
    );
}
