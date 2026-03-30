import type { Metadata } from "next";
import { Plus_Jakarta_Sans, Inter, Lora } from "next/font/google";
import "./globals.css";
import { ClientWrapper } from "@/components/layout/ClientWrapper";
import { ThemeProvider } from "@/components/theme-provider";
import { ErrorBoundary } from "@/components/ErrorBoundary";

const jakartaSans = Plus_Jakarta_Sans({
  subsets: ["latin"],
  variable: "--font-jakarta",
  display: "swap",
});

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
  display: "swap",
});

const lora = Lora({
  subsets: ["latin"],
  variable: "--font-lora",
  display: "swap",
  weight: ["400", "500", "600", "700"],
});

export const metadata: Metadata = {
  title: "Study Buddy AI | Mentor Platform",
  description: "Your AI-powered geography study companion",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className={`${jakartaSans.variable} ${inter.variable} ${lora.variable} font-inter antialiased`}>
        <ErrorBoundary>
          <ThemeProvider
            attribute="class"
            defaultTheme="light"
            enableSystem={false}
          >
            <ClientWrapper>
              {children}
            </ClientWrapper>
          </ThemeProvider>
        </ErrorBoundary>
      </body>
    </html>
  );
}
