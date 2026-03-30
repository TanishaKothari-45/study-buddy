"use client";

import React from "react";
import { usePathname, useRouter } from "next/navigation";
import { AuthProvider, useAuth } from "@/context/AuthContext";
import { Sidebar } from "@/components/layout/Sidebar";
import { Header } from "@/components/layout/Header";
import { NavigationProgress } from "@/components/layout/NavigationProgress";
import { ToastProvider, useToast } from "@/components/ui/toast";
import { setGlobalToastHandler as setAuthToastHandler } from "@/lib/authHandler";
import { setGlobalToastHandler as setApiToastHandler } from "@/lib/apiClient";
import { storeReturnUrl } from "@/lib/authHandler";
import { ErrorBoundary } from "@/components/ErrorBoundary";

// Public routes that don't require authentication
const PUBLIC_ROUTES = ["/login", "/signup", "/forgot-password", "/auth/callback"];

function ProtectedContent({ children }: { children: React.ReactNode }) {
    const pathname = usePathname();
    const router = useRouter();
    const { user, isLoading } = useAuth();
    const isPublicRoute = PUBLIC_ROUTES.some(route => pathname.startsWith(route));

    // TODO: REVERT FOR PROD — uncomment the block below to restore login redirect.
    // AUTH CHECK DISABLED — skip login redirect (no-auth India mode)
    // React.useEffect(() => {
    //     if (isLoading) return;
    //     if (!user && !isPublicRoute) {
    //         storeReturnUrl(pathname);
    //         router.push("/login");
    //     }
    // }, [user, isLoading, isPublicRoute, pathname, router]);

    // Show loading state while checking auth
    if (isLoading) {
        return (
            <div className="flex h-screen items-center justify-center bg-background">
                <div className="flex flex-col items-center gap-4">
                    <div className="h-8 w-8 animate-spin rounded-full border-4 border-primary border-t-transparent" />
                    <p className="text-sm text-muted-foreground">Loading...</p>
                </div>
            </div>
        );
    }

    // TODO: REVERT FOR PROD — uncomment the line below to restore the redirect guard.
    // AUTH CHECK DISABLED — always render content regardless of auth state
    // if (!user && !isPublicRoute) { return <div>Redirecting...</div>; }

    // Render public routes or authenticated content
    if (isPublicRoute) {
        return <>{children}</>;
    }

    // Render protected content with layout
    return (
        <div className="flex h-screen overflow-hidden bg-background">
            <Sidebar />
            <div className="flex-1 flex flex-col overflow-hidden">
                <Header />
                <main className="flex-1 overflow-y-auto">
                    {children}
                </main>
            </div>
        </div>
    );
}

function ClientWrapperContent({ children }: { children: React.ReactNode }) {
    const { addToast } = useToast();

    // Set up global toast handler for authHandler and apiClient
    React.useEffect(() => {
        setAuthToastHandler(addToast);
        setApiToastHandler(addToast);
    }, [addToast]);

    return (
        <AuthProvider>
            <NavigationProgress />
            <ErrorBoundary>
                <ProtectedContent>{children}</ProtectedContent>
            </ErrorBoundary>
        </AuthProvider>
    );
}

export function ClientWrapper({ children }: { children: React.ReactNode }) {
    return (
        <ToastProvider>
            <ClientWrapperContent>{children}</ClientWrapperContent>
        </ToastProvider>
    );
}
