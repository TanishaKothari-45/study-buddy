"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { FileText, ChevronDown, ChevronRight, Minimize2, BookOpen, Loader2, CheckCircle, RefreshCw } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { markdownComponents, urlTransform } from "@/components/ui/mermaid";
import { cn } from "@/lib/utils";
import { EvaluationResult, ImprovedAnswerResult } from "@/stores/types";
import { apiClient, api, showToast } from "@/lib/apiClient";

interface EvaluationResultCardProps {
    result: any; // Can be EvaluationResult or EvaluationFeedbackResult
    index?: number;
    files?: File[];
    isCollapsible?: boolean;
    defaultExpanded?: boolean;
}

// Helper function to format text with line breaks around ** markers
const formatBlueprintText = (text: string): string => {
    if (!text) return text;
    let formatted = text
        .replace(/(\d+)\.\s*\n\s*\*\*/g, '$1. **')
        .replace(/\*\*([^*:]+?):\s*\n\s*\*\*/g, '**$1:**')
        .replace(/\*\*\s*\n\s*\*\*/g, '**')
        .replace(/(\d+)\.\s*\*\*([^*:]+?):\*\*\s*/g, '$1.**$2:**\n')
        .replace(/\n{3,}/g, '\n\n')
        .trim();
    return formatted;
};

