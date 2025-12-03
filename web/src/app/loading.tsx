"use client";

import { Loader2 } from "lucide-react";

export default function Loading() {
    return (
        <div className="flex items-center justify-center h-full min-h-[400px]">
            <div className="flex flex-col items-center gap-4">
                <Loader2 className="h-12 w-12 animate-spin text-accent" />
                <p className="text-muted-foreground text-sm">Loading...</p>
            </div>
        </div>
    );
}
