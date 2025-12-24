"use client";

import { useState, useRef, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { fetchApi, API_URL } from "@/lib/api";
import { Upload, FileText, CheckCircle, AlertCircle, Loader2, BookOpen } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { markdownComponents, urlTransform } from "@/components/ui/mermaid";
import { cn } from "@/lib/utils";
import ApiKeyBanner from "@/components/layout/ApiKeyBanner";
import { apiClient, ApiError, api, showToast } from "@/lib/apiClient";
import { useEvaluateAnswerStore } from "@/stores";
import { useAuth } from "@/context/AuthContext";
import { EvaluationResult } from "@/stores/types";

export default function EvaluatePage() {
    const { user, refreshUser, isApiKeyValid, setIsApiKeyValid, verifyApiKey } = useAuth();
    const [showBanner, setShowBanner] = useState(false);
    const {
        question,
        jobId,
        jobStatus,
        result,
        error,
        setQuestion,
        setJobId,
        setJobStatus,
        setResult,
        setError,
        reset
    } = useEvaluateAnswerStore();

    const [files, setFiles] = useState<File[]>([]);
    const [showCompressed, setShowCompressed] = useState(true);
    const [showOriginal, setShowOriginal] = useState(false);

    // Derived state for UI
    const loading = jobStatus === 'pending' || jobStatus === 'processing' || jobStatus === 'queued';
    const polling = jobStatus === 'pending' || jobStatus === 'processing' || jobStatus === 'queued';

    const [statusMessage, setStatusMessage] = useState("Evaluating...");

    // Ref to track active job for cancellation effect
    const activeJobId = useRef<string | null>(null);

    // Sync ref with store
    useEffect(() => {
        activeJobId.current = jobId;
    }, [jobId]);

    // Resume polling on mount if active
    useEffect(() => {
        if (jobId && (jobStatus === 'pending' || jobStatus === 'processing' || jobStatus === 'queued')) {
            setStatusMessage("Resuming evaluation...");
            pollStatus(jobId);
        }
    }, []);

    // Proactively show banner removed - on-demand only

    const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
        if (e.target.files && e.target.files.length > 0) {
            const newFiles = Array.from(e.target.files);
            setFiles(prev => [...prev, ...newFiles]);
        }
    };

    const removeFile = (index: number) => {
        setFiles(prev => prev.filter((_, i) => i !== index));
    };

    const handleReset = () => {
        reset();
        setFiles([]);
        setShowCompressed(true);
        setShowOriginal(false);
    };

    const pollStatus = async (id: string) => {
        if (activeJobId.current !== id) return;

        try {
            const data = await apiClient<{ status: string, result?: EvaluationResult, error?: string }>(`/evaluate-answer/status/${id}`);

            if (activeJobId.current !== id) return;

            if (data.status === 'completed') {
                if (data.result) {
                    setResult(data.result);
                    setJobId(null);
                    activeJobId.current = null;
                } else {
                    setError("Evaluation completed but returned no results.");
                    setJobId(null);
                    activeJobId.current = null;
                }
            } else if (data.status === 'failed') {
                const cleanedError = data.error || "Evaluation failed";
                setError(cleanedError);
                setJobStatus('failed');

                // Show banner if it's an API key error
                if (cleanedError.toLowerCase().includes("api key") || cleanedError.includes("API_KEY_INVALID")) {
                    setIsApiKeyValid('invalid');
                    setShowBanner(true);
                }
                setJobId(null);
                activeJobId.current = null;
            } else {
                if (data.status === 'processing') {
                    if (jobStatus !== 'processing') setJobStatus('processing');
                    setStatusMessage("Analyzing your answer...");
                } else if (data.status === 'queued') {
                    if (jobStatus !== 'queued') setJobStatus('queued');
                    setStatusMessage("Waiting in queue...");
                }

                setTimeout(() => pollStatus(id), 2000);
            }
        } catch (err) {
            if (activeJobId.current !== id) return;
            console.error("Polling error:", err);
            setTimeout(() => pollStatus(id), 3000);
        }
    };

    const handleCancel = async () => {
        if (!jobId) return;

        const idToCancel = jobId;
        setJobId(null);
        setJobStatus('idle');
        setError("Evaluation cancelled");
        activeJobId.current = null;

        try {
            await api.post(`/jobs/${idToCancel}/cancel`);
            showToast("Evaluation cancelled successfully.", 'success');
        } catch (err) {
            console.error("Failed to send cancel request:", err);
            showToast("Local cancellation successful, but backend signal failed.", 'warning');
        }
    };

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();

        // Strict guard for API key
        if (!user || user.has_gemini_api_key === false || isApiKeyValid === 'invalid') {
            // Prioritize "missing key" message over "invalid" just in case state is mixed
            const msg = (user && user.has_gemini_api_key === false)
                ? "Please set your Gemini API key in Settings before evaluating."
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

        if (files.length === 0) {
            setError("Please select at least one file to upload.");
            return;
        }

        setError(null);
        setResult(null);
        setJobId(null);
        setJobStatus('queued');
        setStatusMessage("Uploading and starting...");

        const formData = new FormData();
        files.forEach((file) => {
            formData.append("files", file);
        });
        if (question) formData.append("question", question);

        try {
            const data = await apiClient<{ job_id: string, status: string }>('/evaluate-answer/', {
                method: 'POST',
                body: formData,
                headers: {},
            });

            if (data.job_id) {
                setJobId(data.job_id);
                setJobStatus('queued');
                activeJobId.current = data.job_id;
                setStatusMessage("Queued for evaluation...");
                pollStatus(data.job_id);
            } else {
                throw new Error("No job ID received");
            }

        } catch (err) {
            setJobStatus('failed');
            let message = "Evaluation failed";
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

    return (
        <div className="p-8 max-w-7xl mx-auto space-y-8">
            <ApiKeyBanner
                showBanner={showBanner}
                onKeySet={() => {
                    setShowBanner(false);
                    setError("");
                    refreshUser();
                }}
            />

            <div className="flex flex-col space-y-2">
                <h1 className="text-3xl font-bold tracking-tight text-foreground">
                    Evaluate Answer
                </h1>
                <p className="text-muted-foreground">
                    Upload your handwritten answer for AI-powered evaluation and improvement.
                </p>
            </div>

            <div className="grid gap-8">
                {/* Input Section */}
                <div className="lg:col-span-2 space-y-6">
                    <Card>
                        <CardHeader>
                            <div className="flex items-center justify-between">
                                <div>
                                    <CardTitle>Upload & Configure</CardTitle>
                                    <CardDescription>Provide your answer details</CardDescription>
                                </div>
                                {result && (
                                    <Button
                                        variant="outline"
                                        size="sm"
                                        onClick={handleReset}
                                        className="flex items-center gap-2"
                                    >
                                        <RefreshCw className="h-4 w-4" />
                                        New Evaluation
                                    </Button>
                                )}
                            </div>
                        </CardHeader>
                        <CardContent>
                            <form onSubmit={handleSubmit} className="space-y-4">
                                <div className="space-y-2">
                                    <label className="text-sm font-medium leading-none peer-disabled:cursor-not-allowed peer-disabled:opacity-70">
                                        Answer Files (PDF/Images) - Multiple pages supported
                                    </label>
                                    <div className="flex items-center justify-center w-full">
                                        <label
                                            htmlFor="dropzone-file"
                                            className={cn(
                                                "flex flex-col items-center justify-center w-full h-32 border-2 border-dashed rounded-lg cursor-pointer bg-gray-50 hover:bg-gray-100 transition-colors",
                                                files.length > 0 ? "border-green-500 bg-green-50" : "border-gray-300"
                                            )}
                                        >
                                            <div className="flex flex-col items-center justify-center pt-5 pb-6">
                                                {files.length > 0 ? (
                                                    <>
                                                        <CheckCircle className="w-8 h-8 mb-2 text-green-500" />
                                                        <p className="mb-2 text-sm text-green-700 font-medium">
                                                            {files.length} file{files.length > 1 ? 's' : ''} selected
                                                        </p>
                                                        <p className="text-xs text-green-600">Click to add more</p>
                                                    </>
                                                ) : (
                                                    <>
                                                        <Upload className="w-8 h-8 mb-2 text-gray-400" />
                                                        <p className="mb-2 text-sm text-gray-500">
                                                            <span className="font-semibold">Click to upload</span> or drag and drop
                                                        </p>
                                                        <p className="text-xs text-gray-500">PDF, PNG, JPG (MAX. 10MB each)</p>
                                                    </>
                                                )}
                                            </div>
                                            <input
                                                id="dropzone-file"
                                                type="file"
                                                className="hidden"
                                                onChange={handleFileChange}
                                                accept=".pdf,image/*"
                                                multiple
                                            />
                                        </label>
                                    </div>

                                    {/* File List */}
                                    {files.length > 0 && (
                                        <div className="mt-3 space-y-2 max-h-40 overflow-y-auto">
                                            {files.map((file, index) => (
                                                <div key={index} className="flex items-center justify-between p-2 bg-white border rounded-md">
                                                    <div className="flex items-center gap-2 flex-1 min-w-0">
                                                        <FileText className="h-4 w-4 text-gray-400 flex-shrink-0" />
                                                        <span className="text-sm truncate">{file.name}</span>
                                                        <span className="text-xs text-gray-400 flex-shrink-0">({(file.size / 1024).toFixed(1)} KB)</span>
                                                    </div>
                                                    <Button
                                                        type="button"
                                                        variant="ghost"
                                                        size="sm"
                                                        onClick={() => removeFile(index)}
                                                        className="h-6 w-6 p-0 flex-shrink-0"
                                                    >
                                                        ×
                                                    </Button>
                                                </div>
                                            ))}
                                        </div>
                                    )}
                                </div>

                                <div className="space-y-2">
                                    <label className="text-sm font-medium">Question (Optional)</label>
                                    <Input
                                        placeholder="Enter the question text..."
                                        value={question}
                                        onChange={(e) => setQuestion(e.target.value)}
                                    />
                                    <p className="text-xs text-muted-foreground">
                                        If left blank, AI will try to identify it from the file.
                                    </p>
                                </div>


                                {error && (
                                    <div className="p-4 text-base font-semibold text-red-700 bg-red-50 dark:bg-red-900/20 rounded-lg border-2 border-red-500 flex items-center gap-3">
                                        <AlertCircle className="h-5 w-5 flex-shrink-0" />
                                        <span>{error}</span>
                                    </div>
                                )}

                                <div className="flex gap-2">
                                    <Button
                                        type="submit"
                                        className="w-full h-12 text-lg font-semibold border-2 border-primary/20 hover:border-primary/50 transition-all duration-300"
                                        disabled={loading || files.length === 0}
                                    >
                                        {loading ? (
                                            <>
                                                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                                                {statusMessage}
                                            </>
                                        ) : result ? (
                                            <>
                                                <CheckCircle className="mr-2 h-4 w-4" />
                                                Evaluated
                                            </>
                                        ) : (
                                            "Evaluate Answer"
                                        )}
                                    </Button>

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
                            </form>
                        </CardContent>
                    </Card>
                </div>

                {/* Results Section */}
                <div className="lg:col-span-2 space-y-6">
                    {result ? (
                        <div className="space-y-6 animate-in fade-in slide-in-from-bottom-4 duration-500">
                            {/* Question & Summary */}
                            <Card className="bg-blue-50/50 border-blue-100">
                                <CardHeader className="pb-3">
                                    <CardTitle className="text-lg text-blue-900">Identified Question</CardTitle>
                                </CardHeader>
                                <CardContent>
                                    <p className="text-blue-800 font-medium">{result.question}</p>
                                    <div className="mt-4 flex gap-4 text-sm text-blue-600">
                                        <div className="flex items-center gap-1">
                                            <BookOpen className="h-4 w-4" />
                                            {result.sources.length} Sources Used
                                        </div>
                                        {result.current_affairs_count > 0 && (
                                            <div className="flex items-center gap-1">
                                                <span className="font-bold">NEWS</span>
                                                {result.current_affairs_count} Current Affairs
                                            </div>
                                        )}
                                    </div>
                                </CardContent>
                            </Card>

                            {/* Feedback Grid */}
                            <div className="grid gap-4 md:grid-cols-3">
                                <Card className="border-l-4 border-l-green-500">
                                    <CardHeader className="pb-2">
                                        <CardTitle className="text-base text-green-700">Strengths</CardTitle>
                                    </CardHeader>
                                    <CardContent>
                                        {result.feedback.strengths && result.feedback.strengths.length > 0 ? (
                                            <ul className="list-disc pl-4 space-y-1 text-sm text-gray-700">
                                                {result.feedback.strengths.map((item, i) => (
                                                    <li key={i}>{item}</li>
                                                ))}
                                            </ul>
                                        ) : (
                                            <p className="text-sm text-gray-500 italic">No specific strengths identified</p>
                                        )}
                                    </CardContent>
                                </Card>

                                <Card className="border-l-4 border-l-orange-500">
                                    <CardHeader className="pb-2">
                                        <CardTitle className="text-base text-orange-700">Missing Elements</CardTitle>
                                    </CardHeader>
                                    <CardContent>
                                        {result.feedback.missing_elements && result.feedback.missing_elements.length > 0 ? (
                                            <ul className="list-disc pl-4 space-y-1 text-sm text-gray-700">
                                                {result.feedback.missing_elements.map((item, i) => (
                                                    <li key={i}>{item}</li>
                                                ))}
                                            </ul>
                                        ) : (
                                            <p className="text-sm text-gray-500 italic">All key elements present</p>
                                        )}
                                    </CardContent>
                                </Card>

                                <Card className="border-l-4 border-l-amber-500">
                                    <CardHeader className="pb-2">
                                        <CardTitle className="text-base text-amber-700">Improvements Needed</CardTitle>
                                    </CardHeader>
                                    <CardContent>
                                        {result.feedback.improvements_needed && result.feedback.improvements_needed.length > 0 ? (
                                            <ul className="list-disc pl-4 space-y-1 text-sm text-gray-700">
                                                {result.feedback.improvements_needed.map((item, i) => (
                                                    <li key={i}>{item}</li>
                                                ))}
                                            </ul>
                                        ) : (
                                            <p className="text-sm text-gray-500 italic">No major improvements needed</p>
                                        )}
                                    </CardContent>
                                </Card>
                            </div>

                            {/* Directive Alignment (NEW) */}
                            {result.feedback.directive_alignment && (
                                <Card className="border-l-4 border-l-purple-500">
                                    <CardHeader className="pb-2">
                                        <CardTitle className="text-base text-purple-700">Directive Alignment</CardTitle>
                                        <CardDescription className="text-xs">
                                            How well your answer matches the question's directive
                                        </CardDescription>
                                    </CardHeader>
                                    <CardContent className="space-y-3 text-sm">
                                        <div>
                                            <span className="font-semibold text-gray-900">Directive Identified: </span>
                                            <span className="text-purple-700 font-medium">{result.feedback.directive_alignment.directive_identified}</span>
                                        </div>
                                        <div>
                                            <h4 className="font-semibold text-gray-900 mb-1">Alignment Assessment</h4>
                                            <p className="text-gray-700">{result.feedback.directive_alignment.alignment_assessment}</p>
                                        </div>
                                        {result.feedback.directive_alignment.issues_if_any && result.feedback.directive_alignment.issues_if_any.length > 0 && (
                                            <div>
                                                <h4 className="font-semibold text-amber-700 mb-1">Issues Identified</h4>
                                                <ul className="list-disc pl-4 space-y-1 text-gray-700">
                                                    {result.feedback.directive_alignment.issues_if_any.map((issue, i) => (
                                                        <li key={i}>{issue}</li>
                                                    ))}
                                                </ul>
                                            </div>
                                        )}
                                        <div className="bg-purple-50 p-3 rounded-md border border-purple-100">
                                            <h4 className="font-semibold text-purple-900 mb-1">How to Improve</h4>
                                            <p className="text-purple-800">{result.feedback.directive_alignment.how_to_improve}</p>
                                        </div>
                                    </CardContent>
                                </Card>
                            )}

                            {/* Detailed Feedback */}
                            <Card>
                                <CardHeader>
                                    <CardTitle>Detailed Assessment</CardTitle>
                                </CardHeader>
                                <CardContent className="space-y-4 text-sm">
                                    <div>
                                        <h4 className="font-semibold text-gray-900 mb-1">Structure & Format</h4>
                                        <p className="text-gray-600">{result.feedback.structure_feedback}</p>
                                    </div>
                                    <div>
                                        <h4 className="font-semibold text-gray-900 mb-1">Evidence & Examples</h4>
                                        <p className="text-gray-600">{result.feedback.evidence_feedback}</p>
                                    </div>
                                    {result.feedback.visual_feedback && (
                                        <div>
                                            <h4 className="font-semibold text-gray-900 mb-1">Visuals (Maps/Diagrams/Tables)</h4>
                                            <p className="text-gray-600">{result.feedback.visual_feedback}</p>
                                        </div>
                                    )}
                                    {result.feedback.examiner_expectation_gap && (
                                        <div className="bg-blue-50 p-3 rounded-md border border-blue-100">
                                            <h4 className="font-semibold text-blue-900 mb-1">Examiner's Perspective</h4>
                                            <p className="text-blue-800">{result.feedback.examiner_expectation_gap}</p>
                                        </div>
                                    )}
                                    {result.feedback.strategy_tip && (
                                        <div className="bg-green-50 p-3 rounded-md border border-green-100">
                                            <h4 className="font-semibold text-green-900 mb-1 flex items-center gap-2">
                                                <BookOpen className="h-4 w-4" />
                                                Exam Strategy Tip
                                            </h4>
                                            <p className="text-green-800">{result.feedback.strategy_tip}</p>
                                        </div>
                                    )}
                                    <div className="bg-gray-50 p-3 rounded-md">
                                        <h4 className="font-semibold text-gray-900 mb-1">Overall Verdict</h4>
                                        <p className="text-gray-600 italic">{result.feedback.overall_assessment}</p>
                                    </div>
                                </CardContent>
                            </Card>

                            {/* Improved Answer Section (with Compression) */}
                            <div className="space-y-4">
                                {/* Compressed Version */}
                                {result.compressed_answer && (
                                    <Card className="border-2 border-indigo-100 overflow-hidden shadow-sm">
                                        <button
                                            type="button"
                                            onClick={() => setShowCompressed(!showCompressed)}
                                            className="w-full flex items-center justify-between p-4 bg-indigo-50/50 hover:bg-indigo-100/50 transition-colors border-b border-indigo-100"
                                        >
                                            <div className="flex flex-col items-start gap-1">
                                                <div className="flex items-center gap-2 text-indigo-900 font-semibold">
                                                    <Minimize2 className="h-4 w-4" />
                                                    Compressed Model Solution
                                                </div>
                                                <div className="text-xs text-indigo-600/70">
                                                    {result.word_count_compressed} words • Optimized for quick reading
                                                </div>
                                            </div>
                                            <ChevronDown className={cn("h-4 w-4 text-indigo-400 transition-transform", showCompressed && "rotate-180")} />
                                        </button>
                                        {showCompressed && (
                                            <CardContent className="p-6">
                                                <div className="prose prose-indigo max-w-none prose-headings:text-indigo-900">
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

                                {/* Original Improved Version */}
                                <Card className={cn(
                                    "overflow-hidden",
                                    result.compressed_answer ? "border-dashed border-gray-300" : "border-2 border-indigo-100 shadow-sm"
                                )}>
                                    <button
                                        type="button"
                                        onClick={() => setShowOriginal(!showOriginal)}
                                        className={cn(
                                            "w-full flex items-center justify-between p-4 transition-colors border-b",
                                            result.compressed_answer ? "bg-gray-50/50 hover:bg-gray-100/50" : "bg-indigo-50/50 hover:bg-indigo-100/50"
                                        )}
                                    >
                                        <div className="flex flex-col items-start gap-1">
                                            <div className={cn(
                                                "flex items-center gap-2 font-semibold",
                                                result.compressed_answer ? "text-gray-700" : "text-indigo-900"
                                            )}>
                                                <FileText className="h-4 w-4" />
                                                {result.compressed_answer ? "Original Model Solution" : "Model Solution"}
                                            </div>
                                            <div className="text-xs text-muted-foreground">
                                                {result.word_count_actual} words • Comprehensive version
                                            </div>
                                        </div>
                                        <ChevronDown className={cn(
                                            "h-4 w-4 transition-transform",
                                            result.compressed_answer ? "text-gray-400" : "text-indigo-400",
                                            (showOriginal || !result.compressed_answer) && "rotate-180"
                                        )} />
                                    </button>
                                    {(showOriginal || !result.compressed_answer) && (
                                        <CardContent className="p-6">
                                            <div className="prose prose-indigo max-w-none prose-headings:text-indigo-900">
                                                <ReactMarkdown
                                                    remarkPlugins={[remarkGfm]}
                                                    components={markdownComponents}
                                                    urlTransform={urlTransform}
                                                >
                                                    {result.improved_answer}
                                                </ReactMarkdown>
                                            </div>
                                        </CardContent>
                                    )}
                                </Card>
                            </div>
                        </div>
                    ) : (
                        <div className="h-full flex flex-col items-center justify-center text-center p-12 border-2 border-dashed rounded-lg bg-gray-50/50">
                            <div className="bg-white p-4 rounded-full shadow-sm mb-4">
                                <FileText className="h-8 w-8 text-gray-400" />
                            </div>
                            <h3 className="text-lg font-medium text-gray-900">No Evaluation Yet</h3>
                            <p className="text-muted-foreground max-w-sm mt-2">
                                Upload your answer sheet on the left to receive detailed AI feedback and an improved model answer.
                            </p>
                        </div>
                    )}
                </div>
            </div>
        </div >
    );
}

// Import additional icons
import { RefreshCw, Minimize2, ChevronDown } from "lucide-react";