export function EvaluationResultCard({ result, index, files, isCollapsible = false, defaultExpanded = true }: EvaluationResultCardProps) {
    const [isCollapsed, setIsCollapsed] = useState(!defaultExpanded);
    const [improvedAnswerJobId, setImprovedAnswerJobId] = useState<string | null>(null);
    const [improvedAnswerStatus, setImprovedAnswerStatus] = useState<string | null>(null);
    const [improvedAnswerResult, setImprovedAnswerResult] = useState<ImprovedAnswerResult | null>(null);
    const [improvedAnswerError, setImprovedAnswerError] = useState<string | null>(null);
    const [showCompressed, setShowCompressed] = useState(true);
    const [showOriginal, setShowOriginal] = useState(false);

    const feedback = result.feedback;

    const handleGenerateImprovedAnswer = async () => {
        if (!feedback) {
            showToast("No evaluation feedback available", "error");
            return;
        }

        try {
            setImprovedAnswerStatus('queued');
            setImprovedAnswerError(null);

            const formData = new FormData();
            formData.append("question", result.question);
            if (result.student_answer) formData.append("student_answer", result.student_answer);
            formData.append("feedback", JSON.stringify(feedback));
            formData.append("word_count", (result.word_count || 250).toString());

            if (files && files.length > 0) {
                files.forEach((file) => formData.append("files", file));
            }

            const data = await apiClient<{ job_id: string, status: string }>('/evaluate-answer/generate-improved', {
                method: 'POST',
                body: formData,
                headers: {},
            });

            if (data.job_id) {
                setImprovedAnswerJobId(data.job_id);
                pollImprovedAnswerStatus(data.job_id);
            }
        } catch (error: any) {
            console.error("Failed to generate improved answer:", error);
            setImprovedAnswerError(error.message || "Failed to generate improved answer");
            setImprovedAnswerStatus('failed');
        }
    };

    const pollImprovedAnswerStatus = async (id: string) => {
        try {
            const data = await apiClient<{ status: string, result?: ImprovedAnswerResult, error?: string }>(`/evaluate-answer/status/${id}`);

            if (data.status === 'completed') {
                if (data.result) {
                    setImprovedAnswerResult(data.result);
                    setImprovedAnswerJobId(null);
                    setImprovedAnswerStatus('completed');
                } else {
                    setImprovedAnswerError("Completed but returned no results.");
                    setImprovedAnswerJobId(null);
                    setImprovedAnswerStatus('failed');
                }
            } else if (data.status === 'failed') {
                setImprovedAnswerError(data.error || "Generation failed");
                setImprovedAnswerJobId(null);
                setImprovedAnswerStatus('failed');
            } else {
                setImprovedAnswerStatus(data.status);
                setTimeout(() => pollImprovedAnswerStatus(id), 2000);
            }
        } catch (error: any) {
            console.error("Polling improved answer status error:", error);
            setImprovedAnswerError(error.message || "Failed to check status");
            setImprovedAnswerStatus('failed');
        }
    };

    return (
        <div className="space-y-6 animate-in fade-in slide-in-from-bottom-4 duration-500">
            {/* Question Card (Acts as header if collapsible) */}
            <Card
                className={cn(
                    "bg-blue-50/50 border-blue-100",
                    isCollapsible && "cursor-pointer hover:bg-blue-100/50 transition-colors"
                )}
                onClick={() => isCollapsible && setIsCollapsed(!isCollapsed)}
            >
                <CardHeader className="pb-3">
                    <div className="flex items-center justify-between">
                        <CardTitle className="text-lg text-blue-900">
                            {index !== undefined ? `Answer ${index + 1}: ` : ""}Question
                        </CardTitle>
                        {isCollapsible && (
                            <div className="text-blue-500">
                                {isCollapsed ? <ChevronRight className="h-5 w-5" /> : <ChevronDown className="h-5 w-5" />}
                            </div>
                        )}
                    </div>
                </CardHeader>
                <CardContent>
                    <p className="text-blue-800 font-medium">
                        {result.question || "Question extracted from uploaded file"}
                    </p>
                    {(result.marks || result.word_count) && (
                        <div className="mt-3 flex gap-4 text-sm text-blue-700">
                            {result.marks && <span className="font-semibold">Marks: {result.marks}</span>}
                            {result.word_count && <span className="font-semibold">Word Count: {result.word_count}</span>}
                        </div>
                    )}
                </CardContent>
            </Card>

            {!isCollapsed && (
                <>
                    {/* Examiner Expectation Blueprint */}
                    {feedback.examiner_expectation_blueprint && (
                        <Card className="border-l-4 border-l-blue-500">
                            <CardHeader className="pb-2">
                                <CardTitle className="text-base text-blue-700">Examiner's Expectation Blueprint</CardTitle>
                                <CardDescription className="text-xs">What the examiner expects for this question</CardDescription>
                            </CardHeader>
                            <CardContent className="space-y-4 text-sm text-foreground">
                                {feedback.examiner_expectation_blueprint.key_demands_of_the_question?.length > 0 && (
                                    <div>
                                        <h4 className="font-semibold text-gray-900 mb-2">Key Demands of the Question</h4>
                                        <ul className="list-disc pl-4 space-y-1 text-gray-700">
                                            {feedback.examiner_expectation_blueprint.key_demands_of_the_question.map((demand: string, i: number) => (
                                                <li key={i}>{demand}</li>
                                            ))}
                                        </ul>
                                    </div>
                                )}
                                {feedback.examiner_expectation_blueprint.ideal_logical_structure && (
                                    <div>
                                        <h4 className="font-semibold text-gray-900 mb-2">Ideal Logical Structure</h4>
                                        <div className="space-y-3 pl-4 border-l-2 border-blue-200">
                                            {['introduction', 'body', 'conclusion'].map((section: any) => (
                                                <div key={section}>
                                                    <span className="font-medium text-blue-700 capitalize">{section}: </span>
                                                    <div className="text-gray-700 whitespace-pre-line mt-1">
                                                        {formatBlueprintText(feedback.examiner_expectation_blueprint.ideal_logical_structure[section])}
                                                    </div>
                                                </div>
                                            ))}
                                        </div>
                                    </div>
                                )}
                                {feedback.examiner_expectation_blueprint.non_negotiables?.length > 0 && (
                                    <div>
                                        <h4 className="font-semibold text-gray-900 mb-2">Non-Negotiable Elements</h4>
                                        <ul className="list-disc pl-4 space-y-1 text-gray-700">
                                            {feedback.examiner_expectation_blueprint.non_negotiables.map((item: string, i: number) => (
                                                <li key={i}>{item}</li>
                                            ))}
                                        </ul>
                                    </div>
                                )}
                            </CardContent>
                        </Card>
                    )}

                    {/* Margin Comments */}
                    {feedback.margin_comments?.length > 0 && (
                        <Card className="border-l-4 border-l-indigo-500">
                            <CardHeader className="pb-3">
                                <CardTitle className="text-base text-indigo-700 flex items-center gap-2">
                                    <BookOpen className="h-5 w-5" />
                                    Margin Comments
                                </CardTitle>
                            </CardHeader>
                            <CardContent>
                                <div className="space-y-3">
                                    {feedback.margin_comments.map((comment: any, idx: number) => (
                                        <div key={idx} className={cn(
                                            "p-3 rounded-lg border-l-4",
                                            (comment.severity === "high" ? "bg-red-50 border-red-200 text-red-800" :
                                                comment.severity === "medium" ? "bg-amber-50 border-amber-200 text-amber-800" :
                                                    "bg-blue-50 border-blue-200 text-blue-800")
                                        )}>
                                            <div className="flex items-center gap-2 mb-1">
                                                <span className="text-xs font-semibold px-2 py-0.5 rounded bg-white/50 uppercase">
                                                    {comment.comment_type.replace(/_/g, ' ')}
                                                </span>
                                                <span className="text-xs font-medium">{comment.severity?.toUpperCase()} SEVERITY</span>
                                            </div>
                                            <p className="text-sm font-medium text-gray-900 mb-1 italic">"{comment.anchor_text}"</p>
                                            <p className="text-sm text-gray-800">{comment.comment}</p>
                                            {comment.suggested_fix && (
                                                <div className="mt-2 pt-2 border-t border-gray-300">
                                                    <p className="text-xs font-semibold text-gray-700 mb-1">Suggested Fix:</p>
                                                    <p className="text-xs text-gray-600">{comment.suggested_fix}</p>
                                                </div>
                                            )}
                                        </div>
                                    ))}
                                </div>
                            </CardContent>
                        </Card>
                    )}

                    {/* Directive Alignment */}
                    {feedback.directive_alignment && (
                        <Card className="border-l-4 border-l-purple-500">
                            <CardHeader className="pb-2">
                                <CardTitle className="text-base text-purple-700">Directive Alignment</CardTitle>
                            </CardHeader>
                            <CardContent className="space-y-3 text-sm text-foreground">
                                <div>
                                    <span className="font-semibold text-gray-900">Directive: </span>
                                    <span className="text-purple-700 font-medium">{feedback.directive_alignment.directive_identified}</span>
                                </div>
                                <p className="text-gray-700">{feedback.directive_alignment.alignment_assessment}</p>
                                <div className="bg-purple-50 p-3 rounded-md border border-purple-100">
                                    <h4 className="font-semibold text-purple-900 mb-1">How to Improve</h4>
                                    <p className="text-purple-800">{feedback.directive_alignment.how_to_improve}</p>
                                </div>
                            </CardContent>
                        </Card>
                    )}

                    {/* Strengths & Gaps */}
                    <div className="grid gap-4 md:grid-cols-2">
                        <Card className="border-l-4 border-l-green-500">
                            <CardHeader className="pb-2"><CardTitle className="text-base text-green-700">Strengths</CardTitle></CardHeader>
                            <CardContent>
                                {feedback.strengths?.length > 0 ? (
                                    <ul className="list-disc pl-4 space-y-1 text-sm text-gray-700">
                                        {feedback.strengths.map((item: string, i: number) => <li key={i}>{item}</li>)}
                                    </ul>
                                ) : <p className="text-sm text-gray-500 italic">No strengths identified</p>}
                            </CardContent>
                        </Card>
                        <Card className="border-l-4 border-l-red-500">
                            <CardHeader className="pb-2"><CardTitle className="text-base text-red-700">Critical Gaps & Remedies</CardTitle></CardHeader>
                            <CardContent className="space-y-3">
                                {feedback.critical_gaps_and_remedies?.map((item: any, i: number) => (
                                    <div key={i} className="p-3 bg-red-50/50 rounded-md border border-red-100">
                                        <p className="text-sm text-gray-800"><span className="text-xs font-semibold uppercase text-red-800">Gap:</span> {item.gap}</p>
                                        <p className="text-sm text-gray-700 font-medium mt-1"><span className="text-xs font-semibold uppercase text-green-800">Remedy:</span> {item.remedy}</p>
                                    </div>
                                )) || (
                                        (feedback.missing_elements?.length > 0 || feedback.improvements_needed?.length > 0) ? (
                                            <>
                                                {feedback.missing_elements?.map((item: string, i: number) => (
                                                    <div key={i} className="p-2 text-sm text-red-700 bg-red-50 rounded">Missing: {item}</div>
                                                ))}
                                                {feedback.improvements_needed?.map((item: string, i: number) => (
                                                    <div key={i} className="p-2 text-sm text-green-700 bg-green-50 rounded">Better: {item}</div>
                                                ))}
                                            </>
                                        ) : <p className="text-sm text-gray-500 italic">No gaps identified</p>
                                    )}
                            </CardContent>
                        </Card>
                    </div>

                    {/* Overall Feedback */}
                    <Card>
                        <CardContent className="p-6 space-y-4 text-sm text-foreground">
                            {feedback.section_wise_assessment && (
                                <div className="space-y-3">
                                    {['introduction', 'body', 'conclusion'].map((s: any) => (
                                        <div key={s}><h4 className="font-semibold capitalize text-gray-900">{s}</h4><p className="text-gray-700">{feedback.section_wise_assessment[s]}</p></div>
                                    ))}
                                </div>
                            )}
                            <div className="pt-4 border-t space-y-2">
                                <p className="text-gray-700"><strong>Evidence:</strong> {feedback.evidence_feedback}</p>
                                {feedback.visual_feedback && <p className="text-gray-700"><strong>Visuals:</strong> {feedback.visual_feedback}</p>}
                                {feedback.strategy_tip && (
                                    <div className="bg-green-50 p-3 rounded-md border border-green-100 text-green-800">
                                        <strong>Strategy Tip:</strong> {feedback.strategy_tip}
                                    </div>
                                )}
                                <div className="bg-gray-50 p-3 rounded-md italic text-gray-600">
                                    <strong>Verdict:</strong> {feedback.overall_assessment}
                                </div>
                            </div>
                        </CardContent>
                    </Card>

                    {/* Improved Answer Section */}
                    {!improvedAnswerResult ? (
                        <Card className="border-2 border-dashed border-indigo-200 bg-indigo-50/30">
                            <CardContent className="p-6 flex flex-col items-center text-center space-y-4 text-foreground">
                                <div className="bg-indigo-100 p-3 rounded-full"><FileText className="h-6 w-6 text-indigo-600" /></div>
                                <div>
                                    <h3 className="text-lg font-semibold mb-1">Generate Improved Answer</h3>
                                    <p className="text-sm text-gray-600">Optimize this answer with retrieval-based context and expert refinement.</p>
                                </div>
                                <Button
                                    onClick={handleGenerateImprovedAnswer}
                                    disabled={['queued', 'processing', 'pending'].includes(improvedAnswerStatus || '')}
                                    className="bg-indigo-300 hover:bg-indigo-400"
                                >
                                    {['queued', 'processing', 'pending'].includes(improvedAnswerStatus || '') ? (
                                        <><Loader2 className="mr-2 h-4 w-4 animate-spin" /> Generating...</>
                                    ) : <><RefreshCw className="mr-2 h-4 w-4" /> Generate Improved Answer</>}
                                </Button>
                                {improvedAnswerError && <p className="text-sm text-red-600">{improvedAnswerError}</p>}
                            </CardContent>
                        </Card>
                    ) : (
                        <div className="space-y-4">
                            {improvedAnswerResult.compressed_answer && (
                                <Card className="overflow-hidden border-2 border-indigo-100">
                                    <button
                                        onClick={() => setShowCompressed(!showCompressed)}
                                        className="w-full flex items-center justify-between p-4 bg-indigo-50/50 hover:bg-indigo-100 transition-colors"
                                    >
                                        <div className="flex items-center gap-2 text-indigo-900 font-semibold text-foreground">
                                            <Minimize2 className="h-4 w-4" /> Compressed Model Answer
                                        </div>
                                        <ChevronDown className={cn("h-4 w-4 transition-transform", showCompressed && "rotate-180")} />
                                    </button>
                                    {showCompressed && (
                                        <CardContent className="p-6 prose prose-indigo max-w-none text-foreground">
                                            <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents} urlTransform={urlTransform}>
                                                {improvedAnswerResult.compressed_answer}
                                            </ReactMarkdown>
                                        </CardContent>
                                    )}
                                </Card>
                            )}
                            <Card className="overflow-hidden border-2 border-indigo-100">
                                <button
                                    onClick={() => setShowOriginal(!showOriginal)}
                                    className="w-full flex items-center justify-between p-4 bg-gray-50/50 hover:bg-gray-100 transition-colors"
                                >
                                    <div className="flex items-center gap-2 font-semibold text-foreground">
                                        <FileText className="h-4 w-4" /> Full Model Answer
                                    </div>
                                    <ChevronDown className={cn("h-4 w-4 transition-transform", (showOriginal || !improvedAnswerResult.compressed_answer) && "rotate-180")} />
                                </button>
                                {(showOriginal || !improvedAnswerResult.compressed_answer) && (
                                    <CardContent className="p-6 prose prose-indigo max-w-none text-foreground">
                                        <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents} urlTransform={urlTransform}>
                                            {improvedAnswerResult.improved_answer}
                                        </ReactMarkdown>
                                    </CardContent>
                                )}
                            </Card>
                        </div>
                    )}
                </>
            )}
        </div>
    );
}
