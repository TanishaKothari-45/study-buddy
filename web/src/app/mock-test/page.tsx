"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Loader2, Play, CheckCircle, XCircle, RefreshCw, Clock, BookOpen, ClipboardList } from "lucide-react";
import { cn } from "@/lib/utils";
import ReactMarkdown from "react-markdown";
import { markdownComponents, urlTransform } from "@/components/ui/mermaid";

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

interface MockTestQuestion {
    question: string;
    options: string[];
    correct_answer: string;
    explanation: string;
    source: {
        filename: string;
        chapter?: string;
        section?: string;
    };
}

interface MockTestResponse {
    questions: MockTestQuestion[];
    total_marks: number;
    time_allowed: string;
    instructions: string[];
}

export default function MockTestPage() {
    const [loading, setLoading] = useState(false);
    const [testData, setTestData] = useState<MockTestResponse | null>(null);
    const [userAnswers, setUserAnswers] = useState<Record<number, string>>({});
    const [submitted, setSubmitted] = useState(false);
    const [score, setScore] = useState(0);

    // Configuration State
    const [numQuestions, setNumQuestions] = useState("5");
    const [difficulty, setDifficulty] = useState("medium");

    // Topic Selection State
    const [selectedDomain, setSelectedDomain] = useState<string>("");
    const [selectedSubDomain, setSelectedSubDomain] = useState<string>("");
    const [customTopic, setCustomTopic] = useState("");

    const generateTest = async () => {
        setLoading(true);
        setTestData(null);
        setUserAnswers({});
        setSubmitted(false);
        setScore(0);

        // Determine topics list
        let topics: string[] = [];
        if (customTopic.trim()) {
            topics = [customTopic.trim()];
        } else if (selectedSubDomain && selectedSubDomain !== "all") {
            topics = [selectedSubDomain];
        } else if (selectedDomain) {
            // If only domain is selected, include all its subtopics or just the domain name
            // The backend likely handles broad topics, but let's be specific if possible
            // or just send the domain name.
            topics = [selectedDomain];
        } else {
            topics = ["Geography"]; // Fallback
        }

        try {
            const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8001";
            const res = await fetch(`${API_URL}/mock-test/generate`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    num_questions: parseInt(numQuestions),
                    difficulty,
                    topics: topics
                }),
            });

            if (!res.ok) throw new Error("Failed to generate test");
            const data = await res.json();
            setTestData(data);
        } catch (error) {
            console.error("Failed to generate test:", error);
            alert("Failed to generate mock test. Please try again.");
        } finally {
            setLoading(false);
        }
    };

    const handleAnswerSelect = (questionIndex: number, option: string) => {
        if (submitted) return;
        setUserAnswers(prev => ({
            ...prev,
            [questionIndex]: option
        }));
    };

    const submitTest = () => {
        if (!testData) return;

        let correctCount = 0;
        testData.questions.forEach((q, idx) => {
            if (userAnswers[idx] === q.correct_answer) {
                correctCount++;
            }
        });

        // Calculate score: +2 for correct, -0.66 for wrong
        let calculatedScore = 0;
        testData.questions.forEach((q, idx) => {
            if (userAnswers[idx]) {
                if (userAnswers[idx] === q.correct_answer) {
                    calculatedScore += 2;
                } else {
                    calculatedScore -= 0.66;
                }
            }
        });

        setScore(parseFloat(calculatedScore.toFixed(2)));
        setSubmitted(true);
        window.scrollTo({ top: 0, behavior: 'smooth' });
    };

    const getOptionLabel = (index: number) => String.fromCharCode(65 + index); // 0->A, 1->B...

    return (
        <div className="p-8 max-w-5xl mx-auto space-y-8">
            <div className="flex flex-col space-y-2">
                <h1 className="text-3xl font-bold tracking-tight text-foreground">
                    Prelims Mock Test
                </h1>
                <p className="text-muted-foreground">
                    Generate AI-powered mock tests based on your study materials and UPSC patterns.
                </p>
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
                                    </SelectContent>
                                </Select>
                            </div>

                            <div className="space-y-2">
                                <Label>Difficulty Level</Label>
                                <Select value={difficulty} onValueChange={setDifficulty}>
                                    <SelectTrigger>
                                        <SelectValue placeholder="Select difficulty" />
                                    </SelectTrigger>
                                    <SelectContent className="bg-card z-50">
                                        <SelectItem value="easy">Easy (Conceptual)</SelectItem>
                                        <SelectItem value="medium">Medium (Standard)</SelectItem>
                                        <SelectItem value="hard">Hard (Complex/Applied)</SelectItem>
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
                    </CardContent>
                    <CardFooter>
                        <Button onClick={generateTest} disabled={loading} className="w-full md:w-auto">
                            {loading ? (
                                <>
                                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                                    Generating Test...
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
                                            <CardTitle className="text-base font-medium leading-relaxed">
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
                                                    optionClass = "flex items-center space-x-2 p-3 rounded-lg border border-green-200 bg-green-50 text-green-900 dark:bg-green-900/20 dark:border-green-800 dark:text-green-300";
                                                } else if (userAnswers[qIdx] === optionLabel) {
                                                    optionClass = "flex items-center space-x-2 p-3 rounded-lg border border-red-200 bg-red-50 text-red-900 dark:bg-red-900/20 dark:border-red-800 dark:text-red-300";
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
                                                            submitted && userAnswers[qIdx] === optionLabel ? "bg-red-600 border-red-600 text-white" :
                                                                userAnswers[qIdx] === optionLabel ? "bg-accent border-accent text-white" : "border-border text-muted-foreground"
                                                    )}>
                                                        {userAnswers[qIdx] === optionLabel && !submitted && <div className="w-3 h-3 rounded-full bg-white" />}
                                                        {!userAnswers[qIdx] || userAnswers[qIdx] !== optionLabel ? optionLabel : ""}
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
                        <Button variant="outline" onClick={() => setTestData(null)}>
                            <RefreshCw className="mr-2 h-4 w-4" />
                            Generate New Test
                        </Button>
                        {!submitted && (
                            <Button onClick={submitTest} className="px-8">
                                Submit Test
                            </Button>
                        )}
                    </div>
                </div>
            )}
        </div>
    );
}
