"use client";

import { motion } from "framer-motion";
import { cn } from "@/lib/utils";

interface LoaderProps {
    className?: string;
    text?: string;
}

export function PageLoader({ className, text = "Loading..." }: LoaderProps) {
    return (
        <div className={cn("flex flex-col items-center justify-center min-h-[300px] gap-6", className)}>
            <div className="relative flex items-center justify-center">
                {/* Outer pulsing ring */}
                <motion.div
                    className="absolute inset-[-12px] rounded-full bg-orange-100/80 dark:bg-orange-500/10"
                    animate={{
                        scale: [1, 1.4, 1],
                        opacity: [0.5, 0.1, 0.5],
                    }}
                    transition={{
                        duration: 2.5,
                        repeat: Infinity,
                        ease: "easeInOut",
                    }}
                />
                {/* Inner animating dots */}
                <div className="flex gap-2.5 relative z-10 px-5 py-3 bg-[var(--bg-secondary)] backdrop-blur-sm rounded-full border border-[var(--card-border)] shadow-sm">
                    {[0, 1, 2].map((i) => (
                        <motion.div
                            key={i}
                            className="w-2.5 h-2.5 rounded-full bg-orange-400"
                            animate={{
                                y: ["0%", "-40%", "0%"],
                                opacity: [0.4, 1, 0.4],
                            }}
                            transition={{
                                duration: 1.2,
                                repeat: Infinity,
                                ease: "easeInOut",
                                delay: i * 0.2,
                            }}
                        />
                    ))}
                </div>
            </div>
            {text && (
                <motion.p
                    className="text-[13px] font-medium text-[var(--text-muted)] tracking-widest uppercase"
                    animate={{ opacity: [0.4, 1, 0.4] }}
                    transition={{ duration: 2.5, repeat: Infinity }}
                >
                    {text}
                </motion.p>
            )}
        </div>
    );
}

// A smaller inline loader to replace simple spinners inside buttons
export function InlineLoader({ className }: Omit<LoaderProps, "text">) {
    return (
        <div className={cn("flex items-center gap-1", className)}>
            {[0, 1, 2].map((i) => (
                <motion.div
                    key={i}
                    className="w-1.5 h-1.5 rounded-full bg-current opacity-70"
                    animate={{ y: ["0%", "-40%", "0%"], opacity: [0.3, 1, 0.3] }}
                    transition={{
                        duration: 0.9,
                        repeat: Infinity,
                        ease: "easeInOut",
                        delay: i * 0.15,
                    }}
                />
            ))}
        </div>
    );
}
