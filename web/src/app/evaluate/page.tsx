"use client";

import { useState, useRef, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { Label } from "@/components/ui/label";
import { Checkbox } from "@/components/ui/checkbox";
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

// Helper function to format text with line breaks around ** markers for better readability
const formatBlueprintText = (text: string): string => {
    if (!text) return text;

    // First, fix broken patterns where ** markers are split across lines
    // Pattern: "1.\n**Text:\n**" -> "1. **Text:**"
    let formatted = text
        // Fix: Remove line breaks between number and **
        .replace(/(\d+)\.\s*\n\s*\*\*/g, '$1. **')
        // Fix: Remove line breaks between **Text: and **
        .replace(/\*\*([^*:]+?):\s*\n\s*\*\*/g, '**$1:**')
        // Fix: Remove line breaks in the middle of ** markers
        .replace(/\*\*\s*\n\s*\*\*/g, '**')
        // Now format correctly: "1. **Text:** explanation" -> "1.**Text:**\n explanation"
        .replace(/(\d+)\.\s*\*\*([^*:]+?):\*\*\s*/g, '$1.**$2:**\n')
        // Clean up multiple newlines
        .replace(/\n{3,}/g, '\n\n')
        .trim();

    return formatted;
};

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
        reset,
        // Improved Answer State
        improvedAnswerJobId,
        improvedAnswerStatus,
        improvedAnswerResult,
        improvedAnswerError,
        setImprovedAnswerJobId,
        setImprovedAnswerStatus,
        setImprovedAnswerResult,
        setImprovedAnswerError,
        generateImprovedAnswer,
        resetImprovedAnswer
    } = useEvaluateAnswerStore();

    const [files, setFiles] = useState<File[]>([]);
    const [showCompressed, setShowCompressed] = useState(true);
    const [showOriginal, setShowOriginal] = useState(false);
    const [evaluationMode, setEvaluationMode] = useState<"single" | "batch">("single");
    const [useStandardFormat, setUseStandardFormat] = useState(false);
    const [questionFile, setQuestionFile] = useState<File | null>(null);
    const [numQuestions, setNumQuestions] = useState<number>(1);
    const [questionTexts, setQuestionTexts] = useState<string[]>([""]);

    // Derived state for UI
    const loading = jobStatus === 'pending' || jobStatus === 'processing' || jobStatus === 'queued';
    const polling = jobStatus === 'pending' || jobStatus === 'processing' || jobStatus === 'queued';

    const [statusMessage, setStatusMessage] = useState("Evaluating...");

    // Ref to track active job for cancellation effect
    const activeJobId = useRef<string | null>(null);
    const activeImprovedAnswerJobId = useRef<string | null>(null);

    // Sync ref with store
    useEffect(() => {
        activeJobId.current = jobId;
    }, [jobId]);

    useEffect(() => {
        activeImprovedAnswerJobId.current = improvedAnswerJobId;
    }, [improvedAnswerJobId]);

    // Resume polling on mount if active
    useEffect(() => {
        if (jobId && (jobStatus === 'pending' || jobStatus === 'processing' || jobStatus === 'queued')) {
            setStatusMessage("Resuming evaluation...");
            pollStatus(jobId);
        }
    }, []);

    // Resume polling for improved answer if active
    useEffect(() => {
        if (improvedAnswerJobId && (improvedAnswerStatus === 'pending' || improvedAnswerStatus === 'processing' || improvedAnswerStatus === 'queued')) {
            pollImprovedAnswerStatus(improvedAnswerJobId);
        }
    }, []);

    // Proactively show banner removed - on-demand only

    const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
        if (e.target.files && e.target.files.length > 0) {
            const newFiles = Array.from(e.target.files);

            // For batch mode: only allow PDF, replace existing files
            if (evaluationMode === "batch") {
                const pdfFiles = newFiles.filter(f => f.name.toLowerCase().endsWith('.pdf'));
                if (pdfFiles.length === 0) {
                    setError("Batch mode only accepts PDF files. Please upload a PDF.");
                    return;
                }
                // Batch mode: single file only
                setFiles(pdfFiles.slice(0, 1));
            } else {
                // Single mode: allow multiple files
                setFiles(prev => [...prev, ...newFiles]);
            }
        }
    };

    const removeFile = (index: number) => {
        setFiles(prev => prev.filter((_, i) => i !== index));
    };

    const handleReset = () => {
        reset();
        resetImprovedAnswer();
        setFiles([]);
        setShowCompressed(true);
        setShowOriginal(false);
        setEvaluationMode("single");
        setUseStandardFormat(false);
    };

    const handleGenerateImprovedAnswer = async () => {
        if (!result || !result.feedback) {
            showToast("No evaluation feedback available", "error");
            return;
        }

        try {
            await generateImprovedAnswer(
                result.question,
                result.student_answer || null,
                result.feedback,
                result.word_count || 250,
                files.length > 0 ? files : undefined
            );

            // Start polling - get the job ID from store after state update
            setTimeout(() => {
                const store = useEvaluateAnswerStore.getState();
                if (store.improvedAnswerJobId) {
                    pollImprovedAnswerStatus(store.improvedAnswerJobId);
                }
            }, 100);
        } catch (error: any) {
            console.error("Failed to generate improved answer:", error);
            showToast(error.message || "Failed to generate improved answer", "error");
        }
    };

    const pollImprovedAnswerStatus = async (id: string) => {
        if (activeImprovedAnswerJobId.current !== id) return;

        try {
            const data = await apiClient<{ status: string, result?: any, error?: string }>(`/evaluate-answer/status/${id}`);

            if (activeImprovedAnswerJobId.current !== id) return;

            if (data.status === 'completed') {
                if (data.result) {
                    setImprovedAnswerResult(data.result);
                    setImprovedAnswerJobId(null);
                    activeImprovedAnswerJobId.current = null;
                } else {
                    setImprovedAnswerError("Improved answer generation completed but returned no results.");
                    setImprovedAnswerJobId(null);
                    activeImprovedAnswerJobId.current = null;
                }
            } else if (data.status === 'failed') {
                setImprovedAnswerError(data.error || "Improved answer generation failed");
                setImprovedAnswerJobId(null);
                activeImprovedAnswerJobId.current = null;
            } else {
                // Still processing, poll again
                setImprovedAnswerStatus(data.status as any);
                setTimeout(() => pollImprovedAnswerStatus(id), 2000);
            }
        } catch (error: any) {
            console.error("Failed to poll improved answer status:", error);
            if (activeImprovedAnswerJobId.current === id) {
                setImprovedAnswerError(error.message || "Failed to check status");
                setImprovedAnswerJobId(null);
                activeImprovedAnswerJobId.current = null;
            }
        }
    };

    const pollStatus = async (id: string) => {
        if (activeJobId.current !== id) return;

        try {
            const data = await apiClient<{
                status: string,
                result?: EvaluationResult,
                batch_data?: any,
                error?: string
            }>(`/evaluate-answer/status/${id}`);

            if (activeJobId.current !== id) return;

            // Handle batch mode responses
            if (data.batch_data) {
                const batchData = data.batch_data;
                const completed = batchData.completed_answers || 0;
                const total = batchData.total_answers || 0;
                const failed = batchData.failed_answers || 0;

                if (data.status === 'completed' || data.status === 'partial_failed') {
                    // Batch completed (fully or partially)
                    setStatusMessage(
                        `Batch complete: ${completed} completed, ${failed} failed out of ${total} answers`
                    );
                    // Store batch data in result for display
                    setResult({
                        question: `Batch Evaluation (${total} answers)`,
                        student_answer: "",
                        feedback: batchData as any,
                        word_count: 0,
                        success: true
                    });
                    setJobId(null);
                    activeJobId.current = null;
                } else if (data.status === 'cancelled' || data.status === 'failed') {
                    const cleanedError = data.error || "Batch evaluation failed";
                    setError(cleanedError);
                    setJobStatus('failed');
                    if (cleanedError.toLowerCase().includes("api key") || cleanedError.includes("API_KEY_INVALID")) {
                        setIsApiKeyValid('invalid');
                        setShowBanner(true);
                    }
                    setJobId(null);
                    activeJobId.current = null;
                } else {
                    // Still processing
                    setJobStatus('processing');
                    setStatusMessage(
                        `Processing batch: ${completed}/${total} completed${failed > 0 ? `, ${failed} failed` : ''}...`
                    );
                    setTimeout(() => pollStatus(id), 2000);
                }
                return;
            }

            // Handle single answer mode (existing logic)
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

        // Batch mode requires PDF only
        if (evaluationMode === "batch") {
            if (files.length === 0) {
                setError("Please upload a PDF file for batch evaluation.");
                return;
            }
            if (files.length > 1) {
                setError("Batch mode supports only a single PDF file with multiple answers.");
                return;
            }
            if (!files[0].name.toLowerCase().endsWith('.pdf')) {
                setError("Batch mode only supports PDF files. Please convert your images to PDF first.");
                return;
            }
        }

        setError(null);
        setResult(null);
        setJobId(null);
        setJobStatus('queued');
        setStatusMessage("Uploading and starting...");
        // Reset improved answer when starting a new evaluation
        resetImprovedAnswer();

        const formData = new FormData();

        if (evaluationMode === "batch") {
            // Batch mode: single PDF file
            formData.append("file", files[0]);
            if (useStandardFormat) {
                formData.append("use_standard_format", "true");
            }

            try {
                const data = await apiClient<{ job_id: string, status: string }>('/evaluate-answer/batch', {
                    method: 'POST',
                    body: formData,
                    headers: {},
                });

                if (data.job_id) {
                    setJobId(data.job_id);
                    setJobStatus('queued');
                    activeJobId.current = data.job_id;
                    setStatusMessage("Queued for batch evaluation...");
                    pollStatus(data.job_id);
                } else {
                    throw new Error("No job ID received");
                }
            } catch (err) {
                setJobStatus('failed');
                let message = "Batch evaluation failed";
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
        } else {
            // Single answer mode: existing flow
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
                                {/* Evaluation Mode Selection - At the top */}
                                <Label className="text-sm font-medium mb-2">Evaluation Mode</Label>
                                <div className="space-y-3 p-4 border rounded-lg bg-card">

                                    <RadioGroup
                                        value={evaluationMode}
                                        onValueChange={(value) => {
                                            setEvaluationMode(value as "single" | "batch");
                                            // Reset batch-specific state when switching modes
                                            if (value === "single") {
                                                setQuestionFile(null);
                                                setNumQuestions(1);
                                                setQuestionTexts([""]);
                                                setUseStandardFormat(false);
                                            }
                                        }}
                                        className="flex flex-start space-x-2"
                                    >
                                        <div className="flex items-center space-x-2">
                                            <RadioGroupItem value="single" id="single" />
                                            <Label htmlFor="single" className="cursor-pointer text-foreground">
                                                Single Answer
                                            </Label>
                                        </div>
                                        <div className="flex items-center space-x-2">
                                            <RadioGroupItem value="batch" id="batch" />
                                            <Label htmlFor="batch" className="cursor-pointer text-foreground">
                                                Multiple Answers
                                            </Label>
                                        </div>
                                    </RadioGroup>

                                    {evaluationMode === "batch" && (
                                        <div className="mt-3 pt-3 border-t space-y-2">
                                            <div className="flex items-center space-x-2">
                                                <Checkbox
                                                    id="standard-format"
                                                    checked={useStandardFormat}
                                                    onCheckedChange={(checked) => setUseStandardFormat(checked === true)}
                                                />
                                                <Label htmlFor="standard-format" className="cursor-pointer text-sm">
                                                    Use UPSC standard format
                                                </Label>
                                            </div>
                                            <p className="text-xs text-muted-foreground ml-6">
                                                2 pages for Q1-10 (10 marks), 3 pages for Q11-20 (15 marks)
                                            </p>
                                        </div>
                                    )}
                                </div>

                                {/* Batch Mode: Question Input Options */}
                                {evaluationMode === "batch" && (
                                    <div className="space-y-4 p-4 border rounded-lg bg-secondary/50">
                                        <Label className="text-sm font-medium">Question Reference (Optional but Recommended)</Label>
                                        <p className="text-xs text-muted-foreground mb-3">
                                            Provide questions to improve answer detection accuracy. Choose one option:
                                        </p>

                                        {/* Option 1: Upload Question File */}
                                        <div className="space-y-2">
                                            <Label className="text-sm font-medium">Option 1: Upload Question File</Label>
                                            <div className="flex items-center justify-center w-full">
                                                <label
                                                    htmlFor="question-file"
                                                    className={cn(
                                                        "flex flex-col items-center justify-center w-full h-24 border-2 border-dashed rounded-lg cursor-pointer bg-white hover:bg-gray-50 transition-colors",
                                                        questionFile ? "border-green-500 bg-green-50" : "border-gray-300"
                                                    )}
                                                >
                                                    <div className="flex flex-col items-center justify-center pt-3 pb-3">
                                                        {questionFile ? (
                                                            <>
                                                                <CheckCircle className="w-6 h-6 mb-1 text-green-500" />
                                                                <p className="text-xs text-green-700 font-medium truncate max-w-[200px]">
                                                                    {questionFile.name}
                                                                </p>
                                                                <p className="text-xs text-green-600">Click to change</p>
                                                            </>
                                                        ) : (
                                                            <>
                                                                <FileText className="w-6 h-6 mb-1 text-gray-400" />
                                                                <p className="text-xs text-gray-500">
                                                                    <span className="font-semibold">Click to upload</span> question paper
                                                                </p>
                                                                <p className="text-xs text-gray-400">PDF or Image (MAX. 10MB)</p>
                                                            </>
                                                        )}
                                                    </div>
                                                    <input
                                                        id="question-file"
                                                        type="file"
                                                        className="hidden"
                                                        onChange={(e) => {
                                                            if (e.target.files && e.target.files[0]) {
                                                                setQuestionFile(e.target.files[0]);
                                                                // Clear manual questions when file is uploaded
                                                                setNumQuestions(1);
                                                                setQuestionTexts([""]);
                                                            }
                                                        }}
                                                        accept=".pdf,image/*"
                                                    />
                                                </label>
                                            </div>
                                            {questionFile && (
                                                <Button
                                                    type="button"
                                                    variant="ghost"
                                                    size="sm"
                                                    onClick={() => setQuestionFile(null)}
                                                    className="text-xs"
                                                >
                                                    Remove question file
                                                </Button>
                                            )}
                                        </div>

                                        {/* Option 2: Manual Question Input */}
                                        <div className="space-y-2 pt-2 border-t">
                                            <div className="flex items-center justify-between">
                                                <Label className="text-sm font-medium">Option 2: Enter Questions Manually</Label>
                                                {!questionFile && (
                                                    <div className="flex items-center gap-2">
                                                        <Label className="text-xs text-muted-foreground">Number of questions:</Label>
                                                        <Input
                                                            type="number"
                                                            min="1"
                                                            max="20"
                                                            value={numQuestions}
                                                            onChange={(e) => {
                                                                const num = parseInt(e.target.value) || 1;
                                                                const clamped = Math.min(Math.max(1, num), 20);
                                                                setNumQuestions(clamped);
                                                                // Resize question texts array
                                                                const newTexts = [...questionTexts];
                                                                while (newTexts.length < clamped) {
                                                                    newTexts.push("");
                                                                }
                                                                while (newTexts.length > clamped) {
                                                                    newTexts.pop();
                                                                }
                                                                setQuestionTexts(newTexts);
                                                            }}
                                                            className="w-20 h-8 text-sm"
                                                        />
                                                    </div>
                                                )}
                                            </div>
                                            {!questionFile && numQuestions > 0 && (
                                                <div className="space-y-2 max-h-60 overflow-y-auto">
                                                    {questionTexts.map((text, idx) => (
                                                        <div key={idx} className="space-y-1">
                                                            <Label className="text-xs text-muted-foreground">
                                                                Question {idx + 1}:
                                                            </Label>
                                                            <Input
                                                                placeholder={`Enter question ${idx + 1} text...`}
                                                                value={text}
                                                                onChange={(e) => {
                                                                    const newTexts = [...questionTexts];
                                                                    newTexts[idx] = e.target.value;
                                                                    setQuestionTexts(newTexts);
                                                                }}
                                                                className="text-sm"
                                                            />
                                                        </div>
                                                    ))}
                                                </div>
                                            )}
                                        </div>
                                    </div>
                                )}

                                <div className="space-y-2">
                                    <label className="text-sm font-medium leading-none peer-disabled:cursor-not-allowed peer-disabled:opacity-70">
                                        {evaluationMode === "batch" ? (
                                            <>
                                                Answer PDF File <span className="text-red-500">*</span>{" "}
                                                <span className="text-xs text-muted-foreground font-normal">(Multiple answers in one PDF)</span>
                                            </>
                                        ) : (
                                            "Answer Files (PDF/Images) - Multiple pages supported"
                                        )}
                                    </label>
                                    {evaluationMode === "batch" && (
                                        <p className="text-xs text-red-600">
                                            ⚠️ It supports PDF format only. Please convert to PDF before uploading.
                                        </p>
                                    )}
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
                                                        {evaluationMode === "batch" ? (
                                                            <p className="text-xs text-green-600">PDF file ready</p>
                                                        ) : (
                                                            <p className="text-xs text-green-600">Click to add more</p>
                                                        )}
                                                    </>
                                                ) : (
                                                    <>
                                                        <Upload className="w-8 h-8 mb-2 text-gray-400" />
                                                        <p className="mb-2 text-sm text-gray-500">
                                                            <span className="font-semibold">Click to upload</span> or drag and drop
                                                        </p>
                                                        <p className="text-xs text-gray-500">
                                                            {evaluationMode === "batch"
                                                                ? "PDF only (MAX. 50MB)"
                                                                : "PDF, PNG, JPG (MAX. 10MB each)"}
                                                        </p>
                                                    </>
                                                )}
                                            </div>
                                            <input
                                                id="dropzone-file"
                                                type="file"
                                                className="hidden"
                                                onChange={handleFileChange}
                                                accept={evaluationMode === "batch" ? ".pdf" : ".pdf,image/*"}
                                                multiple={evaluationMode !== "batch"}
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

                                {/* Single Mode: Question Input */}
                                {evaluationMode === "single" && (
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
                                )}


                                {error && (
                                    <div className="p-4 text-base font-semibold text-red-700 bg-red-50 rounded-lg border-2 border-red-500 flex items-center gap-3">
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
                                                {evaluationMode === "batch" ? "Batch Evaluated" : "Evaluated"}
                                            </>
                                        ) : (
                                            evaluationMode === "batch" ? "Evaluate Batch Answers" : "Evaluate Answer"
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
                                    <CardTitle className="text-lg text-blue-900">Question</CardTitle>
                                </CardHeader>
                                <CardContent>
                                    <p className="text-blue-800 font-medium">
                                        {result.question || "Question extracted from uploaded file"}
                                    </p>
                                    {(result.marks || result.word_count) && (
                                        <div className="mt-3 flex gap-4 text-sm text-blue-700">
                                            {result.marks && (
                                                <span className="font-semibold">
                                                    Marks: {result.marks}
                                                </span>
                                            )}
                                            {result.word_count && (
                                                <span className="font-semibold">
                                                    Word Count: {result.word_count}
                                                </span>
                                            )}
                                        </div>
                                    )}
                                </CardContent>
                            </Card>
                            {/* Examiner Expectation Blueprint */}
                            {result.feedback.examiner_expectation_blueprint && (
                                <Card className="border-l-4 border-l-blue-500">
                                    <CardHeader className="pb-2">
                                        <CardTitle className="text-base text-blue-700">Examiner's Expectation Blueprint</CardTitle>
                                        <CardDescription className="text-xs">
                                            What the examiner expects for this question
                                        </CardDescription>
                                    </CardHeader>
                                    <CardContent className="space-y-4 text-sm">
                                        {result.feedback.examiner_expectation_blueprint.key_demands_of_the_question && result.feedback.examiner_expectation_blueprint.key_demands_of_the_question.length > 0 && (
                                            <div>
                                                <h4 className="font-semibold text-gray-900 mb-2">Key Demands of the Question</h4>
                                                <ul className="list-disc pl-4 space-y-1 text-gray-700">
                                                    {result.feedback.examiner_expectation_blueprint.key_demands_of_the_question.map((demand: string, i: number) => (
                                                        <li key={i}>{demand}</li>
                                                    ))}
                                                </ul>
                                            </div>
                                        )}
                                        {result.feedback.examiner_expectation_blueprint.ideal_logical_structure && (
                                            <div>
                                                <h4 className="font-semibold text-gray-900 mb-2">Ideal Logical Structure</h4>
                                                <div className="space-y-3 pl-4 border-l-2 border-blue-200">
                                                    <div>
                                                        <span className="font-medium text-blue-700">Introduction: </span>
                                                        <div className="text-gray-700 whitespace-pre-line mt-1">
                                                            {formatBlueprintText(result.feedback.examiner_expectation_blueprint.ideal_logical_structure.introduction)}
                                                        </div>
                                                    </div>
                                                    <div>
                                                        <span className="font-medium text-blue-700">Body: </span>
                                                        <div className="text-gray-700 whitespace-pre-line mt-1">
                                                            {formatBlueprintText(result.feedback.examiner_expectation_blueprint.ideal_logical_structure.body)}
                                                        </div>
                                                    </div>
                                                    <div>
                                                        <span className="font-medium text-blue-700">Conclusion: </span>
                                                        <div className="text-gray-700 whitespace-pre-line mt-1">
                                                            {formatBlueprintText(result.feedback.examiner_expectation_blueprint.ideal_logical_structure.conclusion)}
                                                        </div>
                                                    </div>
                                                </div>
                                            </div>
                                        )}
                                        {result.feedback.examiner_expectation_blueprint.non_negotiables && result.feedback.examiner_expectation_blueprint.non_negotiables.length > 0 && (
                                            <div>
                                                <h4 className="font-semibold text-gray-900 mb-2">Non-Negotiable Elements</h4>
                                                <ul className="list-disc pl-4 space-y-1 text-gray-700">
                                                    {result.feedback.examiner_expectation_blueprint.non_negotiables.map((item: string, i: number) => (
                                                        <li key={i}>{item}</li>
                                                    ))}
                                                </ul>
                                            </div>
                                        )}
                                    </CardContent>
                                </Card>
                            )}

                            {/* Margin Comments - Displayed Fisrt */}
                            {result.feedback.margin_comments && result.feedback.margin_comments.length > 0 && (
                                <Card className="border-l-4 border-l-indigo-500">
                                    <CardHeader className="pb-3">
                                        <CardTitle className="text-base text-indigo-700 flex items-center gap-2">
                                            <BookOpen className="h-5 w-5" />
                                            Margin Comments
                                        </CardTitle>
                                        <CardDescription className="text-xs">
                                            Examiner-style annotations on specific parts of your answer
                                        </CardDescription>
                                    </CardHeader>
                                    <CardContent>
                                        <div className="space-y-3">
                                            {result.feedback.margin_comments.map((comment, idx) => {
                                                const severityColors: Record<string, string> = {
                                                    low: "bg-blue-50 border-blue-200 text-blue-800",
                                                    medium: "bg-amber-50 border-amber-200 text-amber-800",
                                                    high: "bg-red-50 border-red-200 text-red-800"
                                                };
                                                const typeColors: Record<string, string> = {
                                                    strength: "text-green-700",
                                                    weakness: "text-red-700",
                                                    omission: "text-orange-700",
                                                    directive_misalignment: "text-purple-700",
                                                    evidence_gap: "text-yellow-700",
                                                    structure_issue: "text-pink-700",
                                                    visual_gap: "text-cyan-700"
                                                };

                                                const severity = (comment.severity || "low").toLowerCase();
                                                const severityColor = severityColors[severity] || severityColors.low;

                                                return (
                                                    <div
                                                        key={idx}
                                                        className={`p-3 rounded-lg border-l-4 ${severityColor}`}
                                                    >
                                                        <div className="flex items-start justify-between gap-2 mb-1">
                                                            <div className="flex-1">
                                                                <div className="flex items-center gap-2 mb-1">
                                                                    <span className="text-xs font-semibold px-2 py-0.5 rounded bg-white/50">
                                                                        {comment.comment_type.replace(/_/g, ' ').toUpperCase()}
                                                                    </span>
                                                                    <span className={`text-xs font-medium ${typeColors[comment.comment_type] || 'text-gray-700'}`}>
                                                                        {severity.toUpperCase()} SEVERITY
                                                                    </span>
                                                                </div>
                                                                <p className="text-sm font-medium text-gray-900 mb-1">
                                                                    <span className="italic">"{comment.anchor_text}"</span>
                                                                </p>
                                                                <p className="text-sm text-gray-800">
                                                                    {comment.comment}
                                                                </p>
                                                                {comment.suggested_fix && (
                                                                    <div className="mt-2 pt-2 border-t border-gray-300">
                                                                        <p className="text-xs font-semibold text-gray-700 mb-1">Suggested Fix:</p>
                                                                        <p className="text-xs text-gray-600">{comment.suggested_fix}</p>
                                                                    </div>
                                                                )}
                                                            </div>
                                                        </div>
                                                    </div>
                                                );
                                            })}
                                        </div>
                                    </CardContent>
                                </Card>
                            )}

                            {/* Directive Alignment */}
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

                            {/* Feedback Grid */}
                            <div className="grid gap-4 md:grid-cols-2">
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

                                {/* Critical Gaps and Remedies */}
                                <Card className="border-l-4 border-l-red-500">
                                    <CardHeader className="pb-2">
                                        <CardTitle className="text-base text-red-700">Critical Gaps & Remedies</CardTitle>
                                        <CardDescription className="text-xs">
                                            Key issues and how to fix them
                                        </CardDescription>
                                    </CardHeader>
                                    <CardContent>
                                        {result.feedback.critical_gaps_and_remedies && result.feedback.critical_gaps_and_remedies.length > 0 ? (
                                            <div className="space-y-3">
                                                {result.feedback.critical_gaps_and_remedies.map((item, i) => (
                                                    <div key={i} className="p-3 bg-red-50/50 rounded-md border border-red-100">
                                                        <div className="mb-2">
                                                            <span className="text-xs font-semibold text-red-800 uppercase">Gap:</span>
                                                            <p className="text-sm text-gray-800 mt-1">{item.gap}</p>
                                                        </div>
                                                        <div>
                                                            <span className="text-xs font-semibold text-green-800 uppercase">Remedy:</span>
                                                            <p className="text-sm text-gray-700 mt-1 font-medium">{item.remedy}</p>
                                                        </div>
                                                    </div>
                                                ))}
                                            </div>
                                        ) : (
                                            // Fallback to legacy fields for backward compatibility
                                            <>
                                                {(result.feedback.missing_elements && result.feedback.missing_elements.length > 0) ||
                                                    (result.feedback.improvements_needed && result.feedback.improvements_needed.length > 0) ? (
                                                    <div className="space-y-3">
                                                        {result.feedback.missing_elements && result.feedback.missing_elements.length > 0 && (
                                                            <div>
                                                                <span className="text-xs font-semibold text-red-800 uppercase">Missing Elements:</span>
                                                                <ul className="list-disc pl-4 space-y-1 text-sm text-gray-700 mt-1">
                                                                    {result.feedback.missing_elements.map((item, i) => (
                                                                        <li key={i}>{item}</li>
                                                                    ))}
                                                                </ul>
                                                            </div>
                                                        )}
                                                        {result.feedback.improvements_needed && result.feedback.improvements_needed.length > 0 && (
                                                            <div>
                                                                <span className="text-xs font-semibold text-green-800 uppercase">Improvements:</span>
                                                                <ul className="list-disc pl-4 space-y-1 text-sm text-gray-700 mt-1">
                                                                    {result.feedback.improvements_needed.map((item, i) => (
                                                                        <li key={i}>{item}</li>
                                                                    ))}
                                                                </ul>
                                                            </div>
                                                        )}
                                                    </div>
                                                ) : (
                                                    <p className="text-sm text-gray-500 italic">No critical gaps identified</p>
                                                )}
                                            </>
                                        )}
                                    </CardContent>
                                </Card>
                            </div>

                            {/* Section-wise Assessment */}
                            {result.feedback.section_wise_assessment && (
                                <Card className="border-l-4 border-l-teal-500">
                                    <CardHeader className="pb-2">
                                        <CardTitle className="text-base text-teal-700">Section-wise Assessment</CardTitle>
                                        <CardDescription className="text-xs">
                                            Detailed evaluation of each section
                                        </CardDescription>
                                    </CardHeader>
                                    <CardContent className="space-y-3 text-sm">
                                        <div>
                                            <h4 className="font-semibold text-gray-900 mb-1">Introduction</h4>
                                            <p className="text-gray-700">{result.feedback.section_wise_assessment.introduction}</p>
                                        </div>
                                        <div>
                                            <h4 className="font-semibold text-gray-900 mb-1">Body</h4>
                                            <p className="text-gray-700">{result.feedback.section_wise_assessment.body}</p>
                                        </div>
                                        <div>
                                            <h4 className="font-semibold text-gray-900 mb-1">Conclusion</h4>
                                            <p className="text-gray-700">{result.feedback.section_wise_assessment.conclusion}</p>
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
                                    {result.feedback.section_wise_assessment ? (
                                        // If section_wise_assessment exists, don't show structure_feedback separately
                                        null
                                    ) : result.feedback.structure_feedback ? (
                                        <div>
                                            <h4 className="font-semibold text-gray-900 mb-1">Structure & Format</h4>
                                            <p className="text-gray-600">{result.feedback.structure_feedback}</p>
                                        </div>
                                    ) : null}
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

                            {/* Generate Improved Answer Button or Display Improved Answer */}
                            {result.improved_answer ? (
                                // Legacy format: Show improved answer directly (backward compatibility)
                                <div className="space-y-4">
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
                            ) : (
                                // New format: Show button to generate improved answer
                                <Card className="border-2 border-dashed border-indigo-200 bg-indigo-50/30">
                                    <CardContent className="p-6 flex flex-col items-center justify-center text-center space-y-4">
                                        <div className="bg-indigo-100 p-3 rounded-full">
                                            <FileText className="h-6 w-6 text-indigo-600" />
                                        </div>
                                        <div>
                                            <h3 className="text-lg font-semibold text-gray-900 mb-2">Generate Improved Answer</h3>
                                            <p className="text-sm text-gray-600 max-w-md">
                                                Based on the feedback above, generate an improved model answer with retrieval, current affairs, and enhanced content.
                                            </p>
                                        </div>
                                        <Button
                                            onClick={handleGenerateImprovedAnswer}
                                            disabled={
                                                improvedAnswerStatus === 'pending' ||
                                                improvedAnswerStatus === 'processing' ||
                                                improvedAnswerStatus === 'queued' ||
                                                !!improvedAnswerResult
                                            }
                                            className={improvedAnswerResult ? "bg-green-500 hover:bg-green-500 cursor-not-allowed" : "bg-indigo-300 hover:bg-indigo-400"}
                                        >
                                            {improvedAnswerStatus === 'pending' || improvedAnswerStatus === 'processing' || improvedAnswerStatus === 'queued' ? (
                                                <>
                                                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                                                    Generating...
                                                </>
                                            ) : improvedAnswerResult ? (
                                                <>
                                                    <CheckCircle className="mr-2 h-4 w-4" />
                                                    Generated
                                                </>
                                            ) : (
                                                <>
                                                    <RefreshCw className="mr-2 h-4 w-4" />
                                                    Generate Improved Answer
                                                </>
                                            )}
                                        </Button>
                                        {improvedAnswerError && (
                                            <div className="text-sm text-red-600 bg-red-50 p-2 rounded">
                                                {improvedAnswerError}
                                            </div>
                                        )}
                                    </CardContent>
                                </Card>
                            )}

                            {/* Improved Answer Result (from separate generation) */}
                            {improvedAnswerResult && (
                                <div className="space-y-4 mt-4">
                                    {/* Sources Info Card */}
                                    {improvedAnswerResult.sources && improvedAnswerResult.sources.length > 0 && (
                                        <Card className="border-l-4 border-l-blue-500 bg-blue-50/30">
                                            <CardHeader className="pb-2">
                                                <CardTitle className="text-sm text-blue-900 flex items-center gap-2">
                                                    <BookOpen className="h-4 w-4" />
                                                    Sources Used ({improvedAnswerResult.sources.length})
                                                </CardTitle>
                                            </CardHeader>
                                            <CardContent>
                                                <div className="flex flex-wrap gap-2 text-xs">
                                                    {improvedAnswerResult.sources.slice(0, 5).map((source: any, idx: number) => (
                                                        <span key={idx} className="px-2 py-1 bg-white rounded border border-blue-200 text-blue-700">
                                                            {source.filename || source.content_source || `Source ${idx + 1}`}
                                                        </span>
                                                    ))}
                                                    {improvedAnswerResult.sources.length > 5 && (
                                                        <span className="px-2 py-1 bg-white rounded border border-blue-200 text-blue-700">
                                                            +{improvedAnswerResult.sources.length - 5} more
                                                        </span>
                                                    )}
                                                </div>
                                            </CardContent>
                                        </Card>
                                    )}
                                    {improvedAnswerResult.compressed_answer && (
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
                                                        {improvedAnswerResult.word_count_compressed} words • Optimized for quick reading
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
                                                            {improvedAnswerResult.compressed_answer}
                                                        </ReactMarkdown>
                                                    </div>
                                                </CardContent>
                                            )}
                                        </Card>
                                    )}
                                    <Card className={cn(
                                        "overflow-hidden",
                                        improvedAnswerResult.compressed_answer ? "border-dashed border-gray-300" : "border-2 border-indigo-100 shadow-sm"
                                    )}>
                                        <button
                                            type="button"
                                            onClick={() => setShowOriginal(!showOriginal)}
                                            className={cn(
                                                "w-full flex items-center justify-between p-4 transition-colors border-b",
                                                improvedAnswerResult.compressed_answer ? "bg-gray-50/50 hover:bg-gray-100/50" : "bg-indigo-50/50 hover:bg-indigo-100/50"
                                            )}
                                        >
                                            <div className="flex flex-col items-start gap-1">
                                                <div className={cn(
                                                    "flex items-center gap-2 font-semibold",
                                                    improvedAnswerResult.compressed_answer ? "text-gray-700" : "text-indigo-900"
                                                )}>
                                                    <FileText className="h-4 w-4" />
                                                    {improvedAnswerResult.compressed_answer ? "Original Model Solution" : "Model Solution"}
                                                </div>
                                                <div className="text-xs text-muted-foreground">
                                                    {improvedAnswerResult.word_count_actual} words • Comprehensive version
                                                </div>
                                            </div>
                                            <ChevronDown className={cn(
                                                "h-4 w-4 transition-transform",
                                                improvedAnswerResult.compressed_answer ? "text-gray-400" : "text-indigo-400",
                                                (showOriginal || !improvedAnswerResult.compressed_answer) && "rotate-180"
                                            )} />
                                        </button>
                                        {(showOriginal || !improvedAnswerResult.compressed_answer) && (
                                            <CardContent className="p-6">
                                                <div className="prose prose-indigo max-w-none prose-headings:text-indigo-900">
                                                    <ReactMarkdown
                                                        remarkPlugins={[remarkGfm]}
                                                        components={markdownComponents}
                                                        urlTransform={urlTransform}
                                                    >
                                                        {improvedAnswerResult.improved_answer}
                                                    </ReactMarkdown>
                                                </div>
                                            </CardContent>
                                        )}
                                    </Card>
                                </div>
                            )}
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
