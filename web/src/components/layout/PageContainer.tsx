"use client";

import { cn } from "@/lib/utils";
import { HTMLMotionProps, motion } from "framer-motion";

interface PageContainerProps extends Omit<HTMLMotionProps<"div">, "title"> {
    children: React.ReactNode;
    title?: React.ReactNode;
    description?: React.ReactNode;
    className?: string;
    contentClassName?: string;
}

export function PageContainer({
    children,
    title,
    description,
    className,
    contentClassName,
    ...props
}: PageContainerProps) {
    return (
        <motion.div
            initial={{ opacity: 0, y: 15 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
            className={cn(
                "w-full max-w-6xl mx-auto px-6 py-8 md:px-10 md:py-12 lg:px-12 lg:py-16 min-h-full flex flex-col",
                className
            )}
            {...props}
        >
            {(title || description) && (
                <div className="mb-6 lg:mb-8">
                    {title && (
                        <h1 className="text-3xl md:text-4xl lg:text-5xl font-bold tracking-tight text-[var(--text)] mb-3">
                            {title}
                        </h1>
                    )}
                    {description && (
                        <p className="text-lg text-[var(--text-muted)] max-w-2xl leading-relaxed">
                            {description}
                        </p>
                    )}
                </div>
            )}
            <div className={cn("flex-1", contentClassName)}>
                {children}
            </div>
        </motion.div>
    );
}
