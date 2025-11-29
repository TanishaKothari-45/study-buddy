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
    X
} from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { motion, AnimatePresence } from "framer-motion";

const routes = [
    {
        label: "Dashboard",
        icon: LayoutDashboard,
        href: "/",
        color: "text-sky-500",
    },
    {
        label: "Upload PDFs",
        icon: Upload,
        href: "/upload",
        color: "text-violet-500",
    },
    {
        label: "Evaluate Answer",
        icon: FileText,
        href: "/evaluate",
        color: "text-pink-700",
    },
    {
        label: "Training Data",
        icon: Database,
        href: "/training-data",
        color: "text-orange-700",
    },
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
    const [isOpen, setIsOpen] = useState(false);

    return (
        <>
            {/* Mobile Trigger */}
            <div className="md:hidden fixed top-4 left-4 z-50">
                <Button variant="outline" size="icon" onClick={() => setIsOpen(!isOpen)} className="bg-background">
                    {isOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
                </Button>
            </div>

            {/* Sidebar Container */}
            <AnimatePresence mode="wait">
                <motion.div
                    className={cn(
                        "fixed inset-y-0 left-0 z-40 w-72 bg-[#fcfaf8] text-foreground border-r border-border transform transition-transform duration-300 ease-in-out md:translate-x-0 md:static md:block",
                        isOpen ? "translate-x-0" : "-translate-x-full"
                    )}
                >
                    <div className="space-y-4 py-4 flex flex-col h-full bg-sidebar-bg text-foreground">
                        <div className="px-3 py-2 flex-1">
                            <Link href="/" className="flex items-center pl-3 mb-14">
                                <div className="relative w-8 h-8 mr-4">
                                    {/* Logo placeholder */}
                                    <div className="absolute inset-0 bg-gradient-to-r from-accent to-accent/60 rounded-lg animate-pulse" />
                                </div>
                                <h1 className="text-2xl font-bold bg-clip-text text-transparent bg-gradient-to-r from-accent to-accent/60">
                                    Study Buddy
                                </h1>
                            </Link>
                            <div className="space-y-1">
                                {routes.map((route) => (
                                    <Link
                                        key={route.href}
                                        href={route.href}
                                        onClick={() => setIsOpen(false)}
                                        className={cn(
                                            "text-sm group flex p-3 w-full justify-start font-medium cursor-pointer hover:text-accent hover:bg-sidebar-active rounded-lg transition",
                                            pathname === route.href
                                                ? "text-accent bg-sidebar-active"
                                                : "text-muted-foreground"
                                        )}
                                    >
                                        <div className="flex items-center flex-1">
                                            <route.icon className={cn("h-5 w-5 mr-3", pathname === route.href ? "text-accent" : route.color)} />
                                            {route.label}
                                        </div>
                                    </Link>
                                ))}
                            </div>
                        </div>
                        <div className="px-3 py-2">
                            <div className="bg-sidebar-active rounded-lg p-4">
                                <p className="text-xs text-muted-foreground text-center">
                                    Study Buddy AI v1.0
                                </p>
                            </div>
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
