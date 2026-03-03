"use client";

import { useState, useEffect, useRef } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Loader2, Play, CheckCircle, XCircle, RefreshCw, Clock, BookOpen, ClipboardList, AlertCircle } from "lucide-react";
import { cn } from "@/lib/utils";
import ReactMarkdown from "react-markdown";
import { markdownComponents, urlTransform } from "@/components/ui/mermaid";
import { Progress } from "@/components/ui/progress";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { useMockTestStore } from "@/stores";
import { authFetch, showToast } from "@/lib/authHandler";
import { useAuth } from "@/context/AuthContext";
import ApiKeyBanner from "@/components/layout/ApiKeyBanner";

// UPSC Geography Taxonomy (Mirrors backend/app/utils/metadata_enricher.py)
const GEOGRAPHY_DOMAINS: Record<string, string[]> = {
    "Physical Geography": [
        "Geomorphology",
        "Climatology",
        "Oceanography",
        "Biogeography",
        "Natural Disasters"
    ],
    "Human Geography": [
        "Economic Geography",
        "Cultural Geography",
        "Models and Theories",
        "Population Geography",
        "Settlements",
        "Migration"
    ],
    "Indian Geography": [
        "Indian Physiography",
        "Indian Drainage System",
        "Indian Climate",
        "Indian Soils",
        "Indian Agriculture",
        "Indian Natural Resources",
        "Indian Industries",
        "Transport and Communication",
        "Regional Planning"
    ],
    "World Geography": [
        "Continents and Countries",
        "Major Physical Features",
        "Environmental Challenges",
        "Political and Physical Features",
        "Mapping and Cartography"
    ]
};

type JobStatus = 'idle' | 'pending' | 'processing' | 'completed' | 'failed';

import { API_URL } from "@/lib/api";

