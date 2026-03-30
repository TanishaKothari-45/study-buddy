"use client";

import { useState, useEffect, useRef } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { PenTool, BookOpen, FileText, CheckCircle, AlertCircle, ChevronDown, Minimize2, RefreshCw, History } from "lucide-react";
import { PageLoader, InlineLoader } from "@/components/ui/loader";
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from "@/components/ui/select";
import dynamic from "next/dynamic";
import remarkGfm from "remark-gfm";
import { markdownComponents, urlTransform } from "@/components/ui/mermaid";
// N2: Lazy-load react-markdown (~200KB) to not block first paint
const ReactMarkdown = dynamic(() => import("react-markdown"), { ssr: false });

import { useMainsAnswerStore } from "@/stores";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { useAuth } from "@/context/AuthContext";
import { PageContainer } from "@/components/layout/PageContainer";
import ApiKeyBanner from "@/components/layout/ApiKeyBanner";
import api, { ApiError } from "@/lib/apiClient";
import { cn } from "@/lib/utils";
import { POLL_INTERVAL_MS, POLL_RETRY_INTERVAL_MS } from "@/lib/constants"; // C2

interface MainsAnswerResponse {
    question: string;
    answer: string;
    compressed_answer?: string | null;
    sources: Array<{ filename: string; chapter?: string; section?: string; page_number?: number; chunk_id?: string }>;
    word_count_actual: number;
    word_count_compressed?: number | null;
}

