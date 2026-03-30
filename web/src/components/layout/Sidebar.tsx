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
    Loader2,
    BookOpen,
} from "lucide-react";
import { useState, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { motion, AnimatePresence } from "framer-motion";

const routes = [
    {
        label: "Dashboard",
        icon: LayoutDashboard,
        href: "/",
        color: "text-amber-700 dark:text-amber-500",
    },
    {
        label: "Upload work",
        icon: Upload,
        href: "/upload",
        color: "text-[var(--accent)]",
    },
    {
        label: "Review answers",
        icon: FileText,
        href: "/evaluate",
        color: "text-rose-600 dark:text-rose-400",
    },
    {
        label: "Knowledge base",
        icon: Database,
        href: "/training-data",
        color: "text-orange-600 dark:text-orange-400",
    },
    {
        label: "Mentor chat",
        icon: MessageSquare,
        href: "/chat",
        color: "text-emerald-600 dark:text-emerald-400",
    },
    {
        label: "Prelims practice",
        icon: ClipboardList,
        href: "/mock-test",
        color: "text-blue-600 dark:text-blue-400",
    },
    {
        label: "Mains practice",
        icon: PenTool,
        href: "/mains-answer",
        color: "text-purple-600 dark:text-purple-400",
    },
];

export function Sidebar() {
    const pathname = usePathname();
    const [isOpen, setIsOpen] = useState(false);
    const [isCollapsed, setIsCollapsed] = useState(false);
    const [navigatingTo, setNavigatingTo] = useState<string | null>(null);

    useEffect(() => {
        setNavigatingTo(null);
    }, [pathname]);

    const sidebarContent = (
        <div className="flex flex-col h-full relative">
            {/* Desktop Toggle */}
            <div className="hidden md:block absolute -right-4 top-6 z-50">
                <button
                    className={cn(
                        "h-8 w-8 rounded-full border border-[var(--card-border)] bg-[var(--bg)] shadow-warm-sm",
                        "flex items-center justify-center text-[var(--text-muted)] hover:text-[var(--accent)]",
                        "hover:border-[var(--accent)] transition-all duration-200"
                    )}
                    onClick={() => setIsCollapsed(!isCollapsed)}
                    title={isCollapsed ? "Expand sidebar" : "Collapse sidebar"}
                >
                    {isCollapsed
                        ? <ChevronsRight className="h-4 w-4" />
                        : <ChevronsLeft className="h-4 w-4" />
                    }
                </button>
            </div>

            {/* Logo */}
            <div className={cn(
                "px-4 py-6 border-b border-[var(--sidebar-border)]",
                isCollapsed ? "flex justify-center" : ""
            )}>
                <Link
                    href="/"
                    className={cn(
                        "flex items-center gap-3 transition-all duration-300",
                        isCollapsed ? "justify-center" : ""
                    )}
                >
                    <div className="flex-shrink-0 w-8 h-8 rounded-lg bg-amber-600 flex items-center justify-center shadow-amber-sm">
                        <BookOpen className="h-4 w-4 text-white" />
                    </div>
                    {!isCollapsed && (
                        <span className="font-semibold text-[var(--text)] tracking-tight whitespace-nowrap overflow-hidden text-base">
                            Study Buddy
                        </span>
                    )}
                </Link>
            </div>

            {/* Nav items */}
            <nav className={cn("flex-1 px-3 py-4 space-y-0.5", isCollapsed ? "px-2" : "")}>
                {routes.map((route) => {
                    const isActive = pathname === route.href;
                    const isNavigating = navigatingTo === route.href;

                    return (
                        <Link
                            key={route.href}
                            href={route.href}
                            onClick={() => {
                                if (pathname !== route.href) setNavigatingTo(route.href);
                                setIsOpen(false);
                            }}
                            title={isCollapsed ? route.label : undefined}
                            className={cn(
                                "flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium",
                                "transition-all duration-150 group relative",
                                isActive
                                    ? "bg-[var(--sidebar-active)] text-[var(--accent)]"
                                    : "text-[var(--text-muted)] hover:bg-[var(--sidebar-active)] hover:text-[var(--text)]",
                                isCollapsed ? "justify-center px-2" : ""
                            )}
                        >
                            {/* Active indicator */}
                            {isActive && (
                                <motion.div
                                    layoutId="sidebarActiveIndicator"
                                    className="absolute left-0 top-1/2 -translate-y-1/2 w-1 h-6 bg-[var(--accent)] rounded-r-md"
                                    transition={{ type: "spring", stiffness: 300, damping: 30 }}
                                />
                            )}

                            {isNavigating ? (
                                <Loader2 className="h-5 w-5 flex-shrink-0 animate-spin text-[var(--accent)]" />
                            ) : (
                                <route.icon className={cn(
                                    "h-5 w-5 flex-shrink-0 transition-colors duration-150",
                                    isActive ? "text-amber-600" : route.color,
                                    !isActive && "opacity-75 group-hover:opacity-100"
                                )} />
                            )}

                            {!isCollapsed && (
                                <span className="whitespace-nowrap overflow-hidden text-ellipsis">
                                    {route.label}
                                </span>
                            )}
                        </Link>
                    );
                })}
            </nav>

            {/* Footer */}
            <div className={cn("px-4 py-4 border-t border-[var(--sidebar-border)]", isCollapsed ? "px-2" : "")}>
                {!isCollapsed ? (
                    <p className="text-xs text-[var(--text-faint)] text-center">
                        Study Buddy AI · v1.0
                    </p>
                ) : (
                    <p className="text-[10px] text-[var(--text-faint)] text-center font-medium">v1.0</p>
                )}
            </div>
        </div>
    );

    return (
        <>
            {/* Mobile trigger */}
            <div className="md:hidden fixed top-4 left-4 z-50">
                <button
                    onClick={() => setIsOpen(!isOpen)}
                    className={cn(
                        "h-9 w-9 rounded-lg border border-[var(--card-border)] bg-[var(--bg)]/90 backdrop-blur-sm",
                        "flex items-center justify-center text-[var(--text-muted)] shadow-warm-sm",
                        "hover:text-[var(--accent)] hover:border-[var(--accent)] transition-all duration-200"
                    )}
                >
                    {isOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
                </button>
            </div>

            {/* Sidebar — desktop static */}
            <aside
                className={cn(
                    "hidden md:flex flex-col inset-y-0 left-0 z-40",
                    "bg-[var(--sidebar-bg)] border-r border-[var(--sidebar-border)]",
                    "transition-all duration-300 ease-in-out",
                    isCollapsed ? "w-[72px]" : "w-64"
                )}
            >
                {sidebarContent}
            </aside>

            {/* Sidebar — mobile overlay */}
            <AnimatePresence>
                {isOpen && (
                    <>
                        <motion.div
                            initial={{ opacity: 0 }}
                            animate={{ opacity: 1 }}
                            exit={{ opacity: 0 }}
                            transition={{ duration: 0.2 }}
                            className="fixed inset-0 bg-black/40 z-30 md:hidden"
                            onClick={() => setIsOpen(false)}
                        />
                        <motion.aside
                            initial={{ x: "-100%" }}
                            animate={{ x: 0 }}
                            exit={{ x: "-100%" }}
                            transition={{ duration: 0.25, ease: "easeOut" }}
                            className="fixed inset-y-0 left-0 z-40 w-64 flex flex-col md:hidden bg-[var(--sidebar-bg)] border-r border-[var(--sidebar-border)] shadow-warm-lg"
                        >
                            {sidebarContent}
                        </motion.aside>
                    </>
                )}
            </AnimatePresence>
        </>
    );
}
