import type { Config } from "tailwindcss";

const config: Config = {
    darkMode: "class",
    content: [
        "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
        "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
        "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
    ],
    theme: {
        extend: {
            fontFamily: {
                jakarta: ["var(--font-jakarta)", "system-ui", "sans-serif"],
                inter: ["var(--font-inter)", "system-ui", "sans-serif"],
            },
            colors: {
                // Semantic Tailwind aliases mapping to CSS variables
                background:  "var(--bg)",
                foreground:  "var(--text)",

                card: {
                    DEFAULT:    "var(--card)",
                    foreground: "var(--text)",
                },
                popover: {
                    DEFAULT:    "var(--card)",
                    foreground: "var(--text)",
                },
                primary: {
                    DEFAULT:    "var(--accent)",
                    foreground: "#FAFAF8",
                },
                secondary: {
                    DEFAULT:    "var(--bg-secondary)",
                    foreground: "var(--text)",
                },
                muted: {
                    DEFAULT:    "var(--bg-secondary)",
                    foreground: "var(--text-muted)",
                },
                accent: {
                    DEFAULT:    "var(--accent)",
                    foreground: "#FAFAF8",
                },
                destructive: {
                    DEFAULT:    "var(--destructive)",
                    foreground: "#FAFAF8",
                },
                border:  "var(--card-border)",
                input:   "var(--input-bg)",
                ring:    "var(--accent)",

                // Direct aliases for convenience
                "bg-secondary":  "var(--bg-secondary)",
                "bg-tertiary":   "var(--bg-tertiary)",
                "text-muted":    "var(--text-muted)",
                "text-faint":    "var(--text-faint)",
                "accent-hover":  "var(--accent-hover)",
                "accent-light":  "var(--accent-light)",
                "sidebar-bg":    "var(--sidebar-bg)",
                "sidebar-active":"var(--sidebar-active)",
            },
            borderRadius: {
                lg: "var(--radius)",
                md: "calc(var(--radius) - 2px)",
                sm: "calc(var(--radius) - 4px)",
            },
            boxShadow: {
                "warm-sm": "0 1px 3px rgba(28,25,23,0.08), 0 1px 2px rgba(28,25,23,0.04)",
                "warm-md": "0 4px 12px rgba(28,25,23,0.08), 0 2px 4px rgba(28,25,23,0.04)",
                "warm-lg": "0 10px 32px rgba(28,25,23,0.10), 0 4px 8px rgba(28,25,23,0.04)",
                "amber-sm": "0 1px 3px rgba(217,119,6,0.15)",
            },
        },
    },
    plugins: [require("tailwindcss-animate"), require("@tailwindcss/typography")],
};
export default config;
