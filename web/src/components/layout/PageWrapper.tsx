"use client";

import React from "react";
import ApiKeyBanner from "@/components/layout/ApiKeyBanner";

interface PageWrapperProps {
    children: React.ReactNode;
    className?: string;
    showApiKeyBanner?: boolean;
}

/**
 * PageWrapper component that includes ApiKeyBanner and consistent padding
 * Use this to wrap your page content instead of manually adding p-8
 */
export function PageWrapper({ 
    children, 
    className = "", 
    showApiKeyBanner = true 
}: PageWrapperProps) {
    return (
        <div className={`p-8 ${className}`}>
            {showApiKeyBanner && <ApiKeyBanner />}
            {children}
        </div>
    );
}
