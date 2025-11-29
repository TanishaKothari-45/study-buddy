"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Checkbox } from "@/components/ui/checkbox";
import { Loader2, Play, CheckCircle, XCircle, RefreshCw, Clock, BookOpen } from "lucide-react";
import { cn } from "@/lib/utils";
import ReactMarkdown from "react-markdown";

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

const TOPICS = [
    "Geomorphology",
    "Climatology",
    "Oceanography",
    "Biogeography",
    "Human Geography",
    "Economic Geography",
    "Indian Geography",
    "World Geography"
];

export default function MockTestPage() {
    const [loading, setLoading] = useState(false);
    const [testData, setTestData] = useState<MockTestResponse | null>(null);
    const [userAnswers, setUserAnswers] = useState<Record<number, string>>({});
    const [submitted, setSubmitted] = useState(false);
    const [score, setScore] = useState(0);

    // Configuration State
    const [numQuestions, setNumQuestions] = useState("5");
    const [difficulty, setDifficulty] = useState("medium");
    const [selectedTopics, setSelectedTopics] = useState<string[]>([]);

    const handleTopicToggle = (topic: string) => {
        setSelectedTopics(prev =>
            prev.includes(topic)
                ? prev.filter(t => t !== topic)
                : [...prev, topic]
        );
    };

    const generateTest = async () => {
        setLoading(true);
        setTestData(null);
        setUserAnswers({});
        setSubmitted(false);
        setScore(0);

        try {
            const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8001";
            const res = await fetch(`${API_URL}/mock-test/generate`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    num_questions: parseInt(numQuestions),
                    difficulty,
                    topics: selectedTopics.length > 0 ? selectedTopics : ["Geography"]
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
            // Map option index (0, 1, 2, 3) to letter (A, B, C, D) if needed
            // But the backend returns correct_answer as "A", "B", etc.
            // And our UI will use "A", "B", "C", "D" as values.
            if (userAnswers[idx] === q.correct_answer) {
                correctCount++;
            }
        });

        // Calculate score: +2 for correct, -0.66 for wrong
        // Unanswered = 0
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
                <h1 className="text-3xl font-bold tracking-tight text-gray-900">
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
                            <div className="space-y-2">
                                <Label>Number of Questions</Label>
                                <Select value={numQuestions} onValueChange={setNumQuestions}>
                                    <SelectTrigger>
                                        <SelectValue placeholder="Select count" />
                                    </SelectTrigger>
                                    <SelectContent>
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
                                    <SelectContent>
                                        <SelectItem value="easy">Easy (Conceptual)</SelectItem>
                                        <SelectItem value="medium">Medium (Standard)</SelectItem>
                                        <SelectItem value="hard">Hard (Complex/Applied)</SelectItem>
                                    </SelectContent>
                                </Select>
                            </div>
                        </div>

                        <div className="space-y-3">
                            <Label>Topics (Optional)</Label>
                            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                                {TOPICS.map((topic) => (
                                    <div key={topic} className="flex items-center space-x-2">
                                        <Checkbox
                                            id={topic}
                                            checked={selectedTopics.includes(topic)}
                                            onCheckedChange={() => handleTopicToggle(topic)}
                                        />
                                        <label
                                            htmlFor={topic}
                                            className="text-sm font-medium leading-none peer-disabled:cursor-not-allowed peer-disabled:opacity-70"
                                        >
                                            {topic}
                                        </label>
                                    </div>
                                ))}
                            </div>
                        </div>
                    </CardContent>
                    <CardFooter>
                        <Button onClick={generateTest} disabled={loading} className="w-full md:w-auto bg-blue-600 hover:bg-blue-700">
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
                    <Card className={cn("border-l-4", submitted ? (score >= 0 ? "border-l-green-500" : "border-l-red-500") : "border-l-blue-500")}>
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
                                <div className="bg-blue-50 text-blue-800 text-sm p-3 rounded-md">
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
                            <Card key={qIdx} className={cn("transition-all", submitted ? (userAnswers[qIdx] === q.correct_answer ? "ring-1 ring-green-500" : userAnswers[qIdx] ? "ring-1 ring-red-500" : "") : "")}>
                                <CardHeader className="pb-2">
                                    <div className="flex gap-3">
                                        <span className="flex-shrink-0 flex items-center justify-center w-8 h-8 rounded-full bg-gray-100 text-gray-700 font-bold text-sm">
                                            {qIdx + 1}
                                        </span>
                                        <div className="space-y-1">
                                            <CardTitle className="text-base font-medium leading-relaxed">
                                                {q.question}
                                            </CardTitle>
                                            {submitted && (
                                                <div className="flex items-center gap-2 text-xs text-gray-500">
                                                    <BookOpen className="h-3 w-3" />
                                                    Source: {q.source.filename} {q.source.chapter && `(${q.source.chapter})`}
                                                </div>
                                            )}
                                        </div>
                                    </div>
                                </CardHeader>
                                <CardContent className="pl-14 space-y-3">
                                    <RadioGroup
                                        value={userAnswers[qIdx]}
                                        onValueChange={(val) => handleAnswerSelect(qIdx, val)}
                                        disabled={submitted}
                                    >
                                        {q.options.map((option, optIdx) => {
                                            const optionLabel = getOptionLabel(optIdx);
                                            let optionClass = "flex items-center space-x-2 p-3 rounded-lg border border-transparent hover:bg-gray-50 transition-colors cursor-pointer";

                                            if (submitted) {
                                                if (optionLabel === q.correct_answer) {
                                                    optionClass = "flex items-center space-x-2 p-3 rounded-lg border border-green-200 bg-green-50 text-green-900";
                                                } else if (userAnswers[qIdx] === optionLabel) {
                                                    optionClass = "flex items-center space-x-2 p-3 rounded-lg border border-red-200 bg-red-50 text-red-900";
                                                }
                                            } else if (userAnswers[qIdx] === optionLabel) {
                                                optionClass = "flex items-center space-x-2 p-3 rounded-lg border border-blue-200 bg-blue-50";
                                            }

                                            return (
                                                <div key={optIdx} className={optionClass} onClick={() => !submitted && handleAnswerSelect(qIdx, optionLabel)}>
                                                    <RadioGroupItem value={optionLabel} id={`q${qIdx}-opt${optIdx}`} className="sr-only" />
                                                    <div className={cn(
                                                        "w-6 h-6 rounded-full border flex items-center justify-center text-xs font-medium",
                                                        submitted && optionLabel === q.correct_answer ? "bg-green-600 border-green-600 text-white" :
                                                            submitted && userAnswers[qIdx] === optionLabel ? "bg-red-600 border-red-600 text-white" :
                                                                userAnswers[qIdx] === optionLabel ? "bg-blue-600 border-blue-600 text-white" : "border-gray-300 text-gray-500"
                                                    )}>
                                                        {optionLabel}
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
                                        <div className="mt-4 p-4 bg-gray-50 rounded-lg text-sm space-y-2 border border-gray-100">
                                            <p className="font-semibold text-gray-900">Explanation:</p>
                                            <div className="text-gray-700 leading-relaxed">
                                                <ReactMarkdown>{q.explanation}</ReactMarkdown>
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
                            <Button onClick={submitTest} className="bg-green-600 hover:bg-green-700 px-8">
                                Submit Test
                            </Button>
                        )}
                    </div>
                </div>
            )}
        </div>
    );
}
