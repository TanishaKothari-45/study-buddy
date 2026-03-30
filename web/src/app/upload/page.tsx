"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Upload, FileText, CheckCircle, AlertCircle, Database, Layers, GraduationCap, BookOpen } from "lucide-react";
import { InlineLoader } from "@/components/ui/loader";
import { cn } from "@/lib/utils";
import { API_URL } from "@/lib/api";
import { authFetch } from "@/lib/authHandler";
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from "@/components/ui/select";
import { Label } from "@/components/ui/label";
import { PageContainer } from "@/components/layout/PageContainer";

interface UploadResult {
    filename: string;
    status: string;
    message?: string;
    chunks_created?: number;
    chunks_stored?: number;
    chapters?: string[];
    reason?: string;
}

export default function UploadPage() {
    const [files, setFiles] = useState<FileList | null>(null);
    const [mode, setMode] = useState<"pinecone" | "content_store">("pinecone");
    const [subject, setSubject] = useState<string>("Geography");
    const [majorDomain, setMajorDomain] = useState<string>("Unclassified");
    const [sourceType, setSourceType] = useState<string>("auto");
    const [loading, setLoading] = useState(false);
    const [results, setResults] = useState<UploadResult[]>([]);
    const [error, setError] = useState("");

    const SUBJECT_DOMAINS: Record<string, string[]> = {
        "Geography": [
            "Physical Geography",
            "Indian Geography",
            "World Geography",
            "Human Geography",
            "Mapping and Cartography"
        ],
        "History": [
            "Indian Heritage and Culture",
            "Ancient Indian History",
            "Medieval Indian History",
            "Modern Indian History"
        ],
        "Economy": [
            "Basic Economic Concepts",
            "Macroeconomics & Policy",
            "Indian Economy & Development",
            "Banking & Finance",
            "Taxation & Public Finance",
            "External Sector & Global Economy",
            "Contemporary Economic Issues"
        ],
        "Science & Tech": [
            "Fundamental Science Concepts",
            "Space & Defence Technology",
            "Information & Communication Tech",
            "Biotechnology & Health Tech",
            "Emerging Technologies",
            "Applied Science & Research"
        ],
        "Environment & Ecology": [
            "Ecology & Ecosystems",
            "Biodiversity & Conservation",
            "Pollution & Environmental Issues",
            "Climate Change & Global Frameworks",
            "Environmental Laws & Policies",
            "Natural Resource Management",
            "Contemporary Environmental Issues"
        ],
        "Polity": [
            "Constitutional Framework",
            "Union Government",
            "State & Local Governance",
            "Judiciary & Legal Institutions",
            "Electoral Processes & Reforms",
            "Governance & Public Policy",
            "Contemporary Governance Issues"
        ],
        "Unclassified": ["Unclassified"]
    };

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
        formData.append("subject", subject);
        formData.append("major_domain", majorDomain);
        // Only append source_type if it's not "auto"
        if (sourceType && sourceType !== "auto") {
            formData.append("source_type", sourceType);
        }

        const endpoint = mode === "pinecone" ? "/upload/" : "/upload-content-store/";

        try {
            const res = await authFetch(`${API_URL}${endpoint}`, {
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
        <PageContainer
            title="Upload materials"
            description="Add documents to your knowledge base to improve AI answers."
        >
            <div className="w-full space-y-8">

                <div className="space-y-8">
                    {/* Configuration Section */}
                    <Card>
                        <CardHeader>
                            <CardTitle>1. Storage settings</CardTitle>
                            <CardDescription>Choose where to store your data</CardDescription>
                        </CardHeader>
                        <CardContent>
                            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                                <div
                                    className={cn(
                                        "flex items-start gap-3 p-4 rounded-xl border cursor-pointer transition-all duration-150",
                                        mode === "pinecone"
                                            ? "border-amber-600 bg-amber-50 dark:bg-amber-900/20 ring-1 ring-amber-600"
                                            : "border-[var(--card-border)] hover:bg-[var(--bg-secondary)]"
                                    )}
                                    onClick={() => setMode("pinecone")}
                                >
                                    <Layers className={cn("h-5 w-5 mt-0.5 flex-shrink-0", mode === "pinecone" ? "text-amber-600" : "text-[var(--text-muted)]")} />
                                    <div>
                                        <p className="font-medium text-sm text-[var(--text)]">Pinecone (embeddings)</p>
                                        <p className="text-xs text-[var(--text-muted)] mt-0.5 leading-relaxed">
                                            Best for semantic search and Q&A. Creates vector embeddings.
                                        </p>
                                    </div>
                                </div>

                                <div
                                    className={cn(
                                        "flex items-start gap-3 p-4 rounded-xl border cursor-pointer transition-all duration-150",
                                        mode === "content_store"
                                            ? "border-amber-600 bg-amber-50 dark:bg-amber-900/20 ring-1 ring-amber-600"
                                            : "border-[var(--card-border)] hover:bg-[var(--bg-secondary)]"
                                    )}
                                    onClick={() => setMode("content_store")}
                                >
                                    <Database className={cn("h-5 w-5 mt-0.5 flex-shrink-0", mode === "content_store" ? "text-amber-600" : "text-[var(--text-muted)]")} />
                                    <div>
                                        <p className="font-medium text-sm text-[var(--text)]">Content store (full text)</p>
                                        <p className="text-xs text-[var(--text-muted)] mt-0.5 leading-relaxed">
                                            Best for specific retrieval and citations. Stores raw text.
                                        </p>
                                    </div>
                                </div>
                            </div>

                            <div className="mt-5 grid grid-cols-1 md:grid-cols-3 gap-4">
                                <div className="space-y-1.5">
                                    <Label htmlFor="subject-select" className="text-xs font-medium text-[var(--text-muted)] uppercase tracking-wide">
                                        Subject
                                    </Label>
                                    <Select
                                        value={subject}
                                        onValueChange={(val) => {
                                            setSubject(val);
                                            setMajorDomain(SUBJECT_DOMAINS[val][0]);
                                        }}
                                    >
                                        <SelectTrigger className="w-full">
                                            <SelectValue placeholder="Select subject" />
                                        </SelectTrigger>
                                        <SelectContent>
                                            {Object.keys(SUBJECT_DOMAINS).map((subj) => (
                                                <SelectItem key={subj} value={subj}>{subj}</SelectItem>
                                            ))}
                                        </SelectContent>
                                    </Select>
                                </div>

                                <div className="space-y-1.5">
                                    <Label htmlFor="domain-select" className="text-xs font-medium text-[var(--text-muted)] uppercase tracking-wide">
                                        Major domain
                                    </Label>
                                    <Select value={majorDomain} onValueChange={setMajorDomain}>
                                        <SelectTrigger className="w-full">
                                            <SelectValue placeholder="Select domain" />
                                        </SelectTrigger>
                                        <SelectContent>
                                            {SUBJECT_DOMAINS[subject]?.map((domain) => (
                                                <SelectItem key={domain} value={domain}>
                                                    {domain}
                                                </SelectItem>
                                            ))}
                                        </SelectContent>
                                    </Select>
                                </div>

                                <div className="space-y-1.5">
                                    <Label htmlFor="source-type-select" className="text-xs font-medium text-[var(--text-muted)] uppercase tracking-wide">
                                        Source type
                                    </Label>
                                    <Select value={sourceType} onValueChange={setSourceType}>
                                        <SelectTrigger className="w-full">
                                            <SelectValue placeholder="Select source type" />
                                        </SelectTrigger>
                                        <SelectContent>
                                            <SelectItem value="auto">Auto-detect (from filename)</SelectItem>
                                            <SelectItem value="pyq">Previous Year Questions</SelectItem>
                                            <SelectItem value="ncert">NCERT</SelectItem>
                                            <SelectItem value="concept">Concept / Topic</SelectItem>
                                            <SelectItem value="current_affairs">Current Affairs</SelectItem>
                                        </SelectContent>
                                    </Select>
                                </div>
                            </div>
                            <p className="text-xs text-[var(--text-faint)] mt-3">
                                Using: <span className="text-amber-600 font-medium">{subject} · {majorDomain} · {sourceType || "Auto-detect"}</span>
                            </p>
                        </CardContent>
                    </Card>

                    {/* Upload Section */}
                    <Card>
                        <CardHeader>
                            <CardTitle>2. Upload files</CardTitle>
                            <CardDescription>PDF, TXT, or image files up to 50MB</CardDescription>
                        </CardHeader>
                        <CardContent>
                            <form onSubmit={handleSubmit} className="space-y-5">
                                <label
                                    htmlFor="dropzone-file"
                                    className={cn(
                                        "flex flex-col items-center justify-center w-full h-52 rounded-xl cursor-pointer transition-all duration-200",
                                        "border-2 border-dashed",
                                        files && files.length > 0
                                            ? "border-amber-600 bg-amber-50 dark:bg-amber-900/10"
                                            : "border-[var(--card-border)] bg-[var(--bg-secondary)] hover:border-amber-600/50 hover:bg-[var(--bg-tertiary)]"
                                    )}
                                >
                                    <div className="flex flex-col items-center justify-center gap-2 text-center px-6 py-8">
                                        {files && files.length > 0 ? (
                                            <>
                                                <CheckCircle className="w-9 h-9 text-amber-600 mb-1" />
                                                <p className="text-sm font-medium text-amber-700 dark:text-amber-400">
                                                    {files.length} file{files.length > 1 ? 's' : ''} selected
                                                </p>
                                                <p className="text-xs text-[var(--text-muted)] max-w-xs truncate">
                                                    {Array.from(files).map(f => f.name).join(", ")}
                                                </p>
                                            </>
                                        ) : (
                                            <>
                                                <Upload className="w-9 h-9 text-[var(--text-faint)] mb-1" />
                                                <p className="text-sm text-[var(--text-muted)]">
                                                    <span className="font-medium text-[var(--text)]">Click to upload</span> or drag and drop
                                                </p>
                                                <p className="text-xs text-[var(--text-faint)]">PDF, TXT, images — max 50MB</p>
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

                                {error && (
                                    <div className="p-3 text-sm text-red-700 dark:text-red-400 bg-red-50 dark:bg-red-900/20 rounded-lg border border-red-200 dark:border-red-800 flex items-center gap-2">
                                        <AlertCircle className="h-4 w-4 flex-shrink-0" />
                                        {error}
                                    </div>
                                )}

                                <div className="flex justify-end">
                                    <Button type="submit" disabled={loading || !files}>
                                        {loading ? (
                                            <>
                                                <InlineLoader className="mr-2" />
                                                Processing...
                                            </>
                                        ) : (
                                            "Upload files"
                                        )}
                                    </Button>
                                </div>
                            </form>
                        </CardContent>
                    </Card>

                    {/* Results List */}
                    {results.length > 0 && (
                        <div className="space-y-3 animate-fade-up">
                            <h2 className="text-base font-semibold text-[var(--text)]">Upload results</h2>
                            <div className="grid gap-3">
                                {results.map((res, i) => (
                                    <Card key={i} className={cn(
                                        "border-l-4",
                                        res.status === "success" ? "border-l-green-500" : "border-l-red-500"
                                    )}>
                                        <CardContent className="p-4 flex items-start justify-between gap-4">
                                            <div className="flex-1 min-w-0">
                                                <div className="flex items-center gap-2 mb-1">
                                                    {res.status === "success" ? (
                                                        <CheckCircle className="h-4 w-4 text-green-600 flex-shrink-0" />
                                                    ) : (
                                                        <AlertCircle className="h-4 w-4 text-red-600 flex-shrink-0" />
                                                    )}
                                                    <span className="font-medium text-sm text-[var(--text)] truncate">{res.filename}</span>
                                                </div>
                                                <p className="text-xs text-[var(--text-muted)] mb-2">
                                                    {res.message || res.reason || "Processed successfully"}
                                                </p>

                                                {res.chapters && res.chapters.length > 0 && (
                                                    <div className="mt-2 space-y-1">
                                                        <p className="text-xs font-medium text-[var(--text)] flex items-center gap-1">
                                                            <FileText className="h-3 w-3" />
                                                            Chapters identified:
                                                        </p>
                                                        <div className="flex flex-wrap gap-1 mt-1">
                                                            {res.chapters.map((chapter, idx) => (
                                                                <span key={idx} className="inline-flex items-center px-2 py-0.5 rounded-md text-[10px] font-medium bg-[var(--bg-tertiary)] text-[var(--text-muted)] border border-[var(--card-border)]">
                                                                    {chapter}
                                                                </span>
                                                            ))}
                                                        </div>
                                                    </div>
                                                )}
                                            </div>
                                            {res.chunks_stored !== undefined && (
                                                <div className="text-right flex-shrink-0">
                                                    <span className="text-xl font-bold text-[var(--text)]">{res.chunks_stored}</span>
                                                    <p className="text-xs text-[var(--text-faint)]">chunks</p>
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
        </PageContainer>
    );
}
