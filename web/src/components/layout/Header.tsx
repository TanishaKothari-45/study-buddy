"use client";

import { ThemeToggle } from "@/components/theme-toggle";

export function Header() {
    return (
        <header className="sticky top-0 z-30 w-full border-b border-border bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
            <div className="flex h-16 items-center justify-end px-6">
                <ThemeToggle />
            </div>
        </header>
    );
}
