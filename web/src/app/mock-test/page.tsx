"use client";

import { useState, useEffect, useRef } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Play, CheckCircle, XCircle, RefreshCw, Clock, BookOpen, ClipboardList, AlertCircle } from "lucide-react";
import { InlineLoader } from "@/components/ui/loader";
import { cn } from "@/lib/utils";
import ReactMarkdown from "react-markdown";
import { markdownComponents, urlTransform } from "@/components/ui/mermaid";
import { Progress } from "@/components/ui/progress";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { useMockTestStore } from "@/stores";
import { authFetch, showToast } from "@/lib/authHandler";
import { useAuth } from "@/context/AuthContext";
import ApiKeyBanner from "@/components/layout/ApiKeyBanner";
import { PageContainer } from "@/components/layout/PageContainer";

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

// UPSC History taxonomy
const HISTORY_DOMAINS: Record<string, string[]> = {
    "Indian Heritage and Culture": [
        "Art Forms",
        "Architecture",
        "Literature & Language Traditions",
        "Religious & Philosophical Streams",
        "Performing & Folk Traditions"
    ],
    "Ancient Indian History": [
        "Prehistoric Cultures",
        "Indus Valley Civilization",
        "Vedic Period",
        "Mahajanapadas & Second Urbanisation",
        "Major Empires (Mauryas, Guptas)",
        "Religion, Philosophy & Society",
        "Economy & Trade",
        "Science & Technology / Education"
    ],
    "Medieval Indian History": [
        "Early Medieval Polities",
        "Delhi Sultanate",
        "Mughal Empire",
        "Regional Kingdoms",
        "Socio-Cultural Movements (Bhakti & Sufi)",
        "Architecture & Art",
        "Economic and Agrarian Trends"
    ],
    "Modern Indian History": [
        "European Penetration & Colonial Expansion",
        "Administrative & Economic Policies",
        "Social & Religious Reform Movements",
        "Revolt of 1857",
        "Freedom Movement (1885-1947)",
        "Partition & Independence"
    ]

};


const ECONOMY_DOMAINS: Record<string, string[]> = {
    "Basic Economic Concepts": ["GDP & GNP", "National Income Accounting", "Supply & Demand", "Elasticity", "Market Structures"],
    "Macroeconomics & Policy": ["Inflation and Deflation", "Monetary Policy (RBI/MPC/Repo Rate)", "Fiscal Policy (Deficit, FRBM)", "Balance of Payments & Exchange Rates", "Budget & Economic Survey"],
    "Indian Economy & Development": ["Economic Planning in India", "Poverty & Unemployment", "Sustainable Development", "Inclusive Growth", "Sectoral Growth (Agri/Industry/Services)"],
    "Banking & Finance": ["RBI Functions", "Commercial Banking", "Financial Markets", "Non-Banking Financial Companies", "Financial Inclusion"],
    "Taxation & Public Finance": ["Direct vs Indirect Taxes", "Goods and Services Tax (GST)", "Tax Buoyancy & Structure", "Union vs State Tax Distribution", "Fiscal Federalism"],
    "External Sector & Global Economy": ["Trade & Tariff Policy", "WTO, IMF, World Bank", "Foreign Capital & Investment", "Export-Import Dynamics", "Currency Markets"],
    "Contemporary Economic Issues": ["Inflation Trends & Data (CPI/WPI)", "Banking Reforms", "MSMEs & Economic Initiatives", "Digital Public Infrastructure", "Economic Impacts of Policy Announcements"]
};

