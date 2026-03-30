"use client";

import { useState, useRef, useEffect } from "react";
import dynamic from "next/dynamic";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardFooter } from "@/components/ui/card";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Send, User, Bot, BookOpen, Plus, GraduationCap } from "lucide-react";
import { InlineLoader } from "@/components/ui/loader";
import { cn } from "@/lib/utils";
import { TypewriterEffect } from "@/components/ui/typewriter-effect";
import { useChatStore } from "@/stores";
import { API_URL } from "@/lib/api";
import { authFetch, showToast } from "@/lib/authHandler";

const ReactMarkdown = dynamic(() => import("react-markdown"), { ssr: false });
import remarkGfm from "remark-gfm";
import type { Components } from "react-markdown";
import { markdownComponents, urlTransform } from "@/components/ui/mermaid";
import { PageContainer } from "@/components/layout/PageContainer";

export default function ChatPage() {
    const {
        messages,
        sessionId,
        addMessage,
        appendToMessageContent,
        setMessageSources,
        updateMessageContent,
        startNewChat
    } = useChatStore();

    const [input, setInput] = useState("");
    const [loading, setLoading] = useState(false);
    const [mounted, setMounted] = useState(false);
    const [subject, setSubject] = useState<string>("Geography");
    const messagesEndRef = useRef<HTMLDivElement>(null);
    const abortRef = useRef<AbortController | null>(null);

    useEffect(() => {
        setMounted(true);
        return () => { abortRef.current?.abort(); };
    }, []);

    const scrollToBottom = () => {
        messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
    };

    useEffect(() => {
        if (messages.length > 0) {
            scrollToBottom();
        }
    }, [messages.length]);

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

        const botMessageId = (Date.now() + 1).toString();
        const botMessage = {
            id: botMessageId,
            role: "assistant" as const,
            content: "",
            sources: [],
            timestamp: new Date().toISOString(),
        };
        addMessage(botMessage);

        abortRef.current?.abort();
        abortRef.current = new AbortController();
        const signal = abortRef.current.signal;

        try {
            const res = await authFetch(`${API_URL}/query/stream`, {
                method: "POST",
                signal,
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    question: userMessage.content,
                    subject: subject,
                    session_id: sessionId,
                    k: 5,
                }),
            });

            if (!res.ok) throw new Error("Failed to get response");

            const reader = res.body?.getReader();
            const decoder = new TextDecoder();

            if (!reader) throw new Error("No reader available");

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
            if ((error as Error)?.name === 'AbortError') return;
            const message = error instanceof Error ? error.message : "Chat error occurred";
            showToast(message, "error");
            updateMessageContent(botMessageId, "Something went wrong — try again.");
        } finally {
            setLoading(false);
        }
    };

    return (
        <PageContainer
            title="Ask away"
            description={`Chat with your study buddy about ${subject}`}
        >
            <div className="flex flex-col h-[calc(100vh-12rem)] space-y-4">
                {/* Header Actions */}
                <div className="flex items-center justify-end w-full animate-fade-up">
                    <div className="flex items-center gap-2">
                        <div className="flex items-center gap-1.5">
                            <GraduationCap className="h-4 w-4 text-[var(--text-muted)]" />
                            <Select value={subject} onValueChange={setSubject}>
                                <SelectTrigger className="w-[130px] h-8 text-xs border-[var(--card-border)]">
                                    <SelectValue placeholder="Subject" />
                                </SelectTrigger>
                                <SelectContent>
                                    <SelectItem value="Geography">Geography</SelectItem>
                                    <SelectItem value="History">History</SelectItem>
                                </SelectContent>
                            </Select>
                        </div>
                        <Button variant="outline" size="sm" onClick={startNewChat} className="text-xs h-8 px-3">
                            <Plus className="h-3.5 w-3.5 mr-1.5" />
                            New chat
                        </Button>
                    </div>
                </div>

                {/* Message list */}
                <Card className="flex-1 flex flex-col overflow-hidden animate-fade-up animate-fade-up-delay-1">
                    <CardContent className="flex-1 overflow-y-auto p-4 md:p-6 space-y-5 bg-[var(--bg-secondary)]/40">
                        {messages.length === 0 && (
                            <div className="flex flex-col items-center justify-center h-full text-center py-16 gap-3">
                                <div className="w-12 h-12 rounded-full bg-amber-100 dark:bg-amber-900/30 flex items-center justify-center">
                                    <Bot className="h-6 w-6 text-amber-600" />
                                </div>
                                <p className="text-sm font-medium text-[var(--text)]">Ready to help</p>
                                <p className="text-xs text-[var(--text-muted)] max-w-xs leading-relaxed">
                                    Ask anything about your study materials. I'll search your uploaded notes to answer.
                                </p>
                            </div>
                        )}

                        {messages.map((message, index) => (
                            <div
                                key={message.id}
                                className={cn(
                                    "flex w-full",
                                    message.role === "user" ? "justify-end" : "justify-start"
                                )}
                            >
                                <div className={cn(
                                    "flex max-w-[85%] md:max-w-[75%] gap-3",
                                    message.role === "user" ? "flex-row-reverse" : "flex-row"
                                )}>
                                    {/* Avatar */}
                                    <div className={cn(
                                        "flex-shrink-0 h-7 w-7 rounded-full flex items-center justify-center",
                                        message.role === "user"
                                            ? "bg-amber-600 text-white"
                                            : "bg-[var(--bg-tertiary)] text-[var(--text-muted)] border border-[var(--card-border)]"
                                    )}>
                                        {message.role === "user"
                                            ? <User className="h-4 w-4" />
                                            : <Bot className="h-4 w-4" />
                                        }
                                    </div>

                                    {/* Bubble */}
                                    <div className="flex flex-col gap-1.5">
                                        <div className={cn(
                                            "px-4 py-3 rounded-xl text-sm leading-relaxed",
                                            message.role === "user"
                                                ? "bg-amber-600 text-white rounded-tr-sm"
                                                : "bg-[var(--card)] border border-[var(--card-border)] text-[var(--text)] rounded-tl-sm"
                                        )}>
                                            {message.role === "user" ? (
                                                <p>{message.content}</p>
                                            ) : (
                                                <div className="prose prose-sm max-w-none prose-p:my-1 prose-headings:my-2 prose-ul:my-1 prose-li:my-0.5 dark:prose-invert">
                                                    {index === messages.length - 1 && loading && !message.content ? (
                                                        <div className="flex items-center gap-2 text-[var(--text-muted)] italic text-xs">
                                                            <InlineLoader />
                                                            <span>Finding the best context for this...</span>
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

                                        {/* Sources */}
                                        {message.role === "assistant" && message.sources && message.sources.length > 0 && (
                                            <div className="bg-[var(--bg-secondary)] border border-[var(--card-border)] rounded-lg p-3 text-xs">
                                                <div className="flex items-center gap-1.5 text-[var(--text-muted)] font-medium mb-2">
                                                    <BookOpen className="h-3 w-3" />
                                                    Sources used
                                                </div>
                                                <div className="grid gap-1.5 sm:grid-cols-2">
                                                    {message.sources.map((source, idx) => (
                                                        <div key={idx} className="bg-[var(--bg)] p-2 rounded-lg border border-[var(--card-border)]">
                                                            <p className="font-medium text-[var(--text)] truncate" title={source.filename}>
                                                                {source.filename}
                                                            </p>
                                                            <div className="flex gap-2 text-[var(--text-faint)] mt-0.5">
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

                                        {/* Timestamp */}
                                        {mounted && (
                                            <span className="text-[10px] text-[var(--text-faint)] px-1">
                                                {new Date(message.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                                            </span>
                                        )}
                                    </div>
                                </div>
                            </div>
                        ))}

                        <div ref={messagesEndRef} />
                    </CardContent>

                    {/* Input */}
                    <CardFooter className="p-4 bg-[var(--bg)] border-t border-[var(--card-border)]">
                        <form onSubmit={handleSendMessage} className="flex w-full gap-2">
                            <Input
                                placeholder={`Ask about your ${subject.toLowerCase()} notes...`}
                                value={input}
                                onChange={(e) => setInput(e.target.value)}
                                disabled={loading}
                                className="flex-1"
                            />
                            <Button
                                type="submit"
                                disabled={!input.trim() || loading}
                                size="icon"
                                className={cn(
                                    "h-9 w-9 flex-shrink-0",
                                    (!input.trim() || loading) && "opacity-40"
                                )}
                            >
                                {loading
                                    ? <InlineLoader />
                                    : <Send className="h-4 w-4" />
                                }
                            </Button>
                        </form>
                    </CardFooter>
                </Card>
            </div>
        </PageContainer>
    );
}
