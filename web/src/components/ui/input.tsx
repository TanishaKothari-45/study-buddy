import * as React from "react"
import { cn } from "@/lib/utils"

export interface InputProps
    extends React.InputHTMLAttributes<HTMLInputElement> { }

const Input = React.forwardRef<HTMLInputElement, InputProps>(
    ({ className, type, ...props }, ref) => {
        return (
            <input
                type={type}
                className={cn(
                    "flex h-9 w-full rounded-lg border border-[var(--input-border)] bg-[var(--input-bg)]",
                    "px-3 py-2 text-sm text-[var(--text)] placeholder:text-[var(--text-faint)]",
                    "transition-all duration-150",
                    "file:border-0 file:bg-transparent file:text-sm file:font-medium",
                    "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-amber-600/40 focus-visible:border-amber-600",
                    "disabled:cursor-not-allowed disabled:opacity-50",
                    className
                )}
                ref={ref}
                {...props}
            />
        )
    }
)
Input.displayName = "Input"

export { Input }
