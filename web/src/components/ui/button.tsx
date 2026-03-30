import * as React from "react"
import { Slot } from "@radix-ui/react-slot"
import { cva, type VariantProps } from "class-variance-authority"
import { cn } from "@/lib/utils"

const buttonVariants = cva(
  [
    "inline-flex items-center justify-center whitespace-nowrap rounded-lg text-sm font-medium",
    "transition-all duration-150 ease-in-out",
    "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)] focus-visible:ring-offset-2",
    "disabled:pointer-events-none disabled:opacity-40 cursor-pointer",
    "active:scale-[0.97]",
  ].join(" "),
  {
    variants: {
      variant: {
        // Warm amber primary
        default:
          "bg-amber-600 text-white hover:bg-amber-700 shadow-amber-sm",
        // Soft warm border
        outline:
          "border border-[var(--card-border)] bg-[var(--bg)] text-[var(--text)] hover:bg-[var(--bg-secondary)] hover:border-[var(--text-faint)]",
        // Warm secondary
        secondary:
          "bg-[var(--bg-secondary)] text-[var(--text)] hover:bg-[var(--bg-tertiary)]",
        // Ghost
        ghost:
          "text-[var(--text-muted)] hover:bg-[var(--bg-secondary)] hover:text-[var(--text)]",
        // Destructive
        destructive:
          "bg-red-600 text-white hover:bg-red-700",
        // Text link
        link:
          "text-amber-600 underline-offset-4 hover:underline hover:text-amber-700 p-0 h-auto",
      },
      size: {
        default: "h-9 px-4 py-2",
        sm:      "h-8 px-3 text-xs rounded-md",
        lg:      "h-11 px-6 rounded-lg text-base",
        icon:    "h-9 w-9",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  }
)

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
  VariantProps<typeof buttonVariants> {
  asChild?: boolean
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, ...props }, ref) => {
    const Comp = asChild ? Slot : "button"
    return (
      <Comp
        className={cn(buttonVariants({ variant, size, className }))}
        ref={ref}
        {...props}
      />
    )
  }
)
Button.displayName = "Button"

export { Button, buttonVariants }
