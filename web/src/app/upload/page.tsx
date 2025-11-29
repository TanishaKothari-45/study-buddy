"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Upload, FileText, CheckCircle, AlertCircle, Loader2, Database, Layers } from "lucide-react";
import { cn } from "@/lib/utils";

interface UploadResult {
    filename: string;
    status: string;
    message?: string;
    chunks_created?: number;
    chunks_stored?: number;
    reason?: string;
}

export default function UploadPage() {
    const [files, setFiles] = useState<FileList | null>(null);
    const [mode, setMode] = useState<"pinecone" | "content_store">("pinecone");
    const [loading, setLoading] = useState(false);
    const [results, setResults] = useState<UploadResult[]>([]);
    const [error, setError] = useState("");

    const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
        if (e.target.files && e.target.files.length > 0) {
            setFiles(e.target.files);
        }
    };

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        if (!files || files.length === 0) {
            setError("Please select at least one file to upload.");
            return;
        }

        setLoading(true);
        setError("");
        setResults([]);

        const formData = new FormData();
        for (let i = 0; i < files.length; i++) {
            formData.append("files", files[i]);
        }

        const endpoint = mode === "pinecone" ? "/upload/" : "/upload-content-store/";

        try {
            const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8001";
            const res = await fetch(`${API_URL}${endpoint}`, {
                method: "POST",
                body: formData,
            });

            if (!res.ok) {
                const errData = await res.json().catch(() => ({}));
                throw new Error(errData.detail || "Upload failed");
            }

            const data = await res.json();
            // Normalize response structure as they might differ slightly
            const summary = data.summary || data.processed_files || [];
            setResults(summary);
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
                    Upload Materials
                </h1>
                <p className="text-muted-foreground">
                    Add documents to your knowledge base to improve AI answers.
                </p>
            </div>

            <div className="space-y-8">
                {/* Configuration Section */}
                <Card>
                    <CardHeader>
                        <CardTitle>1. Upload Settings</CardTitle>
                        <CardDescription>Choose where to store your data</CardDescription>
                    </CardHeader>
                    <CardContent>
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                            <div
                                className={cn(
                                    "flex items-start space-x-3 p-4 rounded-lg border cursor-pointer transition-all hover:bg-accent",
                                    mode === "pinecone" ? "border-primary ring-1 ring-primary bg-accent/50" : "border-border"
                                )}
                                onClick={() => setMode("pinecone")}
                            >
                                <Layers className={cn("h-5 w-5 mt-0.5", mode === "pinecone" ? "text-primary" : "text-muted-foreground")} />
                                <div>
                                    <h3 className="font-medium text-sm text-foreground">Pinecone (Embeddings)</h3>
                                    <p className="text-xs text-muted-foreground mt-1">
                                        Best for semantic search and general Q&A. Creates vector embeddings.
                                    </p>
                                </div>
                            </div>

                            <div
                                className={cn(
                                    "flex items-start space-x-3 p-4 rounded-lg border cursor-pointer transition-all hover:bg-accent",
                                    mode === "content_store" ? "border-primary ring-1 ring-primary bg-accent/50" : "border-border"
                                )}
                                onClick={() => setMode("content_store")}
                            >
                                <Database className={cn("h-5 w-5 mt-0.5", mode === "content_store" ? "text-primary" : "text-muted-foreground")} />
                                <div>
                                    <h3 className="font-medium text-sm text-foreground">Content Store (Full Text)</h3>
                                    <p className="text-xs text-muted-foreground mt-1">
                                        Best for specific retrieval and citations. Stores raw text chunks.
                                    </p>
                                </div>
                            </div>
                        </div>
                    </CardContent>
                </Card>

                {/* Upload Section */}
                <Card>
                    <CardHeader>
                        <CardTitle>2. File Upload</CardTitle>
                        <CardDescription>Select PDF, TXT, or Image files</CardDescription>
                    </CardHeader>
                    <CardContent>
                        <form onSubmit={handleSubmit} className="space-y-6">
                            <div className="flex items-center justify-center w-full">
                                <label
                                    htmlFor="dropzone-file"
                                    className={cn(
                                        "flex flex-col items-center justify-center w-full h-64 border-2 border-dashed rounded-lg cursor-pointer bg-card hover:bg-accent/50 transition-colors",
                                        files && files.length > 0 ? "border-primary bg-accent/10" : "border-border"
                                    )}
                                >
                                    <div className="flex flex-col items-center justify-center pt-5 pb-6">
                                        {files && files.length > 0 ? (
                                            <>
                                                <CheckCircle className="w-10 h-10 mb-3 text-primary" />
                                                <p className="mb-2 text-sm text-primary font-medium">
                                                    {files.length} file(s) selected
                                                </p>
                                                <div className="text-xs text-muted-foreground max-w-md text-center">
                                                    {Array.from(files).map(f => f.name).join(", ")}
                                                </div>
                                            </>
                                        ) : (
                                            <>
                                                <Upload className="w-10 h-10 mb-3 text-muted-foreground" />
                                                <p className="mb-2 text-sm text-muted-foreground">
                                                    <span className="font-semibold">Click to upload</span> or drag and drop
                                                </p>
                                                <p className="text-xs text-muted-foreground">PDF, TXT, Images (MAX. 50MB)</p>
                                            </>
                                        )}
                                    </div>
                                    <input
                                        id="dropzone-file"
                                        type="file"
                                        className="hidden"
                                        onChange={handleFileChange}
                                        multiple
                                        accept=".pdf,.txt,image/*"
                                    />
                                </label>
                            </div>

                            {error && (
                                <div className="p-3 text-sm text-destructive bg-destructive/10 rounded-md flex items-center gap-2">
                                    <AlertCircle className="h-4 w-4" />
                                    {error}
                                </div>
                            )}

                            <div className="flex justify-end">
                                <Button type="submit" size="lg" disabled={loading || !files}>
                                    {loading ? (
                                        <>
                                            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                                            Processing...
                                        </>
                                    ) : (
                                        "Start Upload"
                                    )}
                                </Button>
                            </div>
                        </form>
                    </CardContent>
                </Card>

                {/* Results List */}
                {results.length > 0 && (
                    <div className="space-y-4 animate-in fade-in slide-in-from-bottom-4 duration-500">
                        <h3 className="text-lg font-semibold text-foreground">Processing Results</h3>
                        <div className="grid gap-3">
                            {results.map((res, i) => (
                                <Card key={i} className={cn("border-l-4", res.status === "success" ? "border-l-green-500" : "border-l-destructive")}>
                                    <CardContent className="p-4 flex items-start justify-between">
                                        <div>
                                            <div className="flex items-center gap-2 mb-1">
                                                {res.status === "success" ? (
                                                    <CheckCircle className="h-5 w-5 text-green-500" />
                                                ) : (
                                                    <AlertCircle className="h-5 w-5 text-destructive" />
                                                )}
                                                <span className="font-medium text-foreground">{res.filename}</span>
                                            </div>
                                            <p className="text-sm text-muted-foreground">
                                                {res.message || res.reason || "Processed successfully"}
                                            </p>
                                        </div>
                                        {res.chunks_stored !== undefined && (
                                            <div className="text-right">
                                                <span className="text-2xl font-bold text-foreground">{res.chunks_stored}</span>
                                                <p className="text-xs text-muted-foreground">Chunks</p>
                                            </div>
                                        )}
                                    </CardContent>
                                </Card>
                            ))}
                        </div>
                    </div>
                )}
            </div>
        </div>
    );
}
