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
                            {/* Global Reset Button in Results Header */}
                            <div className="flex justify-between items-center bg-white p-4 rounded-lg border shadow-sm">
                                <h2 className="text-xl font-semibold text-foreground">
                                    {evaluationMode === "batch" ? "Batch Evaluation Results" : "Evaluation Result"}
                                </h2>
                                <Button
                                    variant="outline"
                                    onClick={handleReset}
                                    className="flex items-center gap-2 border-primary/20 hover:border-primary/50"
                                >
                                    <RefreshCw className="h-4 w-4" />
                                    New Evaluation
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
        </div>
    );
}
