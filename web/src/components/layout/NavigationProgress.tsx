"use client";

import { useEffect, useState, useRef, Suspense } from "react";
import { usePathname, useSearchParams } from "next/navigation";
import { cn } from "@/lib/utils";

function NavigationProgressInner() {
    const pathname = usePathname();
    const searchParams = useSearchParams();
    const [isNavigating, setIsNavigating] = useState(false);
    const [progress, setProgress] = useState(0);
    const progressRef = useRef<NodeJS.Timeout | null>(null);
    const previousPathRef = useRef(pathname);

    const startProgress = () => {
        setIsNavigating(true);
        setProgress(0);

        // Clear any existing interval
        if (progressRef.current) {
            clearInterval(progressRef.current);
        }

        // Simulate progress
        progressRef.current = setInterval(() => {
            setProgress((prev) => {
                if (prev >= 90) {
                    return prev;
                }
                // Slow down as we approach 90%
                const increment = Math.max(1, (90 - prev) / 10);
                return Math.min(90, prev + increment);
            });
        }, 100);
    };

    const completeProgress = () => {
        // Complete the progress bar
        setProgress(100);

        // Clear the interval
        if (progressRef.current) {
            clearInterval(progressRef.current);
            progressRef.current = null;
        }

        // Hide after animation
        setTimeout(() => {
            setIsNavigating(false);
            setProgress(0);
        }, 300);
    };

    // Complete progress when pathname changes
    useEffect(() => {
        if (previousPathRef.current !== pathname) {
            previousPathRef.current = pathname;
            // Use requestAnimationFrame to avoid synchronous setState in effect
            requestAnimationFrame(() => {
                completeProgress();
            });
        }
    }, [pathname, searchParams]);

    // Listen for navigation start events
    useEffect(() => {
        const handleClick = (e: MouseEvent) => {
            const target = e.target as HTMLElement;
            const anchor = target.closest("a");

            if (anchor) {
                const href = anchor.getAttribute("href");
                // Only start progress for internal navigation
                if (href && href.startsWith("/") && href !== pathname) {
                    startProgress();
                }
            }
        };

        document.addEventListener("click", handleClick);
        return () => document.removeEventListener("click", handleClick);
    }, [pathname]);

    // Cleanup on unmount
    useEffect(() => {
        return () => {
            if (progressRef.current) {
                clearInterval(progressRef.current);
            }
        };
    }, []);

    if (!isNavigating && progress === 0) {
        return null;
    }

    return (
        <div className="fixed top-0 left-0 right-0 z-50 h-1">
            <div
                className={cn(
                    "h-full bg-linear-to-r from-accent via-accent/80 to-accent transition-all duration-200 ease-out",
                    progress === 100 && "opacity-0"
                )}
                style={{ width: `${progress}%` }}
            />
            {/* Glow effect */}
            <div
                className={cn(
                    "absolute right-0 top-0 h-full w-24 bg-linear-to-l from-accent/50 to-transparent blur-sm transition-all duration-200",
                    progress === 100 && "opacity-0"
                )}
                style={{
                    transform: `translateX(${progress < 100 ? 0 : 100}%)`,
                    left: `calc(${progress}% - 24px)`,
                }}
            />
        </div>
    );
}

export function NavigationProgress() {
    return (
        <Suspense fallback={null}>
            <NavigationProgressInner />
        </Suspense>
    );
}
