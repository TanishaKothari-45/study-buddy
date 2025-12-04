"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { fetchApi, API_URL } from "@/lib/api";
import { Upload, FileText, CheckCircle, AlertCircle, Loader2, BookOpen } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { markdownComponents, urlTransform } from "@/components/ui/mermaid";
import { cn } from "@/lib/utils";

interface Feedback {
    strengths: string[];
    missing_elements: string[];
    improvements_needed: string[];
    structure_feedback: string;
    evidence_feedback: string;
    overall_assessment: string;
}

interface EvaluationResult {
    question: string;
    student_answer: string;
    improved_answer: string;
    feedback: Feedback;
    sources: any[];
    current_affairs_count: number;
}

export default function EvaluatePage() {
    const [files, setFiles] = useState<File[]>([]);

    const [question, setQuestion] = useState("");
    const [loading, setLoading] = useState(false);
    const [result, setResult] = useState<EvaluationResult | null>(null);
    const [error, setError] = useState("");

    const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
        if (e.target.files && e.target.files.length > 0) {
            const newFiles = Array.from(e.target.files);
            setFiles(prev => [...prev, ...newFiles]);
        }
    };

    const removeFile = (index: number) => {
        setFiles(prev => prev.filter((_, i) => i !== index));
    };

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        if (files.length === 0) {
            setError("Please select at least one file to upload.");
            return;
        }

        setLoading(true);
        setError("");
        setResult(null);

        const formData = new FormData();
        files.forEach((file) => {
            formData.append("files", file);
        });
        if (question) formData.append("question", question);

        try {
            // We need to use fetch directly for FormData instead of our JSON wrapper
            const res = await fetch(`${API_URL}/evaluate-answer/`, {
                method: "POST",
                body: formData,
            });

            if (!res.ok) {
                const errData = await res.json().catch(() => ({}));
                throw new Error(errData.detail || "Evaluation failed");
            }

            const data = await res.json();
            setResult(data);
        } catch (err: any) {
            setError(err.message);
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="p-8 max-w-7xl mx-auto space-y-8">
            <div className="flex flex-col space-y-2">
                <h1 className="text-3xl font-bold tracking-tight text-gray-900">
                    Evaluate Answer
                </h1>
                <p className="text-muted-foreground">
                    Upload your handwritten answer for AI-powered evaluation and improvement.
                </p>
            </div>

            <div className="grid gap-8 lg:grid-cols-3">
                {/* Input Section */}
                <div className="lg:col-span-1 space-y-6">
                    <Card>
                        <CardHeader>
                            <CardTitle>Upload & Configure</CardTitle>
                            <CardDescription>Provide your answer details</CardDescription>
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
                                    <div className="p-3 text-sm text-red-500 bg-red-50 rounded-md flex items-center gap-2">
                                        <AlertCircle className="h-4 w-4" />
                                        {error}
                                    </div>
                                )}

                                <Button type="submit" className="w-full" disabled={loading}>
                                    {loading ? (
                                        <>
                                            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                                            Evaluating...
                                        </>
                                    ) : (
                                        "Evaluate Answer"
                                    )}
                                </Button>
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
                            <div className="grid gap-4 md:grid-cols-2">
                                <Card className="border-l-4 border-l-green-500">
                                    <CardHeader className="pb-2">
                                        <CardTitle className="text-base text-green-700">Strengths</CardTitle>
                                    </CardHeader>
                                    <CardContent>
                                        <ul className="list-disc pl-4 space-y-1 text-sm text-gray-700">
                                            {result.feedback.strengths.map((item, i) => (
                                                <li key={i}>{item}</li>
                                            ))}
                                        </ul>
                                    </CardContent>
                                </Card>

                                <Card className="border-l-4 border-l-amber-500">
                                    <CardHeader className="pb-2">
                                        <CardTitle className="text-base text-amber-700">Improvements Needed</CardTitle>
                                    </CardHeader>
                                    <CardContent>
                                        <ul className="list-disc pl-4 space-y-1 text-sm text-gray-700">
                                            {result.feedback.improvements_needed.map((item, i) => (
                                                <li key={i}>{item}</li>
                                            ))}
                                        </ul>
                                    </CardContent>
                                </Card>
                            </div>

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
                                    <div className="bg-gray-50 p-3 rounded-md">
                                        <h4 className="font-semibold text-gray-900 mb-1">Overall Verdict</h4>
                                        <p className="text-gray-600 italic">{result.feedback.overall_assessment}</p>
                                    </div>
                                </CardContent>
                            </Card>

                            {/* Improved Answer */}
                            <Card className="border-2 border-indigo-100 overflow-hidden">
                                <CardHeader className="bg-indigo-50/50 border-b border-indigo-100">
                                    <CardTitle className="flex items-center gap-2 text-indigo-900">
                                        <FileText className="h-5 w-5" />
                                        Improved Answer (Model Solution)
                                    </CardTitle>
                                    <CardDescription>
                                        Enhanced version preserving your voice but adding facts, structure, and examples.
                                    </CardDescription>
                                </CardHeader>
                                <CardContent className="p-6">
                                    <div className="prose prose-indigo max-w-none prose-headings:text-indigo-900 prose-a:text-indigo-600">
                                        <ReactMarkdown
                                            remarkPlugins={[remarkGfm]}
                                            components={markdownComponents}
                                            urlTransform={urlTransform}
                                        >
                                            {result.improved_answer}
                                        </ReactMarkdown>
                                    </div>
                                </CardContent>
                            </Card>
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
