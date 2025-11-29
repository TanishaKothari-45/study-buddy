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
            colors: {
                // Base colors mapped to CSS variables
                background: 'hsl(var(--bg))',
                foreground: 'hsl(var(--text))',

                card: {
                    DEFAULT: 'hsl(var(--card))',
                    foreground: 'hsl(var(--text))'
                },
                popover: {
                    DEFAULT: 'hsl(var(--card))',
                    foreground: 'hsl(var(--text))'
                },
                primary: {
                    DEFAULT: 'hsl(var(--accent))',
                    foreground: 'hsl(var(--bg))'
                },
                secondary: {
                    DEFAULT: 'hsl(var(--bg-secondary))',
                    foreground: 'hsl(var(--text))'
                },
                muted: {
                    DEFAULT: 'hsl(var(--bg-secondary))',
                    foreground: 'hsl(var(--text-muted))'
                },
                accent: {
                    DEFAULT: 'hsl(var(--accent))',
                    foreground: 'hsl(var(--bg))'
                },
                destructive: {
                    DEFAULT: 'hsl(var(--destructive))', // Keeping standard destructive for now or mapping to accent
                    foreground: 'hsl(var(--bg))'
                },
                border: 'hsl(var(--card-border))',
                input: 'hsl(var(--input-bg))',
                ring: 'hsl(var(--accent))',

                // Custom specific names from request for direct usage if needed
                bg: "hsl(var(--bg))",
                "bg-secondary": "hsl(var(--bg-secondary))",
                "card-border": "hsl(var(--card-border))",
                text: "hsl(var(--text))",
                "text-muted": "hsl(var(--text-muted))",
                "accent-hover": "hsl(var(--accent-hover))",
                "sidebar-bg": "hsl(var(--sidebar-bg))",
                "sidebar-active": "hsl(var(--sidebar-active))",
                "input-bg": "hsl(var(--input-bg))",
                "input-border": "hsl(var(--input-border))",
            },
            borderRadius: {
                lg: 'var(--radius)',
                md: 'calc(var(--radius) - 2px)',
                sm: 'calc(var(--radius) - 4px)'
            }
        }
    },
    plugins: [require("tailwindcss-animate"), require("@tailwindcss/typography")],
};
export default config;
