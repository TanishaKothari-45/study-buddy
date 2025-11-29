"use client";

import { useState, useRef, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { Send, User, Bot, Loader2, BookOpen, AlertCircle, Trash2 } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { cn } from "@/lib/utils";

interface Source {
    filename: string;
    chapter?: string;
    section?: string;
    page_number?: number;
    content_source?: string;
}

interface Message {
    id: string;
    role: "user" | "assistant";
    content: string;
    sources?: Source[];
    timestamp: Date;
}

export default function ChatPage() {
    const [messages, setMessages] = useState<Message[]>([
        {
            id: "welcome",
            role: "assistant",
            content: "Hello! I'm your Geography Study Buddy. Ask me anything about your study materials, and I'll explain it simply with examples.",
            timestamp: new Date(),
        },
    ]);
    const [input, setInput] = useState("");
    const [loading, setLoading] = useState(false);
    const messagesEndRef = useRef<HTMLDivElement>(null);

    const scrollToBottom = () => {
        messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
    };

    useEffect(() => {
        scrollToBottom();
    }, [messages]);

    const handleSendMessage = async (e?: React.FormEvent) => {
        e?.preventDefault();
        if (!input.trim() || loading) return;

        const userMessage: Message = {
            id: Date.now().toString(),
            role: "user",
            content: input.trim(),
            timestamp: new Date(),
        };

        setMessages((prev) => [...prev, userMessage]);
        setInput("");
        setLoading(true);

        try {
            const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8001";
            const res = await fetch(`${API_URL}/query/`, {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                },
                body: JSON.stringify({
                    question: userMessage.content,
                    k: 5, // Default to 5 sources
                }),
            });

            if (!res.ok) {
                throw new Error("Failed to get response");
            }

            const data = await res.json();

            const botMessage: Message = {
                id: (Date.now() + 1).toString(),
                role: "assistant",
                content: data.answer,
                sources: data.sources,
                timestamp: new Date(),
            };

            setMessages((prev) => [...prev, botMessage]);
        } catch (error) {
            console.error("Chat error:", error);
            const errorMessage: Message = {
                id: (Date.now() + 1).toString(),
                role: "assistant",
                content: "Sorry, I encountered an error while processing your request. Please try again.",
                timestamp: new Date(),
            };
            setMessages((prev) => [...prev, errorMessage]);
        } finally {
            setLoading(false);
        }
    };

    const clearHistory = () => {
        setMessages([
            {
                id: "welcome",
                role: "assistant",
                content: "Chat history cleared. How can I help you now?",
                timestamp: new Date(),
            },
        ]);
    };

    return (
        <div className="flex flex-col h-[calc(100vh-2rem)] max-w-5xl mx-auto p-4 md:p-6">
            <div className="flex items-center justify-between mb-4">
                <div>
                    <h1 className="text-2xl font-bold text-gray-900">Study Buddy Chat</h1>
                    <p className="text-sm text-muted-foreground">Ask questions from your uploaded materials</p>
                </div>
                <Button variant="outline" size="sm" onClick={clearHistory} className="text-gray-500 hover:text-red-600">
                    <Trash2 className="h-4 w-4 mr-2" />
                    Clear Chat
                </Button>
            </div>

            <Card className="flex-1 flex flex-col overflow-hidden border-gray-200 shadow-sm bg-white">
                <CardContent className="flex-1 overflow-y-auto p-4 space-y-6 bg-gray-50/50">
                    {messages.map((message) => (
                        <div
                            key={message.id}
                            className={cn(
                                "flex w-full",
                                message.role === "user" ? "justify-end" : "justify-start"
                            )}
                        >
                            <div
                                className={cn(
                                    "flex max-w-[85%] md:max-w-[75%] gap-3",
                                    message.role === "user" ? "flex-row-reverse" : "flex-row"
                                )}
                            >
                                {/* Avatar */}
                                <div
                                    className={cn(
                                        "flex-shrink-0 h-8 w-8 rounded-full flex items-center justify-center shadow-sm",
                                        message.role === "user" ? "bg-violet-600 text-white" : "bg-emerald-600 text-white"
                                    )}
                                >
                                    {message.role === "user" ? <User className="h-5 w-5" /> : <Bot className="h-5 w-5" />}
                                </div>

                                {/* Message Bubble */}
                                <div className="flex flex-col gap-2">
                                    <div
                                        className={cn(
                                            "p-4 rounded-2xl shadow-sm text-sm leading-relaxed",
                                            message.role === "user"
                                                ? "bg-violet-600 text-white rounded-tr-none"
                                                : "bg-white border border-gray-100 text-gray-800 rounded-tl-none"
                                        )}
                                    >
                                        {message.role === "user" ? (
                                            <p>{message.content}</p>
                                        ) : (
                                            <div className="prose prose-sm max-w-none prose-p:my-1 prose-headings:my-2 prose-ul:my-1 prose-li:my-0.5 dark:prose-invert">
                                                <ReactMarkdown remarkPlugins={[remarkGfm]}>
                                                    {message.content}
                                                </ReactMarkdown>
                                            </div>
                                        )}
                                    </div>

                                    {/* Sources (only for assistant) */}
                                    {message.role === "assistant" && message.sources && message.sources.length > 0 && (
                                        <div className="bg-blue-50/50 border border-blue-100 rounded-lg p-3 text-xs">
                                            <div className="flex items-center gap-1.5 text-blue-700 font-semibold mb-2">
                                                <BookOpen className="h-3.5 w-3.5" />
                                                Sources Used
                                            </div>
                                            <div className="grid gap-2 sm:grid-cols-2">
                                                {message.sources.map((source, idx) => (
                                                    <div key={idx} className="bg-white/80 p-2 rounded border border-blue-100/50 shadow-sm">
                                                        <p className="font-medium text-gray-700 truncate" title={source.filename}>
                                                            {source.filename}
                                                        </p>
                                                        <div className="flex gap-2 text-gray-500 mt-0.5">
                                                            {source.page_number && <span>Page {source.page_number}</span>}
                                                            {source.chapter && source.chapter !== "Unknown" && (
                                                                <span className="truncate max-w-[100px]" title={source.chapter}>
                                                                    {source.chapter}
                                                                </span>
                                                            )}
                                                        </div>
                                                    </div>
                                                ))}
                                            </div>
                                        </div>
                                    )}

                                    <span className="text-[10px] text-gray-400 px-1">
                                        {message.timestamp.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                                    </span>
                                </div>
                            </div>
                        </div>
                    ))}

                    {loading && (
                        <div className="flex justify-start w-full">
                            <div className="flex max-w-[75%] gap-3">
                                <div className="flex-shrink-0 h-8 w-8 rounded-full bg-emerald-600 text-white flex items-center justify-center shadow-sm">
                                    <Bot className="h-5 w-5" />
                                </div>
                                <div className="bg-white border border-gray-100 p-4 rounded-2xl rounded-tl-none shadow-sm flex items-center gap-2">
                                    <Loader2 className="h-4 w-4 animate-spin text-emerald-600" />
                                    <span className="text-sm text-gray-500">Thinking...</span>
                                </div>
                            </div>
                        </div>
                    )}
                    <div ref={messagesEndRef} />
                </CardContent>

                <CardFooter className="p-4 bg-white border-t border-gray-100">
                    <form onSubmit={handleSendMessage} className="flex w-full gap-3">
                        <Input
                            placeholder="Ask a question about your geography notes..."
                            value={input}
                            onChange={(e) => setInput(e.target.value)}
                            disabled={loading}
                            className="flex-1 bg-gray-50 focus:bg-white transition-colors"
                        />
                        <Button
                            type="submit"
                            disabled={!input.trim() || loading}
                            className={cn(
                                "transition-all",
                                !input.trim() || loading ? "bg-gray-200 text-gray-400" : "bg-violet-600 hover:bg-violet-700 text-white"
                            )}
                        >
                            {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
                            <span className="sr-only">Send</span>
                        </Button>
                    </form>
                </CardFooter>
            </Card>
        </div>
    );
}
