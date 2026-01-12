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

// Public routes that don't require authentication
const PUBLIC_ROUTES = ["/login", "/signup", "/forgot-password", "/auth/callback"];

function ProtectedContent({ children }: { children: React.ReactNode }) {
    const pathname = usePathname();
    const router = useRouter();
    const { user, isLoading } = useAuth();
    const isPublicRoute = PUBLIC_ROUTES.some(route => pathname.startsWith(route));

    React.useEffect(() => {
        // Don't redirect while loading auth state
        if (isLoading) return;

        // If not authenticated and trying to access a protected route, redirect to login
        if (!user && !isPublicRoute) {
            storeReturnUrl(pathname);
            router.push("/login");
        }
    }, [user, isLoading, isPublicRoute, pathname, router]);

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

    // If not authenticated and on protected route, show loading while redirecting
    if (!user && !isPublicRoute) {
        return (
            <div className="flex h-screen items-center justify-center bg-background">
                <div className="flex flex-col items-center gap-4">
                    <div className="h-8 w-8 animate-spin rounded-full border-4 border-primary border-t-transparent" />
                    <p className="text-sm text-muted-foreground">Redirecting to login...</p>
                </div>
            </div>
        );
    }

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
            <ProtectedContent>{children}</ProtectedContent>
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
