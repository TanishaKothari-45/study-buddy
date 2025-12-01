"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Loader2, PenTool, BookOpen, FileText, CheckCircle } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { markdownComponents } from "@/components/ui/mermaid";
import { cn } from "@/lib/utils";

interface Source {
    filename: string;
    chapter?: string;
    section?: string;
    page_number?: number;
}

interface MainsAnswerResponse {
    question: string;
    answer: string;
    sources: Source[];
    word_count_actual: number;
}

export default function MainsAnswerPage() {
    const [loading, setLoading] = useState(false);
    const [question, setQuestion] = useState("");
    const [wordCount, setWordCount] = useState("250");
    const [result, setResult] = useState<MainsAnswerResponse | null>(null);

    const handleGenerate = async (e: React.FormEvent) => {
        e.preventDefault();
        if (!question.trim()) return;

        setLoading(true);
        setResult(null);

        try {
            const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8001";
            const res = await fetch(`${API_URL}/mains-answer/generate`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    question: question.trim(),
                    word_count: parseInt(wordCount)
                }),
            });

            if (!res.ok) throw new Error("Failed to generate answer");
            const data = await res.json();
            setResult(data);
        } catch (error) {
            console.error("Failed to generate answer:", error);
            alert("Failed to generate answer. Please try again.");
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="p-8 max-w-5xl mx-auto space-y-8">
            <div className="flex flex-col space-y-2">
                <h1 className="text-3xl font-bold tracking-tight text-gray-900">
                    Mains Answer Generation
                </h1>
                <p className="text-muted-foreground">
                    Generate comprehensive, structured UPSC Mains answers with current affairs integration.
                </p>
            </div>

            <div className="space-y-8">
                {/* Input Section */}
                <Card>
                    <CardHeader>
                        <CardTitle>1. Question Details</CardTitle>
                        <CardDescription>Enter the question and requirements.</CardDescription>
                    </CardHeader>
                    <CardContent>
                        <form onSubmit={handleGenerate} className="space-y-6">
                            <div className="space-y-2">
                                <Label htmlFor="question">Question</Label>
                                <Textarea
                                    id="question"
                                    placeholder="e.g., Discuss the impact of climate change on Indian agriculture..."
                                    className="min-h-[100px]"
                                    value={question}
                                    onChange={(e) => setQuestion(e.target.value)}
                                />
                            </div>

                            <div className="grid grid-cols-1 md:grid-cols-2 gap-6 items-end">
                                <div className="space-y-2">
                                    <Label htmlFor="word-count">Word Limit</Label>
                                    <Input
                                        id="word-count"
                                        type="number"
                                        min="100"
                                        max="1000"
                                        step="50"
                                        value={wordCount}
                                        onChange={(e) => setWordCount(e.target.value)}
                                    />
                                    <p className="text-xs text-muted-foreground">Standard limits: 150, 250 words</p>
                                </div>

                                <Button type="submit" className="w-full" disabled={loading || !question.trim()}>
                                    {loading ? (
                                        <>
                                            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                                            Generating...
                                        </>
                                    ) : (
                                        <>
                                            <PenTool className="mr-2 h-4 w-4" />
                                            Generate Answer
                                        </>
                                    )}
                                </Button>
                            </div>
                        </form>
                    </CardContent>
                </Card>

                {/* Output Section */}
                {result && (
                    <div className="space-y-6 animate-in fade-in slide-in-from-bottom-4 duration-500">
                        <Card className="bg-green-50/50 border-green-200 dark:bg-green-900/10 dark:border-green-900">
                            <CardContent className="pt-6">
                                <div className="flex items-center gap-2 text-green-700 dark:text-green-400 font-medium mb-2">
                                    <CheckCircle className="h-5 w-5" />
                                    Generation Complete
                                </div>
                                <div className="text-sm text-green-800 dark:text-green-300">
                                    <p>Actual Word Count: {result.word_count_actual}</p>
                                    <p>Sources Used: {result.sources.length}</p>
                                </div>
                            </CardContent>
                        </Card>

                        <Card className="h-full flex flex-col">
                            <CardHeader className="bg-muted/50 border-b">
                                <CardTitle className="text-lg font-medium leading-relaxed">
                                    {result.question}
                                </CardTitle>
                            </CardHeader>
                            <CardContent className="flex-1 p-6">
                                <div className="prose prose-sm md:prose-base max-w-none dark:prose-invert prose-headings:font-semibold prose-a:text-primary">
                                    <ReactMarkdown
                                        remarkPlugins={[remarkGfm]}
                                        components={markdownComponents}
                                    >
                                        {result.answer}
                                    </ReactMarkdown>
                                </div>

                                {result.sources.length > 0 && (
                                    <div className="mt-8 pt-6 border-t">
                                        <h4 className="text-sm font-semibold text-foreground mb-3 flex items-center gap-2">
                                            <BookOpen className="h-4 w-4" />
                                            References
                                        </h4>
                                        <div className="grid gap-2 sm:grid-cols-2">
                                            {result.sources.map((source, idx) => (
                                                <div key={idx} className="bg-muted/50 p-2 rounded text-xs border text-muted-foreground">
                                                    <p className="font-medium text-foreground truncate" title={source.filename}>
                                                        {source.filename}
                                                    </p>
                                                    <div className="flex gap-2 mt-0.5">
                                                        {source.page_number && <span>Page {source.page_number}</span>}
                                                        {source.chapter && (
                                                            <span className="truncate max-w-[150px]" title={source.chapter}>
                                                                {source.chapter}
                                                            </span>
                                                        )}
                                                    </div>
                                                </div>
                                            ))}
                                        </div>
                                    </div>
                                )}
                            </CardContent>
                        </Card>
                    </div>
                )}

                {!result && !loading && (
                    <div className="flex flex-col items-center justify-center p-12 border-2 border-dashed rounded-lg bg-muted/30 text-center">
                        <FileText className="h-16 w-16 text-muted-foreground mb-4" />
                        <h3 className="text-lg font-medium text-foreground">Ready to Generate</h3>
                        <p className="text-muted-foreground max-w-sm mt-2">
                            Enter a question and word limit to generate a structured Mains answer with introduction, body, conclusion, and diagrams.
                        </p>
                    </div>
                )}
            </div>
        </div>
    );
}
