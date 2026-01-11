import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import { ClientWrapper } from "@/components/layout/ClientWrapper";
import { ThemeProvider } from "@/components/theme-provider";
import { ErrorBoundary } from "@/components/ErrorBoundary";

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: "Study Buddy AI",
  description: "Your AI-powered geography study companion",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className={inter.className}>
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