export default function MainsAnswerPage() {
    const { user, refreshUser, isApiKeyValid, setIsApiKeyValid, verifyApiKey } = useAuth();
    const [showBanner, setShowBanner] = useState(false);

    // Persist state from store
    const {
        question,
        wordCount,
        gsPaper,
        subject,
        result,
        error,
        jobId,
        jobStatus,
        history,
        historyHasMore,
        historySearch,
        isLoadingHistory,
        setQuestion,
        setWordCount,
        setGsPaper,
        setSubject,
        setResult,
        setError,
        setJobId,
        setJobStatus,
        setHistorySearch,
        fetchHistory,
        clear
    } = useMainsAnswerStore();

    // Derived state
    const loading = jobStatus === 'pending' || jobStatus === 'processing' || jobStatus === 'queued';

    // Status message based on job status
    const getStatusMessage = () => {
        if (jobStatus === 'queued') return "Waiting in queue...";
        if (jobStatus === 'processing') return "Writing your answer...";
        return "Generating Answer...";
    };

    // UI-only state
    const [showCompressed, setShowCompressed] = useState(true);
    const [showOriginal, setShowOriginal] = useState(false);

    // ... history UI state ...
    const [historyOpen, setHistoryOpen] = useState(false);
    const [historyModalOpen, setHistoryModalOpen] = useState(false);
    const [historyModalLoading, setHistoryModalLoading] = useState(false);
    const [historyModalError, setHistoryModalError] = useState<string | null>(null);
    const [historyModalAnswer, setHistoryModalAnswer] = useState<MainsAnswerResponse | null>(null);
    const [historyModalItem, setHistoryModalItem] = useState<any | null>(null);
    const [modalShowCompressed, setModalShowCompressed] = useState(false);
    const [modalShowOriginal, setModalShowOriginal] = useState(false);
    const historyRef = useRef<HTMLDivElement | null>(null);

    // Polling Ref to avoid closure staleness
    const activeJobId = useRef<string | null>(null);
    // F5: Store timer ID so we can cancel it on unmount (prevents memory leak)
    const pollTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

    // Sync ref with store
    useEffect(() => {
        activeJobId.current = jobId;
    }, [jobId]);

    // Resume polling on mount if active
    useEffect(() => {
        if (jobId && (jobStatus === 'pending' || jobStatus === 'processing' || jobStatus === 'queued')) {
            pollStatus(jobId);
        }
        // F5: Cleanup — cancel any in-flight poll timer on unmount
        return () => {
            if (pollTimerRef.current) clearTimeout(pollTimerRef.current);
        };
    }, []);

    // Proactively show banner removed - on-demand only

    // ... helper functions ...

    const stripHeavyContent = (
        text?: string | null,
        opts: { removeAllMaps?: boolean; stripImages?: boolean } = {}
    ) => {
        if (!text) return "";
        const { removeAllMaps = false, stripImages = false } = opts;
        let cleaned = text.replace(/```map-json[\s\S]*?```/g, removeAllMaps ? "" : "[map omitted]");
        if (stripImages) {
            cleaned = cleaned.replace(/!\[[^\]]*\]\(data:image[^\)]*\)/g, "[image omitted]");
        }
        return cleaned;
    };

    // Extract first data-image (svg/png) uri from text for on-demand rendering (currently unused)
    const extractMapDataUri = (text?: string | null): string | null => {
        if (!text) return null;
        const match = text.match(/data:image\/[^;]+;base64,[A-Za-z0-9+/=]+/m);
        return match ? match[0] : null;
    };

    // Lighter markdown components for modal
    const modalMarkdownComponents = {
        ...markdownComponents,
        img: ({ src, alt }: any) => {
            if (!src) return null;
            const isDataImg = src.startsWith("data:image/");
            const isPng = src.includes("image/png");
            const isSvg = src.includes("image/svg+xml");
            if (isDataImg && isPng) {
                return (
                    <img
                        src={src}
                        alt={alt || "Map"}
                        className="max-h-[400px] w-auto max-w-full"
                        loading="lazy"
                    />
                );
            }
            if (isDataImg && isSvg) {
                return (
                    <div className="text-xs text-muted-foreground italic">
                        [SVG map not shown in modal]
                    </div>
                );
            }
            return (
                <a
                    href={src}
                    target="_blank"
                    rel="noreferrer"
                    className="text-primary underline text-sm"
                >
                    {alt || "Open image"}
                </a>
            );
        },
    };



    // Fetch history on mount and with debounce for search
    useEffect(() => {
        const timer = setTimeout(() => {
            fetchHistory({ reset: true });
        }, 300);

        return () => clearTimeout(timer);
    }, [historySearch, fetchHistory]);

    // Close history dropdown on outside click
    useEffect(() => {
        if (!historyOpen) return;
        const handleClickOutside = (event: MouseEvent) => {
            if (historyRef.current && !historyRef.current.contains(event.target as Node)) {
                setHistoryOpen(false);
            }
        };
        document.addEventListener("mousedown", handleClickOutside);
        return () => document.removeEventListener("mousedown", handleClickOutside);
    }, [historyOpen]);

    const pollStatus = async (id: string) => {
        if (activeJobId.current !== id) return;

        try {
            const data = await api.get<{ status: string, result?: MainsAnswerResponse, error?: string }>(`/mains-answer/status/${id}`);

            if (activeJobId.current !== id) return;

            if (data.status === 'completed') {
                if (data.result) {
                    // Success
                    const normalizedData = {
                        ...data.result,
                        compressed_answer: data.result.compressed_answer ?? null,
                        word_count_compressed: data.result.word_count_compressed ?? null,
                    };

                    if (
                        normalizedData.compressed_answer &&
                        normalizedData.answer &&
                        normalizedData.compressed_answer.trim() === normalizedData.answer.trim()
                    ) {
                        normalizedData.compressed_answer = null;
                        normalizedData.word_count_compressed = null;
                    }

                    setResult(normalizedData);
                    fetchHistory({ reset: true }); // Refresh history
                    // setJobStatus('completed') handled by setResult
                    setJobId(null);
                } else {
                    // Completed but no result - treat as error to avoid stuck UI
                    setError("Generation completed but returned no data.");
                    setJobId(null);
                }
            } else if (data.status === 'failed') {
                const cleanedError = data.error || "Generation failed";
                setError(cleanedError);
                setJobStatus('failed');

                // Show banner if it's an API key error
                if (cleanedError.toLowerCase().includes("api key") || cleanedError.includes("API_KEY_INVALID")) {
                    setIsApiKeyValid('invalid');
                    setShowBanner(true);
                }
                return;
            } else {
                // Update status if needed (e.g. queued -> processing)
                if (data.status === 'processing' && jobStatus !== 'processing') setJobStatus('processing');

                // Continue polling
                pollTimerRef.current = setTimeout(() => pollStatus(id), POLL_INTERVAL_MS); // C2

            }
        } catch (err) {
            if (activeJobId.current !== id) return;
            console.error("Polling error:", err);
            pollTimerRef.current = setTimeout(() => pollStatus(id), POLL_RETRY_INTERVAL_MS); // C2

        }
    };

    const handleCancel = async () => {
        if (!jobId) return;
        const idToCancel = jobId;

        // Optimistic update
        setJobId(null);
        setJobStatus('idle');
        setError("Generation cancelled");

        try {
            await api.post(`/jobs/${idToCancel}/cancel`);
        } catch (err) {
            console.error("Cancel failed:", err);
        }
    };

    const handleGenerate = async (e?: React.FormEvent) => {
        e?.preventDefault();
        if (!question.trim()) return;

        // Clear previous state to prevent localStorage quota issues
        // This ensures old result is removed before generating new one
        clear();

        // Strict guard: check if user has Gemini API key
        // TODO: REVERT FOR PROD — remove the hasLocalKey bypass below and restore:
        //   if (!user || user.has_gemini_api_key === false || isApiKeyValid === 'invalid') {
        // No-auth India mode: if a local key exists in localStorage, skip this check
        const hasLocalKey = typeof window !== 'undefined' && !!localStorage.getItem('gemini_api_key');
        if (!hasLocalKey && (!user || user.has_gemini_api_key === false || isApiKeyValid === 'invalid')) {
            // Prioritize "missing key" message over "invalid" just in case state is mixed
            const msg = (user && user.has_gemini_api_key === false)
                ? "Please set your Gemini API key in Settings before generating an answer."
                : "Your Gemini API key is invalid. Please update it in Settings.";

            setError(msg);
            setShowBanner(true);
            return;
        }

        // On-demand validation if status is unknown
        if (isApiKeyValid === 'unknown') {
            setJobStatus('queued');
            setError(null);
            const isValid = await verifyApiKey();
            if (!isValid) {
                setError("Your Gemini API key is invalid. Please update it in Settings.");
                setShowBanner(true);
                setJobStatus('idle');
                return;
            }
        }

        setJobStatus('queued');
        setError(null);
        setResult(null);

        try {
            const data = await api.post<{ job_id: string, status: string, message: string }>('/mains-answer/generate', {
                question: question.trim(),
                word_count: parseInt(wordCount),
                gs_paper: gsPaper || undefined,
                subject: subject || undefined
            });

            if (data.job_id) {
                activeJobId.current = data.job_id;
                setJobId(data.job_id);
                setJobStatus('queued'); // Start as queued
                pollStatus(data.job_id);
            } else {
                throw new Error("No job ID returned");
            }

        } catch (err) {
            setJobStatus('failed');
            let message = "Failed to start generation";
            if (err instanceof ApiError) {
                message = err.message;
            } else if (err instanceof Error) {
                message = err.message;
            }
            setError(message);
            if (message.toLowerCase().includes("api key") || message.toLowerCase().includes("invalid") || message.toLowerCase().includes("gemini")) {
                setShowBanner(true);
            }
        }
    };

    const handleHistoryClick = async (item: any) => {
        setHistoryOpen(false);
        setHistoryModalOpen(true);
        setHistoryModalLoading(true);
        setHistoryModalError(null);
        setHistoryModalAnswer(null);
        setHistoryModalItem(item);
        setModalShowCompressed(true);
        setModalShowOriginal(true);

        try {
            const wc = item.word_count || 250;
            const data = await api.get<MainsAnswerResponse>(`/mains-answer/history/answer?question=${encodeURIComponent(item.question)}&word_count=${wc}`);
            const normalizedData = {
                ...data,
                compressed_answer: data.compressed_answer ?? null,
                word_count_compressed: data.word_count_compressed ?? null,
            };
            if (
                normalizedData.compressed_answer &&
                normalizedData.answer &&
                normalizedData.compressed_answer.trim() === normalizedData.answer.trim()
            ) {
                normalizedData.compressed_answer = null;
                normalizedData.word_count_compressed = null;
            }
            setHistoryModalAnswer(normalizedData);
        } catch (err) {
            let message = "Failed to load cached answer";
            if (err instanceof ApiError) {
                message = err.message;
            } else if (err instanceof Error) {
                message = err.message;
            }
            setHistoryModalError(message);
        } finally {
            setHistoryModalLoading(false);
        }
    };

    // Filter subjects based on GS Paper
    const GS_TO_SUBJECTS: Record<string, string[]> = {
        "GS1": ["History", "Geography", "Social Issues"],
        "GS2": ["Constitution", "Administration", "International Relations", "Social Justice"],
        "GS3": ["Economic Development", "Agriculture", "Technology", "Environment", "Disaster Management", "Internal Security"],
        "GS4": ["Foundational Values", "Thinkers", "Governance & Ethics", "Case Studies"]
    };

    const ALL_SUBJECTS = Array.from(new Set(Object.values(GS_TO_SUBJECTS).flat())).sort();

    const availableSubjects = gsPaper ? GS_TO_SUBJECTS[gsPaper] || ALL_SUBJECTS : ALL_SUBJECTS;

    // Reset subject if not valid for selected GS Paper
    useEffect(() => {
        if (gsPaper && subject && !GS_TO_SUBJECTS[gsPaper]?.includes(subject)) {
            setSubject("");
        }
    }, [gsPaper, subject, setSubject]);

    return (
        <PageContainer
            title="Let's write your answer"
            description="Provide a question and we'll craft a structured, comprehensive answer with relevant datasets and diagrams."
        >
            <div className="w-full space-y-8">
                {/* API Key Banner */}
                <ApiKeyBanner
                    showBanner={showBanner}
                    onKeySet={() => {
                        setShowBanner(false);
                        setError(null);
                        // Skip verification since the key was just validated during save
                        refreshUser(true);
                    }}
                />

                {/* Actions: New Answer and History */}
                <div className="flex items-center justify-end gap-3 w-full mb-2">
                    {result && (
                        <Button
                            variant="outline"
                            size="sm"
                            onClick={() => clear()}
                            className="flex items-center gap-2"
                        >
                            <RefreshCw className="h-4 w-4" />
                            New Answer
                        </Button>
                    )}
                    {/* History button - always visible */}
                    <div className="relative" ref={historyRef}>
                        <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => setHistoryOpen(!historyOpen)}
                            className="flex items-center gap-2"
                            disabled={history.length === 0 && !isLoadingHistory}
                        >
                            {isLoadingHistory ? (
                                <InlineLoader />
                            ) : (
                                <History className="h-4 w-4" />
                            )}
                            History {history.length > 0 && `(${history.length})`}
                        </Button>
                        {historyOpen && history.length > 0 && (
                            <div className="absolute right-0 top-full mt-2 w-96 rounded-md shadow-2xl z-50 max-h-[420px] overflow-hidden border bg-popover backdrop-blur-md text-popover-foreground flex flex-col">
                                <div className="p-3 border-b font-semibold text-sm text-popover-foreground bg-popover rounded-t-lg">
                                    Previous Answers (Redises)
                                </div>
                                <div className="p-2 border-b bg-popover">
                                    <Input
                                        placeholder="Search previous questions..."
                                        value={historySearch}
                                        onChange={(e) => {
                                            setHistorySearch(e.target.value);
                                        }}
                                        className="bg-popover! text-popover-foreground"
                                    />
                                </div>
                                <div className="overflow-y-auto max-h-80 bg-popover">
                                    {history.map((item) => (
                                        <button
                                            key={item.id}
                                            onClick={() => handleHistoryClick(item)}
                                            className="w-full text-left p-4 hover:bg-accent hover:text-accent-foreground border-b last:border-b-0 transition-colors bg-popover text-popover-foreground"
                                        >
                                            <p className="text-sm font-medium line-clamp-2">{item.question}</p>
                                            <p className="text-xs text-muted-foreground mt-1">
                                                {item.word_count || "250"} words • {new Date(item.timestamp).toLocaleDateString()}
                                            </p>
                                        </button>
                                    ))}
                                    {history.length === 0 && !isLoadingHistory && (
                                        <div className="p-4 text-sm text-muted-foreground bg-popover">No results</div>
                                    )}
                                </div>
                                <div className="p-2 border-t bg-popover flex items-center justify-between">
                                    <span className="text-xs text-muted-foreground">
                                        Showing {history.length} item{history.length === 1 ? "" : "s"}
                                    </span>
                                    <Button
                                        variant="outline"
                                        size="sm"
                                        disabled={!historyHasMore || isLoadingHistory}
                                        onClick={() => fetchHistory({ reset: false })}
                                    >
                                        {isLoadingHistory ? "Loading..." : historyHasMore ? "Load more" : "All loaded"}
                                    </Button>
                                </div>
                            </div>
                        )}
                    </div>
                </div>
                <div className="space-y-8">
                    {/* Input Section */}
                    <Card>
                        <CardHeader className="pb-4 border-b border-[var(--card-border)] bg-[var(--bg-secondary)] rounded-t-xl">
                            <CardTitle className="text-xl font-bold text-[var(--text)]">1. Question details</CardTitle>
                            <CardDescription className="text-[var(--text-muted)] mt-1">Enter the question and requirements.</CardDescription>
                        </CardHeader>
                        <CardContent className="pt-6">
                            <form onSubmit={handleGenerate} className="space-y-6">
                                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                                    <div className="space-y-1.5">
                                        <Label className="text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wide">GS paper context</Label>
                                        <Select value={gsPaper} onValueChange={setGsPaper}>
                                            <SelectTrigger>
                                                <SelectValue placeholder="Select GS paper (optional)" />
                                            </SelectTrigger>
                                            <SelectContent className="bg-[var(--card)] z-50">
                                                <SelectItem value="GS1">GS1</SelectItem>
                                                <SelectItem value="GS2">GS2</SelectItem>
                                                <SelectItem value="GS3">GS3</SelectItem>
                                                <SelectItem value="GS4">GS4</SelectItem>
                                            </SelectContent>
                                        </Select>
                                    </div>
                                    <div className="space-y-1.5">
                                        <Label className="text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wide">Subject domain</Label>
                                        <Select value={subject} onValueChange={setSubject}>
                                            <SelectTrigger>
                                                <SelectValue placeholder="Select subject (optional)" />
                                            </SelectTrigger>
                                            <SelectContent className="bg-[var(--card)] z-50">
                                                {availableSubjects.map((subj) => (
                                                    <SelectItem key={subj} value={subj}>
                                                        {subj}
                                                    </SelectItem>
                                                ))}
                                            </SelectContent>
                                        </Select>
                                    </div>
                                </div>

                                <div className="space-y-1.5">
                                    <Label htmlFor="question" className="text-sm font-semibold text-[var(--text)]">Question</Label>
                                    <Textarea
                                        id="question"
                                        placeholder="e.g. Discuss the impact of climate change on Indian agriculture..."
                                        className="min-h-[120px] resize-y text-base"
                                        value={question}
                                        onChange={(e) => setQuestion(e.target.value)}
                                        disabled={loading}
                                    />
                                </div>

                                <div className="space-y-3 pt-2">
                                    <Label htmlFor="word-count" className="text-sm font-semibold text-[var(--text)]">Word limit</Label>
                                    <div className="flex flex-col md:flex-row md:items-start gap-6">
                                        <div className="relative w-full md:w-56">
                                            <Input
                                                id="word-count"
                                                type="number"
                                                min="100"
                                                max="1000"
                                                step="50"
                                                value={wordCount}
                                                onChange={(e) => setWordCount(e.target.value)}
                                                disabled={loading}
                                            />
                                            <p className="text-[13px] text-[var(--text-muted)] mt-2">Standard limits: 150, 250 words</p>
                                        </div>

                                        <div className="flex gap-3">
                                            <Button
                                                type="submit"
                                                className={cn(
                                                    "w-auto px-6 border-2 transition-all shadow-sm",
                                                    jobStatus === 'completed' && result
                                                        ? "bg-green-600 border-green-700 hover:bg-green-700 text-white"
                                                        : "border-primary/20 hover:border-primary/50"
                                                )}
                                                disabled={loading || !question.trim() || (jobStatus === 'completed' && !!result)}
                                            >
                                                {loading ? (
                                                    <>
                                                        <InlineLoader className="mr-2" />
                                                        Generating...
                                                    </>
                                                ) : jobStatus === 'completed' && result ? (
                                                    <>
                                                        <CheckCircle className="mr-2 h-4 w-4" />
                                                        Generated Answer
                                                    </>
                                                ) : jobStatus === 'failed' ? (
                                                    <>
                                                        <RefreshCw className="mr-2 h-4 w-4" />
                                                        Regenerate Answer
                                                    </>
                                                ) : (
                                                    <>
                                                        <PenTool className="mr-2 h-4 w-4" />
                                                        Generate Answer
                                                    </>
                                                )}
                                            </Button>

                                            {(result || error || jobStatus === 'failed') && !loading && (
                                                <Button
                                                    type="button"
                                                    variant="outline"
                                                    onClick={() => clear()}
                                                    className="shrink-0"
                                                >
                                                    <RefreshCw className="mr-2 h-4 w-4" />
                                                    New Answer
                                                </Button>
                                            )}

                                            {loading && (
                                                <Button
                                                    type="button"
                                                    variant="destructive"
                                                    onClick={handleCancel}
                                                    className="shrink-0"
                                                >
                                                    Cancel
                                                </Button>
                                            )}
                                        </div>
                                    </div>
                                </div>
                            </form>
                        </CardContent>
                    </Card>

                    {/* Error Alert */}
                    {error && (
                        <Alert variant="destructive" className="border-2 border-red-500 bg-red-50 dark:bg-red-900/20">
                            <AlertCircle className="h-5 w-5" />
                            <AlertDescription className="font-semibold text-base">{error}</AlertDescription>
                        </Alert>
                    )}

                    {/* Output Section */}
                    {result && (
                        <div className="space-y-6 pt-4 animate-fade-up">

                            {/* Question Title Card */}
                            <Card className="bg-[var(--bg-secondary)] border-[var(--card-border)] shadow-none">
                                <CardHeader className="py-5 px-6">
                                    <CardTitle className="text-lg font-semibold leading-relaxed text-[var(--text)]">
                                        Q: {result.question}
                                    </CardTitle>
                                </CardHeader>
                            </Card>

                            {/* Compressed Answer Accordion (shown if compression was applied) */}
                            {result.compressed_answer && (
                                <Card className="border-[var(--card-border)] shadow-sm">
                                    <button
                                        type="button"
                                        onClick={() => setShowCompressed(!showCompressed)}
                                        className="w-full flex items-center justify-between p-5 text-left hover:bg-[var(--bg-secondary)] transition-colors border-b border-[var(--card-border)] rounded-t-xl"
                                    >
                                        <span className="font-semibold text-[var(--text)] flex items-center gap-2">
                                            <Minimize2 className="h-4 w-4 text-amber-600" />
                                            Concise answer
                                        </span>
                                        <ChevronDown className={`h-4 w-4 text-[var(--text-muted)] transition-transform ${showCompressed ? 'rotate-180' : ''}`} />
                                    </button>
                                    {showCompressed && (
                                        <CardContent className="p-6 md:p-8">
                                            <div className="prose prose-sm md:prose-base max-w-none text-[var(--text)] prose-p:leading-relaxed dark:prose-invert 
                                                prose-headings:text-[var(--text)] prose-headings:font-bold prose-headings:mt-8 prose-headings:mb-4
                                                prose-h3:text-lg prose-h4:text-base prose-strong:text-[var(--text)]
                                                prose-ul:my-4 prose-li:my-1 prose-a:text-amber-600 prose-a:no-underline hover:prose-a:underline">
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
                            <Card className={cn("border-[var(--card-border)] shadow-sm", result.compressed_answer ? "border-dashed" : "")}>
                                <button
                                    type="button"
                                    onClick={() => setShowOriginal(!showOriginal)}
                                    className="w-full flex items-center justify-between p-5 text-left hover:bg-[var(--bg-secondary)] transition-colors border-b border-[var(--card-border)] rounded-t-xl"
                                >
                                    <span className="font-semibold text-[var(--text)]">
                                        {result.compressed_answer ? "Comprehensive answer" : "Generated answer"} <span className="text-[var(--text-muted)] font-normal text-sm">({result.word_count_actual} words)</span>
                                    </span>
                                    <ChevronDown className={`h-4 w-4 text-[var(--text-muted)] transition-transform ${(showOriginal || !result.compressed_answer) ? 'rotate-180' : ''}`} />
                                </button>
                                {(showOriginal || !result.compressed_answer) && (
                                    <CardContent className="p-6 md:p-8">
                                        <div className="prose prose-sm md:prose-base max-w-none text-[var(--text)] prose-p:leading-relaxed dark:prose-invert 
                                            prose-headings:text-[var(--text)] prose-headings:font-bold prose-headings:mt-8 prose-headings:mb-4
                                            prose-h3:text-lg prose-h4:text-base prose-strong:text-[var(--text)]
                                            prose-ul:my-4 prose-li:my-1 prose-a:text-amber-600 prose-a:no-underline hover:prose-a:underline">
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
                                <Card className="border-[var(--card-border)] shadow-sm bg-[var(--bg-secondary)]">
                                    <CardContent className="p-6">
                                        <h4 className="text-sm font-semibold text-[var(--text)] mb-4 flex items-center gap-2 uppercase tracking-wide">
                                            <BookOpen className="h-4 w-4 text-amber-600" />
                                            References
                                        </h4>
                                        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                                            {result.sources.map((source, idx) => (
                                                <div key={idx} className="bg-[var(--card)] p-3 rounded-lg text-xs border border-[var(--card-border)] group hover:border-amber-300 transition-colors">
                                                    <p className="font-semibold text-[var(--text)] truncate" title={source.filename}>
                                                        {source.filename.replace('.pdf', '')}
                                                    </p>
                                                    <div className="flex gap-2 mt-1.5 text-[var(--text-muted)] font-medium">
                                                        {source.page_number && <span>Page {source.page_number}</span>}
                                                        {source.chapter && (
                                                            <>
                                                                {source.page_number && <span className="text-[var(--text-faint)]">•</span>}
                                                                <span className="truncate" title={source.chapter}>
                                                                    {source.chapter}
                                                                </span>
                                                            </>
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
                        <PageLoader
                            text={getStatusMessage() || "Generating comprehensive answer..."}
                            className="border-2 border-dashed border-[var(--card-border)] rounded-xl bg-[var(--bg-secondary)]/50 p-12"
                        />
                    )}
                </div>
            </div>
            {/* History Answer Modal */}
            <Dialog
                open={historyModalOpen}
                onOpenChange={(open) => {
                    setHistoryModalOpen(open);
                    if (!open) {
                        setModalShowCompressed(false);
                        setModalShowOriginal(false);
                    }
                }}
            >
                <DialogContent
                    className="sm:max-w-5xl max-h-[85vh] overflow-y-auto bg-[hsl(var(--card))] text-[hsl(var(--text))] border border-[hsl(var(--border))] shadow-2xl [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
                >
                    <DialogHeader>
                        <DialogTitle className="text-2xl font-bold text-[hsl(var(--text))]">Previous Answer</DialogTitle>
                        <DialogDescription className="text-[hsl(var(--text-muted))]">
                            {historyModalItem?.question}
                        </DialogDescription>
                    </DialogHeader>

                    {historyModalLoading && (
                        <div className="flex items-center gap-2 text-muted-foreground p-4">
                            <InlineLoader />
                            <span>Loading cached answer...</span>
                        </div>
                    )}

                    {historyModalError && (
                        <Alert variant="destructive" className="border-2 border-red-500 bg-red-50 dark:bg-red-900/20">
                            <AlertCircle className="h-5 w-5" />
                            <AlertDescription className="font-semibold text-base">{historyModalError}</AlertDescription>
                        </Alert>
                    )}

                    {historyModalAnswer && (
                        <div className="space-y-4">
                            <div className="text-sm text-muted-foreground">
                                <span className="font-semibold text-foreground">{historyModalAnswer.word_count_actual} words</span>
                                {historyModalAnswer.word_count_compressed && (
                                    <span className="ml-2 text-foreground">
                                        • Compressed: {historyModalAnswer.word_count_compressed} words
                                    </span>
                                )}
                            </div>

                            {historyModalAnswer.compressed_answer && (
                                <Card>
                                    <button
                                        type="button"
                                        onClick={() => setModalShowCompressed(!modalShowCompressed)}
                                        className="w-full flex items-center justify-between p-4 text-left hover:bg-muted/30 transition-colors border-b cursor-pointer"
                                    >
                                        <span className="font-medium text-foreground flex items-center gap-2">
                                            <Minimize2 className="h-4 w-4 text-blue-500" />
                                            Compressed Answer ({historyModalAnswer.word_count_compressed} words)
                                        </span>
                                        <ChevronDown className={`h-4 w-4 text-muted-foreground transition-transform ${modalShowCompressed ? 'rotate-180' : ''}`} />
                                    </button>
                                    {modalShowCompressed && (
                                        <CardContent className="p-6">
                                            <div className="prose prose-sm md:prose-base max-w-none dark:prose-invert prose-headings:font-semibold prose-a:text-primary space-y-4">
                                                <ReactMarkdown
                                                    remarkPlugins={[remarkGfm]}
                                                    components={modalMarkdownComponents}
                                                    urlTransform={urlTransform}
                                                >
                                                    {stripHeavyContent(historyModalAnswer.compressed_answer, { removeAllMaps: false })}
                                                </ReactMarkdown>
                                            </div>
                                        </CardContent>
                                    )}
                                </Card>
                            )}

                            <Card className={historyModalAnswer.compressed_answer ? "border-dashed" : ""}>
                                <button
                                    type="button"
                                    onClick={() => setModalShowOriginal(!modalShowOriginal)}
                                    className="w-full flex items-center justify-between p-4 text-left hover:bg-muted/30 transition-colors border-b cursor-pointer"
                                >
                                    <span className="font-medium text-foreground">
                                        {historyModalAnswer.compressed_answer ? "Original Answer" : "Answer"} ({historyModalAnswer.word_count_actual} words)
                                    </span>
                                    <ChevronDown className={`h-4 w-4 text-muted-foreground transition-transform ${(modalShowOriginal || !historyModalAnswer.compressed_answer) ? 'rotate-180' : ''}`} />
                                </button>
                                {(modalShowOriginal || !historyModalAnswer.compressed_answer) && (
                                    <CardContent className="p-6">
                                        <div className="prose prose-sm md:prose-base max-w-none dark:prose-invert prose-headings:font-semibold prose-a:text-primary space-y-4">
                                            <ReactMarkdown
                                                remarkPlugins={[remarkGfm]}
                                                components={modalMarkdownComponents}
                                                urlTransform={urlTransform}
                                            >
                                                {stripHeavyContent(historyModalAnswer.answer, { removeAllMaps: false })}
                                            </ReactMarkdown>
                                        </div>
                                    </CardContent>
                                )}
                            </Card>
                        </div>
                    )}
                </DialogContent>
            </Dialog>
        </PageContainer>
    );
}