const SCIENCE_TECH_DOMAINS: Record<string, string[]> = {
    "Fundamental Science Concepts": ["Physics Basics (Energy, Forces, Waves)", "Chemistry Basics (Atoms, Molecules, Reactions)", "Biology Basics (Cells, Genetics, Ecology)", "Scientific Principles (Newtonian, Thermodynamics)", "Measurement & Units"],
    "Space & Defence Technology": ["ISRO Missions (Chandrayaan, etc.)", "Satellite Technologies (PSLV, GSLV)", "Navigation Systems (GPS/GNSS)", "Defence Technologies (Missiles, Radar)", "Space Research Organisations"],
    "Information & Communication Tech": ["Cybersecurity Fundamentals", "Artificial Intelligence & Machine Learning", "Blockchain & Distributed Ledgers", "Internet of Things (IoT)", "5G/6G and Communications"],
    "Biotechnology & Health Tech": ["Genetic Engineering", "Biotech Applications", "Vaccines & Immunology Basics", "Human Genome & DNA/RNA", "Biotech in Agriculture/Medicine"],
    "Emerging Technologies": ["Quantum Computing", "Nanotechnology", "Robotics & Automation", "Data Science & Analytics", "Green Energy Technologies"],
    "Applied Science & Research": ["Environmental Technologies", "Material Science", "Renewable Energy Systems", "Scientific Research Findings", "Innovation Trends"]
};

const ENVIRONMENT_ECOLOGY_DOMAINS: Record<string, string[]> = {
    "Ecology & Ecosystems": ["Ecosystem Concepts", "Energy Flow & Food Webs", "Biogeochemical Cycles", "Species Interactions", "Ecological Succession"],
    "Biodiversity & Conservation": ["Biodiversity Hotspots", "Protected Areas (Parks/Reserves)", "Endangered Species", "Conservation Strategies", "IUCN/National Designations"],
    "Pollution & Environmental Issues": ["Air, Water, Soil Pollution", "Noise Pollution", "Ocean & Marine Pollution", "Hazardous Waste", "Pollution Control Measures"],
    "Climate Change & Global Frameworks": ["Greenhouse Effect", "Paris Agreement", "UNFCCC", "Nationally Determined Contributions", "Climate Adaptation & Mitigation"],
    "Environmental Laws & Policies": ["Environment Protection Act", "Forest Conservation Act", "Wildlife Protection Act", "EIA/CRZ Notifications", "Water & Air Quality Standards"],
    "Natural Resource Management": ["Water Resource Management", "Soil & Land Use", "Forest & Wildlife", "Mineral Resource Governance", "Sustainable Development Goals"],
    "Contemporary Environmental Issues": ["Climate Summits", "National Missions (e.g., Namami Gange)", "Species Discovery/Threat News", "Disaster Impact on Ecology", "New Policy Developments"]
};

const POLITY_DOMAINS: Record<string, string[]> = {
    "Constitutional Framework": ["Preamble", "Basic Structure Doctrine", "Fundamental Rights", "Directive Principles (DPSP)", "Fundamental Duties"],
    "Union Government": ["President", "Prime Minister & Council of Ministers", "Parliament (Rajya Sabha & Lok Sabha)", "Union Executive", "Union Legislature"],
    "State & Local Governance": ["State Executive & Legislature", "Governor", "Panchayati Raj Institutions", "Municipal Governance", "Centre–State Relations"],
    "Judiciary & Legal Institutions": ["Supreme Court", "High Courts", "Judicial Review", "Writ Jurisdiction", "Tribunals & Legal Bodies"],
    "Electoral Processes & Reforms": ["Election Commission", "Electoral Laws", "Delimitation", "Political Parties", "Election Finance"],
    "Governance & Public Policy": ["Public Administration", "Policy Formulation", "Accountability Mechanisms", "Civil Services", "Legislative Procedures"],
    "Contemporary Governance Issues": ["New Constitutional Amendments", "Governance Reforms", "Citizenship Laws", "Centre–State Legal Issues", "Judicial Pronouncements Impacting Governance"]
};