export default function MockTestPage() {
    const { user, isApiKeyValid, setIsApiKeyValid, verifyApiKey } = useAuth();
    const [showBanner, setShowBanner] = useState(false);
    // Persisted state from store
    const store = useMockTestStore();
    const {
        testData, userAnswers, submitted, score,
        jobId, jobStatus,
        setTestData, updateUserAnswer, setJobId, setJobStatus,
        submitTest: storeSubmitTest, resetTest
    } = store;

    // Local UI state
    const [loading, setLoading] = useState(false);
    const [progress, setProgress] = useState(0);
    const [statusMessage, setStatusMessage] = useState("");
    const [error, setError] = useState<string | null>(null);
    const [estimatedTimeRemaining, setEstimatedTimeRemaining] = useState<number | null>(null);

    // Configuration State (local - doesn't need persistence)
    const [numQuestions, setNumQuestions] = useState("5");
    const [selectedDomain, setSelectedDomain] = useState<string>("");
    const [selectedSubDomain, setSelectedSubDomain] = useState<string>("");
    const [customTopic, setCustomTopic] = useState("");

    const pollingInterval = useRef<NodeJS.Timeout | null>(null);

    // Resume polling if there's an in-progress job when component mounts
    useEffect(() => {
        if (jobId && (jobStatus === 'pending' || jobStatus === 'processing')) {
            setLoading(true);
            setStatusMessage("Resuming generation...");
            startPolling(jobId);
        }

        return () => {
            if (pollingInterval.current) {
                clearInterval(pollingInterval.current);
            }
        };
    }, []); // Only on mount

    // Cleanup polling on unmount
    useEffect(() => {
        return () => {
            if (pollingInterval.current) {
                clearInterval(pollingInterval.current);
            }
        };
    }, []);

    // Proactively show banner if key is missing or invalid
    useEffect(() => {
        if (user && (user.has_gemini_api_key === false || isApiKeyValid === 'invalid')) {
            setShowBanner(true);
        }
    }, [user, isApiKeyValid]);

    const handleCancel = async () => {
        if (!jobId) return;
        const idToCancel = jobId;

        setJobId(null);
        setJobStatus('idle');
        setLoading(false);
        setError("Test generation cancelled.");
        setEstimatedTimeRemaining(null);

        try {
            await authFetch(`${API_URL}/jobs/${idToCancel}/cancel`, { method: "POST" });
            showToast("Test generation cancelled.", "info");
        } catch (err) {
            console.error("Cancel failed:", err);
            showToast("Failed to signal cancellation to backend.", "error");
        }
    };

    const generateTest = async () => {
        // Strict guard: check if user has Gemini API key
        if (!user || user.has_gemini_api_key === false || isApiKeyValid === 'invalid') {
            const msg = isApiKeyValid === 'invalid'
                ? "Your Gemini API key is invalid. Please update it in Settings."
                : "Please set your Gemini API key in Settings before generating a test.";
            setError(msg);
            setShowBanner(true);
            setLoading(false);
            return;
        }

        // On-demand validation if status is unknown
        if (isApiKeyValid === 'unknown') {
            setStatusMessage("Verifying API Key...");
            setError(null);
            const isValid = await verifyApiKey();
            if (!isValid) {
                setError("Your Gemini API key is invalid. Please update it in Settings.");
                setShowBanner(true);
                setLoading(false);
                return;
            }
        }

        setLoading(true);
        resetTest(); // Clear store state
        setProgress(0);
        setStatusMessage("Initializing...");
        setError(null);

        // Determine topics list
        let topics: string[] = [];
        if (customTopic.trim()) {
            topics = [customTopic.trim()];
        } else if (selectedSubDomain && selectedSubDomain !== "all") {
            topics = [selectedSubDomain];
        } else if (selectedDomain) {
            topics = [selectedDomain];
        } else {
            topics = ["Geography"]; // Fallback
        }

        try {
            // Start async job
            const res = await authFetch(`${API_URL}/mock-test/generate-async`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    num_questions: parseInt(numQuestions),
                    topics: topics
                }),
            });

            if (!res.ok) {
                const errData = await res.json();
                throw new Error(errData.detail || "Failed to start generation job");
            }

            const data = await res.json();
            setJobId(data.job_id); // Save to store for persistence
            setJobStatus('processing');

            // Set initial estimated time
            if (data.estimated_time_seconds) {
                setEstimatedTimeRemaining(data.estimated_time_seconds);
                setStatusMessage(`Starting generation... (~${data.estimated_time_seconds}s remaining)`);
            } else {
                setStatusMessage("Starting generation...");
            }

            // Start polling
            startPolling(data.job_id);

        } catch (err) {
            const message = err instanceof Error ? err.message : "Failed to start mock test generation";
            showToast(message, "error");
            setError(message);
            setLoading(false);
        }
    };

    const startPolling = (currentJobId: string) => {
        if (pollingInterval.current) clearInterval(pollingInterval.current);

        pollingInterval.current = setInterval(async () => {
            try {
                const res = await authFetch(`${API_URL}/mock-test/status/${currentJobId}`);
                if (!res.ok) throw new Error("Failed to poll status");

                const jobData = await res.json();

                // Update progress
                const progressPct = Math.round((jobData.progress || 0) * 100);
                setProgress(progressPct);

                // Update estimated time countdown
                setEstimatedTimeRemaining(prev => {
                    if (prev === null || prev <= 0) return 0;
                    return Math.max(0, prev - 2); // Decrease by 2s every poll
                });

                if (jobData.status === 'completed') {
                    if (pollingInterval.current) clearInterval(pollingInterval.current);

                    // Process completed data
                    const result = jobData.result || {};
                    const questions = result.questions || [];

                    console.log("Mock Test Result:", result);

                    if (questions.length === 0) {
                        setJobStatus('failed');
                        setError("Generation completed but no questions were returned. Please try again.");
                        setLoading(false);
                        setEstimatedTimeRemaining(null);
                        return; // Stop processing
                    }

                    // Calculate metadata
                    const minutesPerQuestion = 1.2;
                    const totalMinutes = questions.length * minutesPerQuestion;
                    const hours = Math.floor(totalMinutes / 60);
                    const minutes = Math.floor(totalMinutes % 60);
                    const timeAllowed = hours > 0
                        ? `${hours} hour${hours > 1 ? 's' : ''} ${minutes} minute${minutes !== 1 ? 's' : ''}`
                        : `${minutes} minute${minutes !== 1 ? 's' : ''}`;

                    const totalMarks = questions.length * 2;

                    setTestData({
                        questions,
                        total_marks: totalMarks,
                        time_allowed: timeAllowed,
                        instructions: [
                            "Attempt all questions.",
                            `Each question carries 2 marks.`,
                            `Total marks: ${totalMarks}.`,
                            "Negative marking: -0.67 marks (1/3 of 2 marks) for each wrong answer.",
                            "No marks deducted for unanswered questions.",
                            "Choose the most appropriate option.",
                            "Questions are based on your uploaded study materials."
                        ]
                    });

                    setJobStatus('completed');
                    setLoading(false);
                    setStatusMessage("Generation complete!");
                    setEstimatedTimeRemaining(null);

                } else if (jobData.status === 'failed') {
                    if (pollingInterval.current) clearInterval(pollingInterval.current);
                    const cleanedError = jobData.error || "Generation failed";
                    setError(cleanedError);
                    setJobStatus('failed');
                    setLoading(false);
                    setEstimatedTimeRemaining(null);

                    // Show banner if it's an API key error
                    if (cleanedError.toLowerCase().includes("api key") || cleanedError.includes("API_KEY_INVALID")) {
                        setIsApiKeyValid('invalid');
                        setShowBanner(true);
                    }
                } else {
                    // Still processing
                    setJobStatus('processing');

                    // Update status message with countdown
                    setEstimatedTimeRemaining(prev => {
                        const timeLeft = prev !== null ? prev : 0;
                        const timeMsg = timeLeft > 0 ? `(~${timeLeft}s remaining)` : "(finishing up...)";
                        setStatusMessage(`Generating questions... ${timeMsg}`);
                        return prev; // Return same value, update happens in the other setter
                    });
                }

            } catch {
                // Don't show toast for transient network errors during polling
                // They will auto-retry and showing multiple toasts would be annoying
            }
        }, 2000); // Poll every 2 seconds
    };

    const handleAnswerSelect = (questionIndex: number, option: string) => {
        updateUserAnswer(questionIndex, option); // Use store method
    };

    const submitTest = () => {
        storeSubmitTest(); // Use store method
        window.scrollTo({ top: 0, behavior: 'smooth' });
    };

    const getOptionLabel = (index: number) => String.fromCharCode(65 + index); // 0->A, 1->B...

    return (
        <div className="p-8 max-w-5xl mx-auto space-y-8">
            <ApiKeyBanner showBanner={showBanner} onKeySet={() => setShowBanner(false)} />
            <div className="flex items-center justify-between">
                <div className="flex flex-col space-y-2">
                    <h1 className="text-3xl font-bold tracking-tight text-foreground">
                        Prelims Geography Mock Test
                    </h1>
                    <p className="text-muted-foreground">
                        Generate AI-powered mock tests based on your study materials and UPSC patterns.
                    </p>
                </div>
                {testData && (
                    <Button variant="outline" size="sm" onClick={resetTest} className="text-muted-foreground hover:text-primary">
                        <RefreshCw className="h-4 w-4 mr-2" />
                        New Test
                    </Button>
                )}
            </div>

            {!testData ? (
                <Card>
                    <CardHeader>
                        <CardTitle>Configure Test</CardTitle>
                        <CardDescription>Customize your mock test parameters.</CardDescription>
                    </CardHeader>
                    <CardContent className="space-y-6">
                        <div className="grid gap-6 md:grid-cols-2">
                            {/* Basic Settings */}
                            <div className="space-y-2">
                                <Label>Number of Questions</Label>
                                <Select value={numQuestions} onValueChange={setNumQuestions}>
                                    <SelectTrigger>
                                        <SelectValue placeholder="Select count" />
                                    </SelectTrigger>
                                    <SelectContent className="bg-card z-50">
                                        <SelectItem value="5">5 Questions (Quick)</SelectItem>
                                        <SelectItem value="10">10 Questions</SelectItem>
                                        <SelectItem value="20">20 Questions</SelectItem>
                                        <SelectItem value="50">50 Questions (Full Subject)</SelectItem>
                                        <SelectItem value="100">100 Questions (Full Mock)</SelectItem>
                                    </SelectContent>
                                </Select>
                            </div>

                        </div>

                        {/* Topic Selection */}
                        <div className="space-y-4 border-t pt-4">
                            <Label className="text-base">Topic Selection</Label>

                            <div className="grid gap-6 md:grid-cols-2">
                                <div className="space-y-2">
                                    <Label className="text-xs text-muted-foreground">Major Domain</Label>
                                    <Select
                                        value={selectedDomain}
                                        onValueChange={(val) => {
                                            setSelectedDomain(val);
                                            setSelectedSubDomain(""); // Reset subdomain when domain changes
                                        }}
                                    >
                                        <SelectTrigger>
                                            <SelectValue placeholder="Select Major Domain" />
                                        </SelectTrigger>
                                        <SelectContent className="bg-card z-50">
                                            {Object.keys(GEOGRAPHY_DOMAINS).map((domain) => (
                                                <SelectItem key={domain} value={domain}>{domain}</SelectItem>
                                            ))}
                                        </SelectContent>
                                    </Select>
                                </div>

                                <div className="space-y-2">
                                    <Label className="text-xs text-muted-foreground">Sub-Domain (Optional)</Label>
                                    <Select
                                        value={selectedSubDomain}
                                        onValueChange={setSelectedSubDomain}
                                        disabled={!selectedDomain}
                                    >
                                        <SelectTrigger>
                                            <SelectValue placeholder="Select Specific Topic" />
                                        </SelectTrigger>
                                        <SelectContent className="bg-card z-50">
                                            <SelectItem value="all">All Sub-topics</SelectItem>
                                            {selectedDomain && GEOGRAPHY_DOMAINS[selectedDomain]?.map((sub) => (
                                                <SelectItem key={sub} value={sub}>{sub}</SelectItem>
                                            ))}
                                        </SelectContent>
                                    </Select>
                                </div>
                            </div>

                            <div className="relative">
                                <div className="absolute inset-0 flex items-center">
                                    <span className="w-full border-t" />
                                </div>
                                <div className="relative flex justify-center text-xs uppercase">
                                    <span className="bg-card px-2 text-muted-foreground">Or</span>
                                </div>
                            </div>

                            <div className="space-y-2">
                                <Label>Custom Topic</Label>
                                <Input
                                    placeholder="e.g., El Nino, Coral Reefs, Industrial Location Theory"
                                    value={customTopic}
                                    onChange={(e) => setCustomTopic(e.target.value)}
                                />
                                <p className="text-xs text-muted-foreground">
                                    Type a specific topic to override the dropdown selection.
                                </p>
                            </div>
                        </div>

                        {/* Progress Indicator */}
                        {loading && (
                            <div className="space-y-4 pt-4 border-t animate-in fade-in slide-in-from-bottom-4 duration-500">
                                <div className="flex justify-between items-center text-sm">
                                    <span className="font-medium">{statusMessage}</span>
                                    <span className="text-muted-foreground">{progress}%</span>
                                </div>
                                <Progress value={progress} className="h-2" />
                                <div className="flex justify-center pt-2">
                                    <Button variant="destructive" size="sm" onClick={handleCancel}>
                                        Cancel Generation
                                    </Button>
                                </div>
                            </div>
                        )}

                        {/* Error Message */}
                        {error && (
                            <Alert variant="destructive" className="mt-4">
                                <AlertCircle className="h-4 w-4" />
                                <AlertTitle>Error</AlertTitle>
                                <AlertDescription>{error}</AlertDescription>
                            </Alert>
                        )}

                    </CardContent>
                    <CardFooter>
                        <Button onClick={generateTest} disabled={loading} className="w-full md:w-auto">
                            {loading ? (
                                <>
                                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                                    Generating...
                                </>
                            ) : (
                                <>
                                    <Play className="mr-2 h-4 w-4" />
                                    Start Mock Test
                                </>
                            )}
                        </Button>
                    </CardFooter>
                </Card>
            ) : (
                <div className="space-y-6">
                    {/* Test Header / Results */}
                    <Card className={cn("border-l-4", submitted ? (score >= 0 ? "border-l-green-500" : "border-l-destructive") : "border-l-primary")}>
                        <CardHeader className="pb-2">
                            <div className="flex justify-between items-start">
                                <div>
                                    <CardTitle>{submitted ? "Test Results" : "Mock Test In Progress"}</CardTitle>
                                    <CardDescription className="flex items-center gap-4 mt-1">
                                        <span className="flex items-center gap-1"><Clock className="h-3 w-3" /> {testData.time_allowed}</span>
                                        <span>•</span>
                                        <span>Total Marks: {testData.total_marks}</span>
                                    </CardDescription>
                                </div>
                                {submitted && (
                                    <div className="text-right">
                                        <div className="text-3xl font-bold">{score}</div>
                                        <div className="text-xs text-muted-foreground">Your Score</div>
                                    </div>
                                )}
                            </div>
                        </CardHeader>
                        {!submitted && (
                            <CardContent>
                                <div className="bg-accent/50 text-accent-foreground text-sm p-3 rounded-md">
                                    <strong>Instructions:</strong>
                                    <ul className="list-disc list-inside mt-1 space-y-0.5">
                                        {testData.instructions.map((inst, i) => (
                                            <li key={i}>{inst}</li>
                                        ))}
                                    </ul>
                                </div>
                            </CardContent>
                        )}
                    </Card>

                    {/* Questions List */}
                    <div className="space-y-6">
                        {testData.questions.map((q, qIdx) => (
                            <Card key={qIdx} className={cn("transition-all", submitted ? (userAnswers[qIdx] === q.correct_answer ? "ring-1 ring-green-500" : userAnswers[qIdx] ? "ring-1 ring-destructive" : "") : "")}>
                                <CardHeader className="pb-2">
                                    <div className="flex gap-3">
                                        <span className="flex-shrink-0 flex items-center justify-center w-8 h-8 rounded-full bg-muted text-muted-foreground font-bold text-sm">
                                            {qIdx + 1}
                                        </span>
                                        <div className="space-y-1">
                                            <CardTitle className="text-base font-medium leading-relaxed whitespace-pre-line">
                                                {q.question}
                                            </CardTitle>
                                            {submitted && (
                                                <div className="flex items-center gap-2 text-xs text-muted-foreground">
                                                    <BookOpen className="h-3 w-3" />
                                                    Source: {q.source.filename} {q.source.chapter && `(${q.source.chapter})`}
                                                </div>
                                            )}
                                        </div>
                                    </div>
                                </CardHeader>
                                <CardContent className="pl-14 space-y-3">
                                    <RadioGroup
                                        value={userAnswers[qIdx] || ""}
                                        onValueChange={(val) => handleAnswerSelect(qIdx, val)}
                                        disabled={submitted}
                                    >
                                        {q.options.map((option, optIdx) => {
                                            const optionLabel = getOptionLabel(optIdx);
                                            let optionClass = "flex items-center space-x-2 p-3 rounded-lg border border-transparent hover:bg-accent/50 transition-colors cursor-pointer";

                                            if (submitted) {
                                                if (optionLabel === q.correct_answer) {
                                                    // Correct answer: Light green background, dark green text
                                                    optionClass = "flex items-center space-x-2 p-3 rounded-lg border border-green-100 bg-green-20 text-green-800 dark:bg-green-600/20 dark:border-green-800 dark:text-green-600";
                                                } else if (userAnswers[qIdx] === optionLabel) {
                                                    // Wrong answer: Light red background, dark red text
                                                    optionClass = "flex items-center space-x-2 p-3 rounded-lg border border-red-100 bg-red-20 text-red-800 dark:bg-red-600/20 dark:border-red-800 dark:text-red-500";
                                                }
                                            } else if (userAnswers[qIdx] === optionLabel) {
                                                optionClass = "flex items-center space-x-2 p-3 rounded-lg border border-primary/20 bg-primary/5";
                                            }

                                            return (
                                                <div key={optIdx} className={optionClass} onClick={() => !submitted && handleAnswerSelect(qIdx, optionLabel)}>
                                                    <RadioGroupItem value={optionLabel} id={`q${qIdx}-opt${optIdx}`} />
                                                    <div className={cn(
                                                        "w-6 h-6 rounded-full border-2 flex items-center justify-center text-xs font-medium transition-all",
                                                        submitted && optionLabel === q.correct_answer ? "bg-green-600 border-green-600 text-white" :
                                                            submitted && userAnswers[qIdx] === optionLabel ? "bg-red-400 border-red-400 text-white" :
                                                                userAnswers[qIdx] === optionLabel ? "bg-accent border-accent text-white" : "border-border text-muted-foreground"
                                                    )}>
                                                        {userAnswers[qIdx] === optionLabel && !submitted && <div className="w-3 h-3 rounded-full bg-white" />}
                                                        {submitted || userAnswers[qIdx] !== optionLabel ? optionLabel : ""}
                                                    </div>
                                                    <Label htmlFor={`q${qIdx}-opt${optIdx}`} className="flex-1 cursor-pointer font-normal">
                                                        {option}
                                                    </Label>
                                                    {submitted && optionLabel === q.correct_answer && <CheckCircle className="h-4 w-4 text-green-600" />}
                                                    {submitted && userAnswers[qIdx] === optionLabel && optionLabel !== q.correct_answer && <XCircle className="h-4 w-4 text-red-600" />}
                                                </div>
                                            );
                                        })}
                                    </RadioGroup>

                                    {submitted && (
                                        <div className="mt-4 p-4 bg-muted/30 rounded-lg text-sm space-y-2 border border-border">
                                            <p className="font-semibold text-foreground">Explanation:</p>
                                            <div className="text-muted-foreground leading-relaxed">
                                                <ReactMarkdown
                                                    components={markdownComponents}
                                                    urlTransform={urlTransform}
                                                >
                                                    {q.explanation}
                                                </ReactMarkdown>
                                            </div>
                                        </div>
                                    )}
                                </CardContent>
                            </Card>
                        ))}
                    </div>

                    <div className="flex justify-between items-center pt-6 pb-12">
                        <Button variant="outline" onClick={resetTest}>
                            <RefreshCw className="mr-2 h-4 w-4" />
                            Generate New Test
                        </Button>
                        {!submitted && (
                            <Button onClick={submitTest} className="px-8">
                                Submit Test
                            </Button>
                        )}
                    </div>

                    {/* Score Summary Card (Bottom) */}
                    {submitted && (
                        <div className="animate-in fade-in slide-in-from-bottom-8 duration-700 pb-12">
                            <Card className="overflow-hidden border-2 border-primary/10 shadow-lg">
                                <div className="bg-primary/5 p-6 border-b border-primary/10">
                                    <div className="flex flex-col md:flex-row justify-between items-center gap-4">
                                        <div>
                                            <h3 className="text-2xl font-bold text-primary">Performance Summary</h3>
                                            <p className="text-muted-foreground">Here is how you performed on this test</p>
                                        </div>
                                        <div className="flex items-center gap-4 bg-background p-4 rounded-xl border shadow-sm">
                                            <div className="text-right">
                                                <div className="text-sm text-muted-foreground font-medium uppercase tracking-wider">Total Score</div>
                                                <div className={cn("text-3xl font-black", score >= 0 ? "text-green-600" : "text-red-600")}>
                                                    {score.toFixed(2)}
                                                    <span className="text-lg text-muted-foreground font-medium ml-1">/ {testData.total_marks}</span>
                                                </div>
                                            </div>
                                            <div className={cn("h-12 w-12 rounded-full flex items-center justify-center text-xl font-bold",
                                                score >= (testData.total_marks * 0.4) ? "bg-green-100 text-green-700" : "bg-red-100 text-red-700"
                                            )}>
                                                {Math.round((score / testData.total_marks) * 100)}%
                                            </div>
                                        </div>
                                    </div>
                                </div>
                                <CardContent className="p-6">
                                    <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                                        <div className="p-4 rounded-lg bg-muted/50 border flex flex-col items-center justify-center text-center space-y-1">
                                            <div className="text-3xl font-bold">{testData.questions.length}</div>
                                            <div className="text-xs text-muted-foreground uppercase font-medium">Total Questions</div>
                                        </div>
                                        <div className="p-4 rounded-lg bg-blue-50 border border-blue-100 dark:bg-blue-900/20 dark:border-blue-800 flex flex-col items-center justify-center text-center space-y-1">
                                            <div className="text-3xl font-bold text-blue-700 dark:text-blue-400">{Object.keys(userAnswers).length}</div>
                                            <div className="text-xs text-blue-600/80 dark:text-blue-400/80 uppercase font-medium">Attempted</div>
                                        </div>
                                        <div className="p-4 rounded-lg bg-green-50 border border-green-100 dark:bg-green-900/20 dark:border-green-800 flex flex-col items-center justify-center text-center space-y-1">
                                            <div className="text-3xl font-bold text-green-700 dark:text-green-400">
                                                {testData.questions.filter((q, i) => userAnswers[i] === q.correct_answer).length}
                                            </div>
                                            <div className="text-xs text-green-600/80 dark:text-green-400/80 uppercase font-medium">Correct</div>
                                        </div>
                                        <div className="p-4 rounded-lg bg-red-50 border border-red-100 dark:bg-red-900/20 dark:border-red-800 flex flex-col items-center justify-center text-center space-y-1">
                                            <div className="text-3xl font-bold text-red-700 dark:text-red-400">
                                                {Object.keys(userAnswers).length - testData.questions.filter((q, i) => userAnswers[i] === q.correct_answer).length}
                                            </div>
                                            <div className="text-xs text-red-600/80 dark:text-red-400/80 uppercase font-medium">Wrong</div>
                                        </div>
                                    </div>
                                </CardContent>
                            </Card>
                        </div>
                    )}
                </div>
            )}
        </div>
    )
}
