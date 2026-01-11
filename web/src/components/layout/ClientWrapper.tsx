"use client";

import React from "react";
import { usePathname } from "next/navigation";
import { AuthProvider } from "@/context/AuthContext";
import { Sidebar } from "@/components/layout/Sidebar";
import { Header } from "@/components/layout/Header";
import { NavigationProgress } from "@/components/layout/NavigationProgress";
import ApiKeyBanner from "@/components/layout/ApiKeyBanner";
import { ToastProvider, useToast } from "@/components/ui/toast";
import { setGlobalToastHandler as setAuthToastHandler } from "@/lib/authHandler";
import { setGlobalToastHandler as setApiToastHandler } from "@/lib/apiClient";

function ClientWrapperContent({ children }: { children: React.ReactNode }) {
    const pathname = usePathname();
    const isAuthPage = pathname === "/login" || pathname === "/signup" || pathname === "/forgot-password";
    const { addToast } = useToast();

    // Set up global toast handler for authHandler and apiClient
    React.useEffect(() => {
        setAuthToastHandler(addToast);
        setApiToastHandler(addToast);
    }, [addToast]);

    return (
        <AuthProvider>
            <NavigationProgress />
            {isAuthPage ? (
                children
            ) : (
                <div className="flex h-screen overflow-hidden bg-background">
                    <Sidebar />
                    <div className="flex-1 flex flex-col overflow-hidden">
                        <Header />
                        <main className="flex-1 overflow-y-auto">
                            {children}
                        </main>
                    </div>
                </div>
            )}
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
