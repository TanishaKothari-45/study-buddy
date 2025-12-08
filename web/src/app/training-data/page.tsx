"use client";

import { useState, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardDescription, CardHeader, CardTitle, CardFooter } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Upload, FileText, CheckCircle, AlertCircle, Loader2, Plus, Save, Database } from "lucide-react";
import { cn } from "@/lib/utils";
import { API_URL } from "@/lib/api";
import { authFetch, showToast } from "@/lib/authHandler";

interface TrainingExample {
    id: string;
    question: string;
    student_answer: string;
    ideal_feedback: string;
    metadata: {
        word_count: number;
        created_at: string;
    };
}

export default function TrainingDataPage() {
    const [examples, setExamples] = useState<TrainingExample[]>([]);
    const [loading, setLoading] = useState(false);
    const [extracting, setExtracting] = useState(false);
    const [submitting, setSubmitting] = useState(false);
    const [error, setError] = useState("");

    // New Example State
    const [files, setFiles] = useState<FileList | null>(null);
    const [question, setQuestion] = useState("");
    const [answerText, setAnswerText] = useState("");
    const [idealFeedback, setIdealFeedback] = useState("");
    const [extractionSuccess, setExtractionSuccess] = useState(false);

    useEffect(() => {
        fetchExamples();
    }, []);

    const fetchExamples = async () => {
        setLoading(true);
        try {
            const res = await authFetch(`${API_URL}/training-data/examples`);
            if (!res.ok) throw new Error("Failed to fetch examples");
            const data = await res.json();
            setExamples(data.training_examples || []);
        } catch (err: any) {
            showToast("Failed to load training examples", "error");
            setError("Failed to load training examples.");
        } finally {
            setLoading(false);
        }
    };

    const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
        if (e.target.files && e.target.files.length > 0) {
            setFiles(e.target.files);
            setExtractionSuccess(false);
        }
    };

    const handleExtract = async (e: React.FormEvent) => {
        e.preventDefault();
        if (!files || files.length === 0) {
            setError("Please select a file to upload.");
            return;
        }

        setExtracting(true);
        setError("");

        const formData = new FormData();
        for (let i = 0; i < files.length; i++) {
            formData.append("files", files[i]);
        }
        if (question) formData.append("question", question);

        try {
            const res = await authFetch(`${API_URL}/training-data/extract-answer`, {
                method: "POST",
                body: formData,
            });

            if (!res.ok) {
                const errData = await res.json().catch(() => ({}));
                throw new Error(errData.detail || "Extraction failed");
            }

            const data = await res.json();
            setQuestion(data.question || question);
            setAnswerText(data.answer_text);
            setExtractionSuccess(true);
        } catch (err: any) {
            setError(err.message);
        } finally {
            setExtracting(false);
        }
    };

    const handleSubmit = async () => {
        if (!question || !answerText || !idealFeedback) {
            setError("Please fill in all fields (Question, Answer Text, Ideal Feedback).");
            return;
        }

        setSubmitting(true);
        setError("");

        const formData = new FormData();
        formData.append("question", question);
        formData.append("answer_text", answerText);
        formData.append("ideal_feedback", idealFeedback);

        try {
            const res = await authFetch(`${API_URL}/training-data/submit`, {
                method: "POST",
                body: formData,
            });

            if (!res.ok) {
                const errData = await res.json().catch(() => ({}));
                throw new Error(errData.detail || "Submission failed");
            }

            // Reset form and refresh list
            setFiles(null);
            setQuestion("");
            setAnswerText("");
            setIdealFeedback("");
            setExtractionSuccess(false);
            fetchExamples();

            // Show success notification
            showToast("Training example saved successfully!", "success");
        } catch (err: any) {
            setError(err.message);
        } finally {
            setSubmitting(false);
        }
    };

    return (
        <div className="p-8 max-w-7xl mx-auto space-y-8">
            <div className="flex flex-col space-y-2">
                <h1 className="text-3xl font-bold tracking-tight text-foreground">
                    Training Data
                </h1>
                <p className="text-muted-foreground">
                    Manage few-shot examples to train the AI on your preferred feedback style.
                </p>
            </div>

            <Tabs defaultValue="new" className="space-y-6">
                <TabsList>
                    <TabsTrigger value="list" className="flex items-center gap-2">
                        <Database className="h-4 w-4" />
                        Existing Examples
                    </TabsTrigger>
                    <TabsTrigger value="new" className="flex items-center gap-2">
                        <Plus className="h-4 w-4" />
                        Add New Example
                    </TabsTrigger>
                </TabsList>

                {/* List Tab */}
                <TabsContent value="list" className="space-y-4">
                    {loading ? (
                        <div className="flex justify-center p-12">
                            <Loader2 className="h-8 w-8 animate-spin text-gray-400" />
                        </div>
                    ) : examples.length === 0 ? (
                        <div className="text-center p-12 border-2 border-dashed rounded-lg bg-gray-50">
                            <Database className="h-10 w-10 text-gray-400 mx-auto mb-3" />
                            <h3 className="text-lg font-medium text-gray-900">No Examples Yet</h3>
                            <p className="text-gray-500 mt-1">Add your first training example to improve AI feedback.</p>
                        </div>
                    ) : (
                        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
                            {examples.map((example) => (
                                <Card key={example.id} className="flex flex-col h-full hover:shadow-md transition-shadow">
                                    <CardHeader className="pb-3">
                                        <CardTitle className="text-base font-medium line-clamp-2" title={example.question}>
                                            {example.question}
                                        </CardTitle>
                                        <CardDescription className="text-xs">
                                            {new Date(example.metadata.created_at).toLocaleDateString()} • {example.metadata.word_count} words
                                        </CardDescription>
                                    </CardHeader>
                                    <CardContent className="flex-1 text-sm text-gray-600 space-y-2">
                                        <div>
                                            <span className="font-semibold text-gray-900">Answer Snippet:</span>
                                            <p className="line-clamp-3 mt-1 bg-gray-50 p-2 rounded border">
                                                {example.student_answer}
                                            </p>
                                        </div>
                                        <div>
                                            <span className="font-semibold text-gray-900">Feedback Snippet:</span>
                                            <p className="line-clamp-3 mt-1 bg-blue-50 p-2 rounded border border-blue-100 text-blue-900">
                                                {example.ideal_feedback}
                                            </p>
                                        </div>
                                    </CardContent>
                                </Card>
                            ))}
                        </div>
                    )}
                </TabsContent>

                {/* Add New Tab */}
                <TabsContent value="new">
                    <div className="grid gap-8 lg:grid-cols-2">
                        {/* Left: Upload & Extraction */}
                        <div className="space-y-6">
                            <Card>
                                <CardHeader>
                                    <CardTitle>1. Upload Answer</CardTitle>
                                    <CardDescription>Upload a handwritten answer to extract text.</CardDescription>
                                </CardHeader>
                                <CardContent>
                                    <form onSubmit={handleExtract} className="space-y-4">
                                        <div className="flex items-center justify-center w-full">
                                            <label
                                                htmlFor="training-file"
                                                className={cn(
                                                    "flex flex-col items-center justify-center w-full h-32 border-2 border-dashed rounded-lg cursor-pointer bg-gray-50 hover:bg-gray-100 transition-colors",
                                                    files && files.length > 0 ? "border-green-500 bg-green-50" : "border-gray-300"
                                                )}
                                            >
                                                <div className="flex flex-col items-center justify-center pt-5 pb-6">
                                                    {files && files.length > 0 ? (
                                                        <>
                                                            <CheckCircle className="w-8 h-8 mb-2 text-green-500" />
                                                            <p className="mb-2 text-sm text-green-700 font-medium">
                                                                {files.length} file(s) selected
                                                            </p>
                                                        </>
                                                    ) : (
                                                        <>
                                                            <Upload className="w-8 h-8 mb-2 text-gray-400" />
                                                            <p className="mb-2 text-sm text-gray-500">
                                                                <span className="font-semibold">Click to upload</span>
                                                            </p>
                                                            <p className="text-xs text-gray-500">PDF or Images</p>
                                                        </>
                                                    )}
                                                </div>
                                                <input
                                                    id="training-file"
                                                    type="file"
                                                    className="hidden"
                                                    onChange={handleFileChange}
                                                    multiple
                                                    accept=".pdf,image/*"
                                                />
                                            </label>
                                        </div>

                                        <div className="space-y-2">
                                            <label className="text-sm font-medium">Question (Optional)</label>
                                            <Input
                                                placeholder="Enter the question text..."
                                                value={question}
                                                onChange={(e) => setQuestion(e.target.value)}
                                            />
                                        </div>

                                        <Button type="submit" className="w-full" disabled={extracting || !files}>
                                            {extracting ? (
                                                <>
                                                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                                                    Extracting Text...
                                                </>
                                            ) : (
                                                <>
                                                    <FileText className="mr-2 h-4 w-4" />
                                                    Extract Text
                                                </>
                                            )}
                                        </Button>
                                    </form>
                                </CardContent>
                            </Card>

                            {error && (
                                <div className="p-3 text-sm text-red-500 bg-red-50 rounded-md flex items-center gap-2">
                                    <AlertCircle className="h-4 w-4" />
                                    {error}
                                </div>
                            )}
                        </div>

                        {/* Right: Edit & Submit */}
                        <div className="space-y-6">
                            <Card className={cn("transition-opacity", !extractionSuccess && !answerText ? "opacity-50 pointer-events-none" : "opacity-100")}>
                                <CardHeader>
                                    <CardTitle>2. Review & Submit</CardTitle>
                                    <CardDescription>Verify extracted text and add ideal feedback.</CardDescription>
                                </CardHeader>
                                <CardContent className="space-y-4">
                                    <div className="space-y-2">
                                        <label className="text-sm font-medium">Question</label>
                                        <Input
                                            value={question}
                                            onChange={(e) => setQuestion(e.target.value)}
                                            placeholder="Question text"
                                        />
                                    </div>

                                    <div className="space-y-2">
                                        <label className="text-sm font-medium">Extracted Answer Text</label>
                                        <textarea
                                            className="flex min-h-[150px] w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
                                            value={answerText}
                                            onChange={(e) => setAnswerText(e.target.value)}
                                            placeholder="Extracted text will appear here..."
                                        />
                                    </div>

                                    <div className="space-y-2">
                                        <label className="text-sm font-medium text-blue-700">Ideal Feedback (Required)</label>
                                        <textarea
                                            className="flex min-h-[150px] w-full rounded-md border-blue-200 border bg-blue-50/30 px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-2"
                                            value={idealFeedback}
                                            onChange={(e) => setIdealFeedback(e.target.value)}
                                            placeholder="Write the ideal feedback for this answer..."
                                        />
                                        <p className="text-xs text-muted-foreground">
                                            This feedback will be used to train the AI on your preferred style.
                                        </p>
                                    </div>
                                </CardContent>
                                <CardFooter>
                                    <Button onClick={handleSubmit} className="w-full bg-green-600 hover:bg-green-700" disabled={submitting}>
                                        {submitting ? (
                                            <>
                                                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                                                Saving...
                                            </>
                                        ) : (
                                            <>
                                                <Save className="mr-2 h-4 w-4" />
                                                Save Training Example
                                            </>
                                        )}
                                    </Button>
                                </CardFooter>
                            </Card>
                        </div>
                    </div>
                </TabsContent>
            </Tabs>
        </div>
    );
}
