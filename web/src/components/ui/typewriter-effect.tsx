"use client";

import { useState, useEffect, useRef } from "react";

interface TypewriterEffectProps {
    content: string;
    speed?: number;
    onComplete?: () => void;
}

export function TypewriterEffect({ content, speed = 15, onComplete }: TypewriterEffectProps) {
    const [displayLength, setDisplayLength] = useState(0);

    useEffect(() => {
        // Reset if content is empty (new chat)
        if (!content) {
            setDisplayLength(0);
            return;
        }

        // If we've already shown everything, stop
        if (displayLength >= content.length) {
            onComplete?.();
            return;
        }

        // Set up the timer to reveal characters
        const interval = setInterval(() => {
            setDisplayLength((prev) => {
                if (prev < content.length) {
                    return prev + 1;
                }
                clearInterval(interval);
                onComplete?.();
                return prev;
            });
        }, speed);

        return () => clearInterval(interval);
    }, [content, speed, onComplete, displayLength]);

    // Always slice from the source content to ensure correctness
    const displayedContent = content.slice(0, displayLength);

    return (
        <span>
            {displayedContent}
            {displayLength < content.length && (
                <span className="inline-block w-1.5 h-4 ml-0.5 align-middle bg-emerald-500 animate-pulse" />
            )}
        </span>
    );
}
