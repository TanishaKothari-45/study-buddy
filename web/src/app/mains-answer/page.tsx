"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Loader2, PenTool, BookOpen, FileText, CheckCircle, AlertCircle, ChevronDown, Minimize2 } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { markdownComponents, urlTransform } from "@/components/ui/mermaid";
import { useMainsAnswerStore } from "@/stores";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { API_URL } from "@/lib/api";

export default function MainsAnswerPage() {
    // Local state for UI only
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [showCompressed, setShowCompressed] = useState(true); // Compressed answer accordion
    const [showOriginal, setShowOriginal] = useState(false); // Original answer accordion

    // Persisted state from store (question, wordCount, and result)
    const { question, wordCount, result, setQuestion, setWordCount, setResult } = useMainsAnswerStore();

    const handleGenerate = async (e: React.FormEvent) => {
        e.preventDefault();
        if (!question.trim()) return;

        setLoading(true);
        setError(null);
        setResult(null); // Clear previous answer immediately

        try {
            const res = await fetch(`${API_URL}/mains-answer/generate`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    question: question.trim(),
                    word_count: parseInt(wordCount)
                }),
            });

            if (!res.ok) {
                const errData = await res.json().catch(() => ({}));
                throw new Error(errData.detail || "Failed to generate answer");
            }

            const data = await res.json();
            setResult(data); // Save to store - persists across tab switches
        } catch (err) {
            const message = err instanceof Error ? err.message : "Failed to generate answer";
            setError(message);
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="p-8 max-w-5xl mx-auto space-y-8">
            <div className="flex flex-col space-y-2">
                <h1 className="text-3xl font-bold tracking-tight text-foreground">
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

                {/* Error Alert */}
                {error && (
                    <Alert variant="destructive">
                        <AlertCircle className="h-4 w-4" />
                        <AlertDescription>{error}</AlertDescription>
                    </Alert>
                )}

                {/* Output Section */}
                {result && (
                    <div className="space-y-6 animate-in fade-in slide-in-from-bottom-4 duration-500">
                        {/* Status Card */}
                        <Card className="bg-green-50/50 border-green-200 dark:bg-green-900/10 dark:border-green-900">
                            <CardContent className="pt-6">
                                <div className="flex items-center gap-2 text-green-700 dark:text-green-400 font-medium mb-2">
                                    <CheckCircle className="h-5 w-5" />
                                    Generation Complete
                                    {result.compressed_answer && (
                                        <span className="ml-2 inline-flex items-center gap-1 text-xs bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400 px-2 py-0.5 rounded-full">
                                            <Minimize2 className="h-3 w-3" />
                                            Compressed
                                        </span>
                                    )}
                                </div>
                                <div className="text-sm text-green-800 dark:text-green-500 space-y-1">
                                    <p>Original Word Count: {result.word_count_actual}</p>
                                    {result.word_count_compressed && (
                                        <p>Compressed Word Count: {result.word_count_compressed}
                                            <span className="text-green-600 dark:text-green-400 ml-1">
                                                ({Math.round((1 - result.word_count_compressed / result.word_count_actual) * 100)}% reduced)
                                            </span>
                                        </p>
                                    )}
                                    <p>Sources Used: {result.sources.length}</p>
                                </div>
                            </CardContent>
                        </Card>

                        {/* Question Title Card */}
                        <Card className="bg-muted/30">
                            <CardHeader className="pb-4">
                                <CardTitle className="text-lg font-medium leading-relaxed">
                                    {result.question}
                                </CardTitle>
                            </CardHeader>
                        </Card>

                        {/* Compressed Answer Accordion (shown if compression was applied) */}
                        {result.compressed_answer && (
                            <Card>
                                <button
                                    onClick={() => setShowCompressed(!showCompressed)}
                                    className="w-full flex items-center justify-between p-4 text-left hover:bg-muted/30 transition-colors border-b"
                                >
                                    <span className="font-medium text-foreground flex items-center gap-2">
                                        <Minimize2 className="h-4 w-4 text-blue-500" />
                                        Compressed Answer ({result.word_count_compressed} words)
                                    </span>
                                    <ChevronDown className={`h-4 w-4 text-muted-foreground transition-transform ${showCompressed ? 'rotate-180' : ''}`} />
                                </button>
                                {showCompressed && (
                                    <CardContent className="p-6">
                                        <div className="prose prose-sm md:prose-base max-w-none dark:prose-invert prose-headings:font-semibold prose-a:text-primary">
                                            <ReactMarkdown
                                                remarkPlugins={[remarkGfm]}
                                                components={markdownComponents}
                                                urlTransform={urlTransform}
                                            >
                                                {result.compressed_answer}
                                            </ReactMarkdown>
                                        </div>
                                    </CardContent>
                                )}
                            </Card>
                        )}

                        {/* Original Answer Accordion */}
                        <Card className={result.compressed_answer ? "border-dashed" : ""}>
                            <button
                                onClick={() => setShowOriginal(!showOriginal)}
                                className="w-full flex items-center justify-between p-4 text-left hover:bg-muted/30 transition-colors border-b"
                            >
                                <span className="font-medium text-foreground">
                                    {result.compressed_answer ? "Original Answer" : "Generated Answer"} ({result.word_count_actual} words)
                                </span>
                                <ChevronDown className={`h-4 w-4 text-muted-foreground transition-transform ${(showOriginal || !result.compressed_answer) ? 'rotate-180' : ''}`} />
                            </button>
                            {(showOriginal || !result.compressed_answer) && (
                                <CardContent className="p-6">
                                    <div className="prose prose-sm md:prose-base max-w-none dark:prose-invert prose-headings:font-semibold prose-a:text-primary">
                                        <ReactMarkdown
                                            remarkPlugins={[remarkGfm]}
                                            components={markdownComponents}
                                            urlTransform={urlTransform}
                                        >
                                            {result.answer}
                                        </ReactMarkdown>
                                    </div>
                                </CardContent>
                            )}
                        </Card>

                        {/* References Card */}
                        {result.sources.length > 0 && (
                            <Card>
                                <CardContent className="pt-6">
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
                                </CardContent>
                            </Card>
                        )}
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

                {!result && loading && (
                    <div className="flex flex-col items-center justify-center p-12 border-2 border-dashed rounded-lg bg-muted/30 text-center">
                        <Loader2 className="h-16 w-16 text-primary animate-spin mb-4" />
                        <h3 className="text-lg font-medium text-foreground">Generating Answer...</h3>
                        <p className="text-muted-foreground max-w-sm mt-2">
                            Please wait while we generate a comprehensive answer with relevant sources.
                        </p>
                    </div>
                )}
            </div>
        </div>
    );
}