const SUBJECT_DOMAINS: Record<string, Record<string, string[]>> = {
    "Geography": GEOGRAPHY_DOMAINS,
    "History": HISTORY_DOMAINS,
    "Economy": ECONOMY_DOMAINS,
    "Science & Tech": SCIENCE_TECH_DOMAINS,
    "Environment & Ecology": ENVIRONMENT_ECOLOGY_DOMAINS,
    "Polity": POLITY_DOMAINS
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
    const [selectedSubject, setSelectedSubject] = useState<string>("Geography");
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

    // Proactively show banner if key is missing or invalid (only when logged in)
    useEffect(() => {
        if (user && (user.has_gemini_api_key === false || isApiKeyValid === 'invalid')) {
            // TODO: REVERT FOR PROD — remove hasLocalKey check; restore: if (user && (...)) setShowBanner(true);
            // Only show banner if no local key is set (no-auth India mode)
            const hasLocalKey = typeof window !== 'undefined' && !!localStorage.getItem('gemini_api_key');
            if (!hasLocalKey) setShowBanner(true);
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
        // TODO: REVERT FOR PROD — remove the hasLocalKey bypass below and restore:
        //   if (!user || user.has_gemini_api_key === false || isApiKeyValid === 'invalid') {
        // No-auth India mode: if a local key exists in localStorage, skip this check
        const hasLocalKey = typeof window !== 'undefined' && !!localStorage.getItem('gemini_api_key');
        if (!hasLocalKey && (!user || user.has_gemini_api_key === false || isApiKeyValid === 'invalid')) {
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
                    topics: topics,
                    subject: selectedSubject
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

                    if (process.env.NODE_ENV === 'development') {
                        console.log("Mock Test Result:", result);
                    }


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
        <PageContainer
            title="Interactive mock test"
            description="Take a custom mock test tailored to your preferred domains and topics."
        >
            <div className="w-full space-y-8">
                {/* API Key Banner */}
                <ApiKeyBanner showBanner={showBanner} onKeySet={() => setShowBanner(false)} />

                {/* Main Content Actions */}
                <div className="flex items-center justify-end gap-3 w-full mb-2">
                    <Button
                        variant="outline"
                        size="sm"
                        onClick={resetTest}
                        className="flex items-center gap-2"
                        disabled={loading && !submitted}
                    >
                        <RefreshCw className={cn("h-4 w-4", loading ? "animate-spin" : "")} />
                        Reset Test
                    </Button>
                </div>

                {!testData ? (
                    <Card>
                        <CardHeader>
                            <CardTitle>Configure test</CardTitle>
                            <CardDescription>Customize your mock test parameters.</CardDescription>
                        </CardHeader>
                        <CardContent className="space-y-6">
                            <div className="grid gap-4 md:grid-cols-2">
                                {/* Basic Settings */}
                                <div className="space-y-1.5">
                                    <Label className="text-xs font-medium text-[var(--text-muted)] uppercase tracking-wide">Number of questions</Label>
                                    <Select value={numQuestions} onValueChange={setNumQuestions}>
                                        <SelectTrigger>
                                            <SelectValue placeholder="Select count" />
                                        </SelectTrigger>
                                        <SelectContent className="bg-[var(--card)] z-50">
                                            <SelectItem value="5">5 questions (quick)</SelectItem>
                                            <SelectItem value="10">10 questions</SelectItem>
                                            <SelectItem value="20">20 questions</SelectItem>
                                            <SelectItem value="50">50 questions</SelectItem>
                                            <SelectItem value="100">100 questions (full mock)</SelectItem>
                                        </SelectContent>
                                    </Select>
                                </div>

                                {/* Subject Selection */}
                                <div className="space-y-1.5">
                                    <Label className="text-xs font-medium text-[var(--text-muted)] uppercase tracking-wide">Subject</Label>
                                    <Select
                                        value={selectedSubject}
                                        onValueChange={(val) => {
                                            setSelectedSubject(val);
                                            setSelectedDomain(""); // Reset domain when subject changes
                                            setSelectedSubDomain("");
                                        }}
                                    >
                                        <SelectTrigger>
                                            <SelectValue placeholder="Select subject" />
                                        </SelectTrigger>
                                        <SelectContent className="bg-[var(--card)] z-50">
                                            {Object.keys(SUBJECT_DOMAINS).map((subject) => (
                                                <SelectItem key={subject} value={subject}>{subject}</SelectItem>
                                            ))}
                                        </SelectContent>
                                    </Select>
                                </div>
                            </div>

                            {/* Topic Selection */}
                            <div className="space-y-4 pt-5 border-t border-[var(--card-border)]">
                                <Label className="text-sm font-semibold text-[var(--text)]">Topic Selection</Label>

                                <div className="grid gap-4 md:grid-cols-2">
                                    <div className="space-y-1.5">
                                        <Label className="text-xs font-medium text-[var(--text-muted)] uppercase tracking-wide">Major domain</Label>
                                        <Select
                                            value={selectedDomain}
                                            onValueChange={(val) => {
                                                setSelectedDomain(val);
                                                setSelectedSubDomain(""); // Reset subdomain when domain changes
                                            }}
                                        >
                                            <SelectTrigger>
                                                <SelectValue placeholder="Select major domain" />
                                            </SelectTrigger>
                                            <SelectContent className="bg-[var(--card)] z-50">
                                                {selectedSubject && SUBJECT_DOMAINS[selectedSubject] ? (
                                                    Object.keys(SUBJECT_DOMAINS[selectedSubject]).map((domain) => (
                                                        <SelectItem key={domain} value={domain}>{domain}</SelectItem>
                                                    ))
                                                ) : (
                                                    <SelectItem value="none" disabled>Select subject first</SelectItem>
                                                )}
                                            </SelectContent>
                                        </Select>
                                    </div>

                                    <div className="space-y-1.5">
                                        <Label className="text-xs font-medium text-[var(--text-muted)] uppercase tracking-wide">Sub-domain (optional)</Label>
                                        <Select
                                            value={selectedSubDomain}
                                            onValueChange={setSelectedSubDomain}
                                            disabled={!selectedDomain}
                                        >
                                            <SelectTrigger>
                                                <SelectValue placeholder="Select specific topic" />
                                            </SelectTrigger>
                                            <SelectContent className="bg-[var(--card)] z-50">
                                                <SelectItem value="all">All sub-topics</SelectItem>
                                                {selectedSubject && selectedDomain && SUBJECT_DOMAINS[selectedSubject]?.[selectedDomain]?.map((sub) => (
                                                    <SelectItem key={sub} value={sub}>{sub}</SelectItem>
                                                ))}
                                            </SelectContent>
                                        </Select>
                                    </div>
                                </div>

                                <div className="relative pt-2 pb-2">
                                    <div className="absolute inset-0 flex items-center">
                                        <span className="w-full border-t border-[var(--card-border)]" />
                                    </div>
                                    <div className="relative flex justify-center text-xs uppercase tracking-widest font-medium">
                                        <span className="bg-[var(--card)] px-3 text-[var(--text-faint)]">or</span>
                                    </div>
                                </div>

                                <div className="space-y-1.5">
                                    <Label className="text-sm font-medium text-[var(--text)]">Custom topic</Label>
                                    <Input
                                        placeholder="e.g. El Nino, Coral Reefs, Industrial Location Theory"
                                        value={customTopic}
                                        onChange={(e) => setCustomTopic(e.target.value)}
                                    />
                                    <p className="text-xs text-[var(--text-muted)]">
                                        Type a specific topic to override the dropdown selection.
                                    </p>
                                </div>
                            </div>

                            {/* Progress Indicator */}
                            {loading && (
                                <div className="space-y-3 pt-5 border-t border-[var(--card-border)] animate-fade-up">
                                    <div className="flex justify-between items-center text-sm">
                                        <span className="font-medium text-[var(--text)] flex items-center gap-2">
                                            <InlineLoader className="text-amber-600" />
                                            {statusMessage}
                                        </span>
                                        <span className="text-[var(--text-muted)] font-medium text-xs">{progress}%</span>
                                    </div>
                                    <Progress value={progress} />
                                    <div className="flex justify-start">
                                        <Button variant="ghost" size="sm" onClick={handleCancel} className="text-red-600 hover:text-red-700 hover:bg-red-50 dark:hover:bg-red-900/20 text-xs h-8">
                                            Cancel generation
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
                                        <InlineLoader className="mr-2" />
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
                        <Card className={cn("border-t-4 shadow-sm", submitted ? (score >= 0 ? "border-t-amber-500" : "border-t-red-500") : "border-t-amber-600")}>
                            <CardHeader className="pb-3 border-b border-[var(--card-border)] bg-[var(--bg-secondary)] rounded-t-xl">
                                <div className="flex justify-between items-start">
                                    <div>
                                        <CardTitle className="text-xl font-bold text-[var(--text)]">{submitted ? "Test results" : "Mock test in progress"}</CardTitle>
                                        <CardDescription className="flex items-center gap-3 mt-2 text-[var(--text-muted)] font-medium">
                                            <span className="flex items-center gap-1.5"><Clock className="h-4 w-4 text-amber-600" /> {testData.time_allowed}</span>
                                            <span className="text-[var(--text-faint)]">•</span>
                                            <span>Total marks: {testData.total_marks}</span>
                                        </CardDescription>
                                    </div>
                                    {submitted && (
                                        <div className="text-right">
                                            <div className="text-3xl font-bold text-[var(--text)]">{score}</div>
                                            <div className="text-xs font-medium uppercase tracking-wide text-[var(--text-muted)] mt-1">Your score</div>
                                        </div>
                                    )}
                                </div>
                            </CardHeader>
                            {!submitted && (
                                <CardContent className="pt-4">
                                    <div className="bg-amber-50 dark:bg-amber-900/10 text-amber-900 dark:text-amber-200 text-sm p-4 rounded-lg border border-amber-200 dark:border-amber-800">
                                        <strong className="font-semibold uppercase tracking-wide text-xs">Instructions</strong>
                                        <ul className="list-disc list-outside ml-4 mt-2 space-y-1 text-sm opacity-90">
                                            {testData.instructions.map((inst, i) => (
                                                <li key={i} className="pl-1">{inst}</li>
                                            ))}
                                        </ul>
                                    </div>
                                </CardContent>
                            )}
                        </Card>

                        {/* Questions List */}
                        <div className="space-y-6">
                            {testData.questions.map((q, qIdx) => (
                                <Card key={qIdx} className={cn("transition-all duration-300", submitted ? (userAnswers[qIdx] === q.correct_answer ? "ring-1 ring-amber-500 border-amber-200 dark:border-amber-800" : userAnswers[qIdx] ? "ring-1 ring-red-500 border-red-200 dark:border-red-800" : "") : "")}>
                                    <CardHeader className="pb-3 border-b border-[var(--card-border)] bg-[var(--bg-secondary)] rounded-t-xl">
                                        <div className="flex gap-4">
                                            <span className="flex-shrink-0 flex items-center justify-center w-8 h-8 rounded-full bg-[var(--bg-tertiary)] text-[var(--text)] font-semibold text-sm border border-[var(--card-border)] shadow-sm">
                                                {qIdx + 1}
                                            </span>
                                            <div className="space-y-1.5 pt-0.5">
                                                <CardTitle className="text-base font-medium leading-relaxed whitespace-pre-line text-[var(--text)]">
                                                    {q.question}
                                                </CardTitle>
                                                {submitted && (
                                                    <div className="flex items-center gap-2 text-xs font-medium text-[var(--text-muted)] mt-2">
                                                        <BookOpen className="h-3.5 w-3.5 text-amber-600" />
                                                        Source: {q.source.filename} {q.source.chapter && `(${q.source.chapter})`}
                                                    </div>
                                                )}
                                            </div>
                                        </div>
                                    </CardHeader>
                                    <CardContent className="p-6 md:p-8 space-y-4">
                                        <RadioGroup
                                            value={userAnswers[qIdx] || ""}
                                            onValueChange={(val) => handleAnswerSelect(qIdx, val)}
                                            disabled={submitted}
                                            className="space-y-3"
                                        >
                                            {q.options.map((option, optIdx) => {
                                                const optionLabel = getOptionLabel(optIdx);
                                                let optionClass = "flex items-center space-x-3 p-4 rounded-xl border border-[var(--card-border)] bg-[var(--card)] hover:bg-[var(--bg-secondary)] transition-colors cursor-pointer";
                                                let dotClass = "border-[var(--card-border)] text-[var(--text-muted)]";

                                                if (submitted) {
                                                    if (optionLabel === q.correct_answer) {
                                                        // Correct answer
                                                        optionClass = "flex items-center space-x-3 p-4 rounded-xl border border-amber-200 bg-amber-50/50 text-amber-900 dark:bg-amber-900/20 dark:border-amber-800 dark:text-amber-100";
                                                        dotClass = "bg-amber-600 border-amber-600 text-white";
                                                    } else if (userAnswers[qIdx] === optionLabel) {
                                                        // Wrong answer
                                                        optionClass = "flex items-center space-x-3 p-4 rounded-xl border border-red-200 bg-red-50 text-red-900 dark:bg-red-900/20 dark:border-red-800 dark:text-red-100";
                                                        dotClass = "bg-red-500 border-red-500 text-white";
                                                    }
                                                } else if (userAnswers[qIdx] === optionLabel) {
                                                    optionClass = "flex items-center space-x-3 p-4 rounded-xl border border-amber-300 bg-amber-50/30 dark:border-amber-700 dark:bg-amber-900/20";
                                                    dotClass = "bg-amber-600 border-amber-600 text-white";
                                                }

                                                return (
                                                    <div key={optIdx} className={optionClass} onClick={() => !submitted && handleAnswerSelect(qIdx, optionLabel)}>
                                                        <RadioGroupItem value={optionLabel} id={`q${qIdx}-opt${optIdx}`} className="sr-only" />
                                                        <div className={cn(
                                                            "w-6 h-6 rounded-full border-2 flex items-center justify-center text-xs font-semibold transition-all flex-shrink-0",
                                                            dotClass
                                                        )}>
                                                            {submitted || userAnswers[qIdx] !== optionLabel ? optionLabel : ""}
                                                        </div>
                                                        <Label htmlFor={`q${qIdx}-opt${optIdx}`} className="flex-1 cursor-pointer font-normal text-sm leading-relaxed">
                                                            {option}
                                                        </Label>
                                                        {submitted && optionLabel === q.correct_answer && <CheckCircle className="h-5 w-5 text-amber-600 flex-shrink-0" />}
                                                        {submitted && userAnswers[qIdx] === optionLabel && optionLabel !== q.correct_answer && <XCircle className="h-5 w-5 text-red-500 flex-shrink-0" />}
                                                    </div>
                                                );
                                            })}
                                        </RadioGroup>

                                        {submitted && (
                                            <div className="mt-6 p-5 bg-[var(--bg-secondary)] rounded-xl border border-[var(--card-border)] animate-fade-up">
                                                <h4 className="font-semibold text-sm text-[var(--text)] mb-3 flex items-center gap-2">
                                                    <ClipboardList className="h-4 w-4 text-amber-600" />
                                                    Explanation
                                                </h4>
                                                <div className="prose prose-sm max-w-none text-[var(--text-muted)] dark:prose-invert">
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

                        <div className="flex flex-col sm:flex-row justify-between items-center gap-4 pt-8 pb-12">
                            <Button variant="outline" onClick={resetTest} className="w-full sm:w-auto min-w-[160px]">
                                <RefreshCw className="mr-2 h-4 w-4" />
                                Generate new test
                            </Button>
                            {!submitted && (
                                <Button onClick={submitTest} size="lg" className="w-full sm:w-auto min-w-[160px]">
                                    Submit test
                                </Button>
                            )}
                        </div>

                        {/* Score Summary Card (Bottom) */}
                        {submitted && (
                            <div className="animate-fade-up pb-12">
                                <Card className="overflow-hidden border-2 border-amber-600/20 shadow-amber-sm">
                                    <div className="bg-amber-50/50 dark:bg-amber-900/10 p-6 sm:p-8 border-b border-[var(--card-border)]">
                                        <div className="flex flex-col md:flex-row justify-between items-center gap-6">
                                            <div className="text-center md:text-left">
                                                <h3 className="text-2xl font-bold text-[var(--text)]">Performance summary</h3>
                                                <p className="text-[var(--text-muted)] mt-1">Here is how you performed on this test</p>
                                            </div>
                                            <div className="flex items-center gap-6 bg-[var(--card)] p-5 rounded-2xl border border-[var(--card-border)] shadow-sm w-full md:w-auto justify-center md:justify-end">
                                                <div className="text-right">
                                                    <div className="text-xs font-semibold text-[var(--text-muted)] uppercase tracking-widest mb-1">Total Score</div>
                                                    <div className={cn("text-4xl font-bold tracking-tight", score >= 0 ? "text-amber-600" : "text-red-600")}>
                                                        {score.toFixed(2)}
                                                        <span className="text-xl text-[var(--text-faint)] font-medium ml-1">/ {testData.total_marks}</span>
                                                    </div>
                                                </div>
                                                <div className={cn("h-16 w-16 rounded-full flex items-center justify-center text-xl font-bold border-4",
                                                    score >= (testData.total_marks * 0.4) ? "bg-amber-50 text-amber-600 border-amber-100" : "bg-red-50 text-red-600 border-red-100"
                                                )}>
                                                    {Math.round((score / testData.total_marks) * 100)}%
                                                </div>
                                            </div>
                                        </div>
                                    </div>
                                    <CardContent className="p-6 sm:p-8">
                                        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 sm:gap-6">
                                            <div className="p-5 rounded-xl bg-[var(--bg-secondary)] border border-[var(--card-border)] flex flex-col items-center justify-center text-center space-y-2">
                                                <div className="text-4xl font-bold text-[var(--text)]">{testData.questions.length}</div>
                                                <div className="text-xs text-[var(--text-muted)] uppercase font-semibold tracking-wide">Total Qs</div>
                                            </div>
                                            <div className="p-5 rounded-xl bg-[var(--bg-secondary)] border border-[var(--card-border)] flex flex-col items-center justify-center text-center space-y-2">
                                                <div className="text-4xl font-bold text-[var(--text)]">{Object.keys(userAnswers).length}</div>
                                                <div className="text-xs text-[var(--text-muted)] uppercase font-semibold tracking-wide">Attempted</div>
                                            </div>
                                            <div className="p-5 rounded-xl bg-amber-50/50 border border-amber-200 dark:bg-amber-900/10 dark:border-amber-800/50 flex flex-col items-center justify-center text-center space-y-2">
                                                <div className="text-4xl font-bold text-amber-600">
                                                    {testData.questions.filter((q, i) => userAnswers[i] === q.correct_answer).length}
                                                </div>
                                                <div className="text-xs text-amber-700 dark:text-amber-400 uppercase font-semibold tracking-wide">Correct</div>
                                            </div>
                                            <div className="p-5 rounded-xl bg-red-50 border border-red-100 dark:bg-red-900/10 dark:border-red-900/50 flex flex-col items-center justify-center text-center space-y-2">
                                                <div className="text-4xl font-bold text-red-600">
                                                    {Object.keys(userAnswers).length - testData.questions.filter((q, i) => userAnswers[i] === q.correct_answer).length}
                                                </div>
                                                <div className="text-xs text-red-700 dark:text-red-400 uppercase font-semibold tracking-wide">Wrong</div>
                                            </div>
                                        </div>
                                    </CardContent>
                                </Card>
                            </div>
                        )}
                    </div>
                )}
            </div>
        </PageContainer>
    )
}
