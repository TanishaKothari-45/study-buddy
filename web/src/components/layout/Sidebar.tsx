"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";
import {
    LayoutDashboard,
    Upload,
    FileText,
    Database,
    MessageSquare,
    ClipboardList,
    PenTool,
    Menu,
    X,
    ChevronsLeft,
    ChevronsRight,
    Loader2
} from "lucide-react";
import { useState, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { motion, AnimatePresence } from "framer-motion";

const routes = [
    {
        label: "Dashboard",
        icon: LayoutDashboard,
        href: "/",
        color: "text-sky-500",
    },
    // {
    //     label: "Upload PDFs",
    //     icon: Upload,
    //     href: "/upload",
    //     color: "text-violet-500",
    // },
    {
        label: "Evaluate Answer",
        icon: FileText,
        href: "/evaluate",
        color: "text-pink-700",
    },
    // {
    //     label: "Training Data",
    //     icon: Database,
    //     href: "/training-data",
    //     color: "text-orange-700",
    // },
    {
        label: "Chat / Q&A",
        icon: MessageSquare,
        href: "/chat",
        color: "text-emerald-500",
    },
    {
        label: "Prelims Mock Test",
        icon: ClipboardList,
        href: "/mock-test",
        color: "text-blue-600",
    },
    {
        label: "Mains Answer",
        icon: PenTool,
        href: "/mains-answer",
        color: "text-purple-600",
    },
];

export function Sidebar() {
    const pathname = usePathname();
    const [isOpen, setIsOpen] = useState(false); // Mobile state
    const [isCollapsed, setIsCollapsed] = useState(false); // Desktop state
    const [navigatingTo, setNavigatingTo] = useState<string | null>(null); // Loading state

    // Clear loading state when pathname changes (navigation complete)
    useEffect(() => {
        setNavigatingTo(null);
    }, [pathname]);

    return (
        <>
            {/* Mobile Trigger */}
            <div className="md:hidden fixed top-4 left-4 z-50">
                <Button variant="outline" size="icon" onClick={() => setIsOpen(!isOpen)} className="bg-background/80 backdrop-blur-sm">
                    {isOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
                </Button>
            </div>

            {/* Sidebar Container */}
            <AnimatePresence mode="wait">
                <motion.div
                    className={cn(
                        "fixed inset-y-0 left-0 z-40 bg-[hsl(var(--sidebar-bg))] text-foreground border-r border-border transform transition-all duration-300 ease-in-out md:static md:block",
                        isOpen ? "translate-x-0" : "-translate-x-full md:translate-x-0",
                        isCollapsed ? "w-20" : "w-72"
                    )}
                >
                    <div className="flex flex-col h-full text-foreground relative">
                        {/* Desktop Toggle Button */}
                        <div className="hidden md:block absolute -right-4 top-6 z-50">
                            <Button
                                variant="outline"
                                size="icon"
                                className="h-8 w-8 rounded-full shadow-md bg-background border hover:bg-muted"
                                onClick={() => setIsCollapsed(!isCollapsed)}
                                title={isCollapsed ? "Expand Sidebar" : "Collapse Sidebar"}
                            >
                                {isCollapsed ? <ChevronsRight className="h-5 w-5" /> : <ChevronsLeft className="h-5 w-5" />}
                            </Button>
                        </div>

                        {/* Sidebar Header / Logo */}
                        <div className={cn("px-3 py-4 flex-1 transition-all duration-300", isCollapsed ? "items-center" : "")}>
                            <Link href="/" className={cn("flex items-center mb-14 transition-all duration-300", isCollapsed ? "justify-center px-0" : "pl-3")}>
                                <div className="relative w-8 h-8 flex-shrink-0">
                                    <div className="absolute inset-0 bg-gradient-to-r from-accent to-accent/60 rounded-lg animate-pulse" />
                                </div>
                                {!isCollapsed && (
                                    <h1 className="ml-4 text-2xl font-bold bg-clip-text text-transparent bg-gradient-to-r from-accent to-accent/60 whitespace-nowrap overflow-hidden">
                                        Study Buddy
                                    </h1>
                                )}
                            </Link>

                            {/* Routes */}
                            <div className="space-y-1 w-full">
                                {routes.map((route) => (
                                    <Link
                                        key={route.href}
                                        href={route.href}
                                        onClick={() => {
                                            if (pathname !== route.href) setNavigatingTo(route.href);
                                            setIsOpen(false);
                                        }}
                                        className={cn(
                                            "text-sm group flex p-3 w-full font-medium cursor-pointer hover:text-accent hover:bg-[hsl(var(--sidebar-active))] rounded-lg transition-all relative",
                                            pathname === route.href ? "text-accent bg-[hsl(var(--sidebar-active))]" : "text-muted-foreground",
                                            isCollapsed ? "justify-center" : "justify-start"
                                        )}
                                        title={isCollapsed ? route.label : undefined}
                                    >
                                        <div className={cn("flex items-center", isCollapsed ? "justify-center" : "flex-1")}>
                                            {/* Show spinner if navigating to this route, otherwise show icon */}
                                            {navigatingTo === route.href ? (
                                                <Loader2 className={cn("h-6 w-6 animate-spin text-accent", !isCollapsed && "mr-3")} />
                                            ) : (
                                                <route.icon className={cn("h-6 w-6 flex-shrink-0", pathname === route.href ? "text-accent" : route.color, !isCollapsed && "mr-3")} />
                                            )}

                                            {!isCollapsed && (
                                                <span className="whitespace-nowrap overflow-hidden text-ellipsis">
                                                    {route.label}
                                                </span>
                                            )}
                                        </div>
                                    </Link>
                                ))}
                            </div>
                        </div>

                        {/* Footer / Version Info */}
                        <div className="px-3 py-2">
                            {!isCollapsed && (
                                <div className="bg-[hsl(var(--sidebar-active))] rounded-lg p-4 transition-all opacity-100 duration-300">
                                    <p className="text-xs text-muted-foreground text-center">
                                        Study Buddy AI v1.0
                                    </p>
                                </div>
                            )}
                            {isCollapsed && (
                                <div className="flex justify-center py-4">
                                    <span className="text-[10px] text-muted-foreground font-bold">v1.0</span>
                                </div>
                            )}
                        </div>
                    </div>
                </motion.div>
            </AnimatePresence>

            {/* Overlay for mobile */}
            {isOpen && (
                <div
                    className="fixed inset-0 bg-black/50 z-30 md:hidden"
                    onClick={() => setIsOpen(false)}
                />
            )}
        </>
    );
}
