"use client";

import { useState, useRef, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { Label } from "@/components/ui/label";
import { Checkbox } from "@/components/ui/checkbox";
import { fetchApi, API_URL } from "@/lib/api";
import { Upload, FileText, CheckCircle, AlertCircle, Loader2, BookOpen, RefreshCw } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { markdownComponents, urlTransform } from "@/components/ui/mermaid";
import { cn } from "@/lib/utils";
import ApiKeyBanner from "@/components/layout/ApiKeyBanner";
import { EvaluationResult, BatchData, BatchAnswerResult } from "@/stores/types";
import { EvaluationResultCard } from "@/components/evaluate/EvaluationResultCard";
import { apiClient, ApiError, api, showToast } from "@/lib/apiClient";
import { useEvaluateAnswerStore } from "@/stores";
import { useAuth } from "@/context/AuthContext";
import { PageContainer } from "@/components/layout/PageContainer";

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
        evaluationMode,
        setEvaluationMode,
    } = useEvaluateAnswerStore();

    const [files, setFiles] = useState<File[]>([]);
    const [showCompressed, setShowCompressed] = useState(true);
    const [showOriginal, setShowOriginal] = useState(false);
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
        setFiles([]);
        setShowCompressed(true);
        setShowOriginal(false);
        setUseStandardFormat(false);
        setError(null);
        setJobId(null);
        setJobStatus('idle');
        setStatusMessage("Evaluating...");
        setQuestionFile(null);
        setNumQuestions(1);
        setQuestionTexts([""]);
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
        // TODO: REVERT FOR PROD — remove the hasLocalKey bypass below and restore:
        //   if (!user || user.has_gemini_api_key === false || isApiKeyValid === 'invalid') {
        // No-auth India mode: if a local key exists in localStorage, skip this check
        const hasLocalKey = typeof window !== 'undefined' && !!localStorage.getItem('gemini_api_key');
        if (!hasLocalKey && (!user || user.has_gemini_api_key === false || isApiKeyValid === 'invalid')) {
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
        <PageContainer
            title="Evaluate answer"
            description="Upload your handwritten answer for AI-powered evaluation and improvement."
        >
            <div className="w-full space-y-8">
                <ApiKeyBanner
                    showBanner={showBanner}
                    onKeySet={() => {
                        setShowBanner(false);
                        setError("");
                        // Skip verification since the key was just validated during save
                        refreshUser(true);
                    }}
                />

                <div className="grid gap-8">
                {/* Input Section */}
                <div className="lg:col-span-2 space-y-6">
                    <Card className="border-[var(--card-border)] shadow-sm">
                        <CardHeader className="border-b border-[var(--card-border)] bg-[var(--bg-secondary)] rounded-t-xl pb-4">
                            <div className="flex items-center justify-between">
                                <div>
                                    <CardTitle className="text-xl font-bold text-[var(--text)]">Upload & configure</CardTitle>
                                    <CardDescription className="text-[var(--text-muted)] mt-1">Provide your answer details</CardDescription>
                                </div>
                                {result && (
                                    <Button
                                        variant="outline"
                                        size="sm"
                                        onClick={handleReset}
                                        className="flex items-center gap-2"
                                    >
                                        <RefreshCw className="h-4 w-4" />
                                        New evaluation
                                    </Button>
                                )}
                            </div>
                        </CardHeader>
                        <CardContent className="pt-6">
                            <form onSubmit={handleSubmit} className="space-y-4">
                                {/* Evaluation Mode Selection - At the top */}
                                <Label className="text-sm font-semibold text-[var(--text)] uppercase tracking-wide mb-2 block">Evaluation mode</Label>
                                <div className="space-y-3 p-5 border border-[var(--card-border)] rounded-xl bg-[var(--bg-secondary)]">

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
                                        className="flex flex-start gap-6"
                                    >
                                        <div className="flex items-center space-x-2">
                                            <RadioGroupItem value="single" id="single" className="text-amber-600 border-[var(--card-border)] focus:border-amber-600 focus:ring-amber-600/20" />
                                            <Label htmlFor="single" className="cursor-pointer font-medium text-[var(--text)]">
                                                Single answer
                                            </Label>
                                        </div>
                                        <div className="flex items-center space-x-2">
                                            <RadioGroupItem value="batch" id="batch" className="text-amber-600 border-[var(--card-border)] focus:border-amber-600 focus:ring-amber-600/20" />
                                            <Label htmlFor="batch" className="cursor-pointer font-medium text-[var(--text)]">
                                                Multiple answers
                                            </Label>
                                        </div>
                                    </RadioGroup>

                                    {evaluationMode === "batch" && (
                                        <div className="mt-4 pt-4 border-t border-[var(--card-border)] space-y-2">
                                            <div className="flex items-center space-x-2">
                                                <Checkbox
                                                    id="standard-format"
                                                    checked={useStandardFormat}
                                                    onCheckedChange={(checked) => setUseStandardFormat(checked === true)}
                                                    className="border-[var(--card-border)] data-[state=checked]:bg-amber-600 data-[state=checked]:text-white"
                                                />
                                                <Label htmlFor="standard-format" className="cursor-pointer text-sm font-medium text-[var(--text)]">
                                                    Use UPSC standard format
                                                </Label>
                                            </div>
                                            <p className="text-xs text-[var(--text-muted)] ml-6">
                                                2 pages for Q1-10 (10 marks), 3 pages for Q11-20 (15 marks)
                                            </p>
                                        </div>
                                    )}
                                </div>

                                {/* Batch Mode: Question Input Options */}
                                {evaluationMode === "batch" && (
                                    <div className="space-y-4 p-5 border border-[var(--card-border)] rounded-xl bg-[var(--bg-secondary)]">
                                        <Label className="text-sm font-semibold uppercase tracking-wide text-[var(--text)]">Question reference <span className="text-[var(--text-muted)] lowercase font-normal tracking-normal">(optional but recommended)</span></Label>
                                        <p className="text-[13px] text-[var(--text-muted)] mb-3 leading-relaxed">
                                            Provide questions to improve answer detection accuracy. Choose one option:
                                        </p>

                                        {/* Option 1: Upload Question File */}
                                        <div className="space-y-3">
                                            <Label className="text-sm font-medium text-[var(--text)]">Option 1: Upload question file</Label>
                                            <div className="flex items-center justify-center w-full">
                                                <label
                                                    htmlFor="question-file"
                                                    className={cn(
                                                        "flex flex-col items-center justify-center w-full h-24 border-2 border-dashed rounded-xl cursor-pointer bg-[var(--card)] hover:bg-[var(--bg-tertiary)] transition-colors",
                                                        questionFile ? "border-amber-500 bg-amber-50/10" : "border-[var(--card-border)]"
                                                    )}
                                                >
                                                    <div className="flex flex-col items-center justify-center pt-3 pb-3">
                                                        {questionFile ? (
                                                            <>
                                                                <CheckCircle className="w-6 h-6 mb-1 text-amber-600" />
                                                                <p className="text-xs text-amber-900 font-medium truncate max-w-[200px] dark:text-amber-500">
                                                                    {questionFile.name}
                                                                </p>
                                                                <p className="text-[11px] text-amber-600/80 mt-1">Click to change</p>
                                                            </>
                                                        ) : (
                                                            <>
                                                                <FileText className="w-6 h-6 mb-2 text-[var(--text-faint)]" />
                                                                <p className="text-xs text-[var(--text-muted)]">
                                                                    <span className="font-semibold text-[var(--text)]">Click to upload</span> question paper
                                                                </p>
                                                                <p className="text-[11px] text-[var(--text-faint)] mt-1">PDF or image (MAX. 10MB)</p>
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
                                        <div className="space-y-4 pt-4 border-t border-[var(--card-border)]">
                                            <div className="flex items-center justify-between">
                                                <Label className="text-sm font-medium text-[var(--text)]">Option 2: Enter questions manually</Label>
                                                {!questionFile && (
                                                    <div className="flex items-center gap-2">
                                                        <Label className="text-[13px] text-[var(--text-muted)]">Number of questions:</Label>
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
                                                            className="w-20 text-sm h-9 bg-[var(--card)]"
                                                        />
                                                    </div>
                                                )}
                                            </div>
                                            {!questionFile && numQuestions > 0 && (
                                                <div className="space-y-3 max-h-60 overflow-y-auto pr-1">
                                                    {questionTexts.map((text, idx) => (
                                                        <div key={idx} className="space-y-1.5">
                                                            <Label className="text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wide">
                                                                Question {idx + 1}
                                                            </Label>
                                                            <Input
                                                                placeholder={`Enter question ${idx + 1} text...`}
                                                                value={text}
                                                                onChange={(e) => {
                                                                    const newTexts = [...questionTexts];
                                                                    newTexts[idx] = e.target.value;
                                                                    setQuestionTexts(newTexts);
                                                                }}
                                                                className="text-sm bg-[var(--card)]"
                                                            />
                                                        </div>
                                                    ))}
                                                </div>
                                            )}
                                        </div>
                                    </div>
                                )}

                                <div className="space-y-2">
                                    <label className="text-sm font-semibold text-[var(--text)] block uppercase tracking-wide leading-none peer-disabled:cursor-not-allowed peer-disabled:opacity-70">
                                        {evaluationMode === "batch" ? (
                                            <>
                                                Answer PDF file <span className="text-amber-600">*</span>{" "}
                                                <span className="text-[11px] text-[var(--text-muted)] font-normal lowercase tracking-normal">(multiple answers in one PDF)</span>
                                            </>
                                        ) : (
                                            "Answer files (PDF/Images) - multiple pages supported"
                                        )}
                                    </label>
                                    {evaluationMode === "batch" && (
                                        <p className="text-xs text-amber-600 font-medium">
                                            ⚠️ It supports PDF format only. Please convert to PDF before uploading.
                                        </p>
                                    )}
                                    <div className="flex items-center justify-center w-full mt-2">
                                        <label
                                            htmlFor="dropzone-file"
                                            className={cn(
                                                "flex flex-col items-center justify-center w-full h-32 border-2 border-dashed rounded-xl cursor-pointer bg-[var(--bg-secondary)] hover:bg-[var(--bg-tertiary)] transition-colors",
                                                files.length > 0 ? "border-amber-500 bg-amber-50/10" : "border-[var(--card-border)]"
                                            )}
                                        >
                                            <div className="flex flex-col items-center justify-center pt-5 pb-6">
                                                {files.length > 0 ? (
                                                    <>
                                                        <CheckCircle className="w-8 h-8 mb-2 text-amber-600" />
                                                        <p className="mb-2 text-sm text-[var(--text)] font-semibold">
                                                            {files.length} file{files.length > 1 ? 's' : ''} selected
                                                        </p>
                                                        {evaluationMode === "batch" ? (
                                                            <p className="text-[13px] text-amber-600/90 font-medium">PDF file ready</p>
                                                        ) : (
                                                            <p className="text-[13px] text-amber-600/90 font-medium">Click to add more</p>
                                                        )}
                                                    </>
                                                ) : (
                                                    <>
                                                        <Upload className="w-8 h-8 mb-3 text-[var(--text-faint)]" />
                                                        <p className="mb-2 text-sm text-[var(--text-muted)]">
                                                            <span className="font-semibold text-[var(--text)]">Click to upload</span> or drag and drop
                                                        </p>
                                                        <p className="text-[13px] text-[var(--text-faint)]">
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
                                        <div className="mt-4 space-y-2 max-h-48 overflow-y-auto pr-2">
                                            {files.map((file, index) => (
                                                <div key={index} className="flex items-center justify-between p-3 bg-[var(--bg-secondary)] border border-[var(--card-border)] rounded-lg">
                                                    <div className="flex items-center gap-3 flex-1 min-w-0">
                                                        <FileText className="h-4 w-4 text-amber-600/70 flex-shrink-0" />
                                                        <span className="text-sm font-semibold text-[var(--text)] truncate">{file.name}</span>
                                                        <span className="text-[13px] text-[var(--text-faint)] font-medium flex-shrink-0">({(file.size / 1024).toFixed(1)} KB)</span>
                                                    </div>
                                                    <Button
                                                        type="button"
                                                        variant="ghost"
                                                        size="sm"
                                                        onClick={() => removeFile(index)}
                                                        className="h-7 w-7 p-0 flex-shrink-0 text-[var(--text-muted)] hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-950/30 rounded-full"
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
                                    <div className="space-y-1.5">
                                        <label className="text-sm font-semibold text-[var(--text)] uppercase tracking-wide">Question <span className="text-[var(--text-muted)] lowercase font-normal tracking-normal">(optional)</span></label>
                                        <Input
                                            placeholder="Enter the question text..."
                                            value={question}
                                            onChange={(e) => setQuestion(e.target.value)}
                                            className="bg-[var(--card)] text-[var(--text)] border-[var(--card-border)]"
                                        />
                                        <p className="text-[13px] text-[var(--text-muted)] font-medium mt-1">
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

                                <div className="flex gap-3 pt-2">
                                    <Button
                                        type="submit"
                                        className={cn(
                                            "w-full h-12 text-base font-bold transition-all duration-300 shadow-sm",
                                            result
                                                ? "bg-amber-600 hover:bg-amber-700 text-white"
                                                : ""
                                        )}
                                        disabled={loading || files.length === 0}
                                    >
                                        {loading ? (
                                            <>
                                                <Loader2 className="mr-2 h-5 w-5 animate-spin text-amber-200" />
                                                {statusMessage}
                                            </>
                                        ) : result ? (
                                            <>
                                                <CheckCircle className="mr-2 h-5 w-5" />
                                                {evaluationMode === "batch" ? "Batch evaluated" : "Evaluated"}
                                            </>
                                        ) : (
                                            evaluationMode === "batch" ? "Evaluate batch answers" : "Evaluate answer"
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
                        <div className="space-y-6 pt-2 animate-fade-up">
                            {/* Global Reset Button in Results Header */}
                            <div className="flex justify-between items-center bg-[var(--bg-secondary)] p-4 md:p-5 rounded-xl border border-[var(--card-border)] shadow-sm">
                                <h2 className="text-xl font-bold text-[var(--text)]">
                                    {evaluationMode === "batch" ? "Batch evaluation results" : "Evaluation result"}
                                </h2>
                                <Button
                                    variant="outline"
                                    onClick={handleReset}
                                    className="flex items-center gap-2 border-[var(--card-border)] text-[var(--text-muted)] hover:text-[var(--text)]"
                                >
                                    <RefreshCw className="h-4 w-4" />
                                    New evaluation
                                </Button>
                            </div>

                            {evaluationMode === "batch" && (result.feedback as any).answers ? (
                                (result.feedback as any).answers.map((answer: any, i: number) => (
                                    <div key={answer.answer_id || i} className="pb-4">
                                        {answer.status === 'completed' && answer.evaluation ? (
                                            <EvaluationResultCard
                                                result={answer.evaluation}
                                                index={i}
                                                files={files}
                                                isCollapsible={true}
                                                defaultExpanded={i === 0}
                                            />
                                        ) : (
                                            <Card className="bg-red-50 border-red-100">
                                                <CardHeader>
                                                    <CardTitle className="text-red-900">
                                                        Answer {i + 1} Failed
                                                    </CardTitle>
                                                </CardHeader>
                                                <CardContent>
                                                    <p className="text-red-800 font-medium">
                                                        {answer.error || "An error occurred during evaluation of this segment."}
                                                    </p>
                                                </CardContent>
                                            </Card>
                                        )}
                                    </div>
                                ))
                            ) : (
                                <EvaluationResultCard
                                    result={result}
                                    files={files}
                                    isCollapsible={true}
                                    defaultExpanded={true}
                                />
                            )}
                        </div>
                    ) : (
                        <div className="h-full flex flex-col items-center justify-center text-center p-12 border-2 border-dashed border-[var(--card-border)] rounded-xl bg-[var(--bg-secondary)]/50 min-h-[300px]">
                            <div className="bg-[var(--card)] p-4 rounded-full shadow-sm mb-5 border border-[var(--card-border)]">
                                <FileText className="h-8 w-8 text-amber-600/60" />
                            </div>
                            <h3 className="text-lg font-bold text-[var(--text)]">No evaluation yet</h3>
                            <p className="text-[15px] text-[var(--text-muted)] max-w-sm mt-3 leading-relaxed">
                                Upload your answer sheet on the left to receive detailed AI feedback and an improved model answer.
                            </p>
                        </div>
                    )}
                </div>
            </div>
            </div>
        </PageContainer>
    );
}
