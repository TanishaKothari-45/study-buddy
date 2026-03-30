"use client";

import { useState, useRef, useEffect } from "react";
import dynamic from "next/dynamic";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Send, User, Bot, Loader2, BookOpen, AlertCircle, Plus, GraduationCap } from "lucide-react";
import { cn } from "@/lib/utils";
import { TypewriterEffect } from "@/components/ui/typewriter-effect";
import { useChatStore } from "@/stores";
import { API_URL } from "@/lib/api";
import { authFetch, showToast } from "@/lib/authHandler";

// N2: Lazy-load heavy deps (~1.6MB total) so they don't block the initial render
const ReactMarkdown = dynamic(() => import("react-markdown"), { ssr: false });
import remarkGfm from "remark-gfm";
import type { Components } from "react-markdown";
import { markdownComponents, urlTransform } from "@/components/ui/mermaid";


export default function ChatPage() {
    // Persisted state from store
    const {
        messages,
        sessionId,
        addMessage,
        appendToMessageContent,
        setMessageSources,
        updateMessageContent,
        startNewChat
    } = useChatStore();

    // Local UI state
    const [input, setInput] = useState("");
    const [loading, setLoading] = useState(false);
    const [mounted, setMounted] = useState(false);
    const [subject, setSubject] = useState<string>("Geography");
    const messagesEndRef = useRef<HTMLDivElement>(null);
    // F1: AbortController to cancel in-flight streams on re-send or unmount
    const abortRef = useRef<AbortController | null>(null);

    useEffect(() => {
        setMounted(true);
        // F1: Abort any dangling stream on unmount
        return () => { abortRef.current?.abort(); };
    }, []);

    const scrollToBottom = () => {
        messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
    };

    // Only scroll to bottom on initial load or when user sends a message
    // NOT when streaming chunks arrive (to prevent jittery scrolling)
    useEffect(() => {
        if (messages.length > 0) {
            scrollToBottom();
        }
    }, [messages.length]); // Only trigger when message count changes, not content updates

    const handleSendMessage = async (e?: React.FormEvent) => {
        e?.preventDefault();
        if (!input.trim() || loading) return;

        const userMessage = {
            id: Date.now().toString(),
            role: "user" as const,
            content: input.trim(),
            timestamp: new Date().toISOString(),
        };

        addMessage(userMessage);
        setInput("");
        setLoading(true);

        // Create placeholder for streaming response
        const botMessageId = (Date.now() + 1).toString();
        const botMessage = {
            id: botMessageId,
            role: "assistant" as const,
            content: "",
            sources: [],
            timestamp: new Date().toISOString(),
        };
        addMessage(botMessage);

        // F1: Cancel any previous in-flight stream before starting a new one
        abortRef.current?.abort();
        abortRef.current = new AbortController();
        const signal = abortRef.current.signal;

        try {
            // Use streaming endpoint
            const res = await authFetch(`${API_URL}/query/stream`, {
                method: "POST",
                signal,
                headers: {
                    "Content-Type": "application/json",
                },
                body: JSON.stringify({
                    question: userMessage.content,
                    subject: subject,
                    session_id: sessionId,
                    k: 5,
                }),
            });

            if (!res.ok) {
                throw new Error("Failed to get response");
            }

            // Read the stream
            const reader = res.body?.getReader();
            const decoder = new TextDecoder();

            if (!reader) {
                throw new Error("No reader available");
            }

            let buffer = "";
            while (true) {
                const { done, value } = await reader.read();
                if (done) break;

                buffer += decoder.decode(value, { stream: true });
                const lines = buffer.split("\n");
                buffer = lines.pop() || "";

                for (const line of lines) {
                    if (line.startsWith("data: ")) {
                        try {
                            const data = JSON.parse(line.slice(6));

                            if (data.type === "sources") {
                                setMessageSources(botMessageId, data.sources);
                            } else if (data.type === "content") {
                                // Append content chunk — React 18 auto-batches this in async context
                                appendToMessageContent(botMessageId, data.content);

                            } else if (data.type === "done") {
                                break;
                            } else if (data.type === "error") {
                                throw new Error(data.error);
                            }
                        } catch (e) {
                            showToast("Error parsing response", "error");
                        }
                    }
                }
            }
        } catch (error) {
            if ((error as Error)?.name === 'AbortError') return; // navigation away — ignore
            const message = error instanceof Error ? error.message : "Chat error occurred";
            showToast(message, "error");
            updateMessageContent(botMessageId, "Sorry, I encountered an error while processing your request. Please try again.");
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="flex flex-col h-[calc(100vh-2rem)] max-w-5xl mx-auto p-4 md:p-6">
            <div className="flex items-center justify-between mb-4">
                <div>
                    <h1 className="text-2xl font-bold tracking-tight text-foreground">Ask Away</h1>
                    <p className="text-sm text-muted-foreground">Chat with your AI study buddy about {subject}</p>
                </div>
                <div className="flex items-center gap-3">
                    {/* Subject Dropdown */}
                    <div className="flex items-center gap-2">
                        <GraduationCap className="h-4 w-4 text-muted-foreground" />
                        <Select value={subject} onValueChange={setSubject}>
                            <SelectTrigger className="w-[140px] h-9 text-sm">
                                <SelectValue placeholder="Subject" />
                            </SelectTrigger>
                            <SelectContent>
                                <SelectItem value="Geography">Geography</SelectItem>
                                <SelectItem value="History">History</SelectItem>
                            </SelectContent>
                        </Select>
                    </div>
                    <Button variant="outline" size="sm" onClick={startNewChat} className="text-gray-500 hover:text-violet-600">
                        <Plus className="h-4 w-4 mr-2" />
                        New Chat
                    </Button>
                </div>
            </div>

            <Card className="flex-1 flex flex-col overflow-hidden border-gray-200 shadow-sm bg-white dark:bg-card">
                <CardContent className="flex-1 overflow-y-auto p-4 space-y-6 bg-gray-50/50 dark:bg-background/50">
                    {messages.map((message, index) => (
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
                                                {/* 
                                                    Smart Loader Logic:
                                                    1. If loading AND content is empty -> Show "Thinking..." loader INSIDE bubble
                                                    2. If loading AND content exists -> Show TypewriterEffect (streaming)
                                                    3. If not loading -> Show static markdown
                                                */}
                                                {index === messages.length - 1 && loading && !message.content ? (
                                                    <div className="flex items-center gap-2 text-gray-400 italic">
                                                        <Loader2 className="h-3 w-3 animate-spin" />
                                                        <span>Thinking...</span>
                                                    </div>
                                                ) : index === messages.length - 1 && loading ? (
                                                    <TypewriterEffect content={message.content} />
                                                ) : (
                                                    <ReactMarkdown
                                                        remarkPlugins={[remarkGfm]}
                                                        components={markdownComponents}
                                                        urlTransform={urlTransform}
                                                    >
                                                        {message.content}
                                                    </ReactMarkdown>
                                                )}
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

                                    {mounted && (
                                        <span className="text-[10px] text-gray-400 px-1">
                                            {new Date(message.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                                        </span>
                                    )}
                                </div>
                            </div>
                        </div>
                    ))}


                    <div ref={messagesEndRef} />
                </CardContent>

                <CardFooter className="p-4 bg-white border-t border-gray-100">
                    <form onSubmit={handleSendMessage} className="flex w-full gap-3">
                        <Input
                            placeholder={`Ask a question about your ${subject.toLowerCase()} notes...`}
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
