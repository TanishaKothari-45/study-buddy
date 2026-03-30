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
            if (result.paper_and_subject_identification) {
                formData.append("paper_and_subject_identification", JSON.stringify(result.paper_and_subject_identification));
            }
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
                    "bg-[var(--bg-secondary)] border-[var(--card-border)] shadow-sm",
                    isCollapsible && "cursor-pointer hover:bg-[var(--bg-tertiary)] transition-colors"
                )}
                onClick={() => isCollapsible && setIsCollapsed(!isCollapsed)}
            >
                <CardHeader className="pb-3 border-b border-[var(--card-border)]/50">
                    <div className="flex items-center justify-between">
                        <CardTitle className="text-lg font-bold text-[var(--text)]">
                            {index !== undefined ? `Answer ${index + 1}: ` : ""}question
                        </CardTitle>
                        {isCollapsible && (
                            <div className="text-[var(--text-muted)] hover:text-[var(--text)] transition-colors">
                                {isCollapsed ? <ChevronRight className="h-5 w-5" /> : <ChevronDown className="h-5 w-5" />}
                            </div>
                        )}
                    </div>
                </CardHeader>
                <CardContent className="pt-4">
                    <p className="text-[var(--text)] font-medium leading-relaxed">
                        {result.question || "Question extracted from uploaded file"}
                    </p>
                    {result.paper_and_subject_identification && (
                        <div className="mt-4 flex flex-wrap gap-2">
                            <span className="inline-flex items-center px-2.5 py-1 rounded-md text-[11px] font-semibold bg-[var(--card)] text-[var(--text)] border border-[var(--card-border)] uppercase tracking-wider">
                                {result.paper_and_subject_identification.gs_paper}
                            </span>
                            <span className="inline-flex items-center px-2.5 py-1 rounded-md text-[11px] font-semibold bg-amber-50/50 dark:bg-amber-900/20 text-amber-700 dark:text-amber-500 border border-amber-200 dark:border-amber-900/50 uppercase tracking-wider">
                                {result.paper_and_subject_identification.subject_domain || result.paper_and_subject_identification.primary_domain}
                            </span>
                            {result.paper_and_subject_identification.subject_domain && result.paper_and_subject_identification.primary_domain && result.paper_and_subject_identification.subject_domain !== result.paper_and_subject_identification.primary_domain && (
                                <span className="inline-flex items-center px-2.5 py-1 rounded-md text-[11px] font-semibold bg-[var(--bg-tertiary)] text-[var(--text-muted)] border border-[var(--card-border)] uppercase tracking-wider">
                                    {result.paper_and_subject_identification.primary_domain}
                                </span>
                            )}
                            {result.paper_and_subject_identification.secondary_domain && (
                                Array.isArray(result.paper_and_subject_identification.secondary_domain) ? (
                                    result.paper_and_subject_identification.secondary_domain.map((topic: string, i: number) => (
                                        <span key={i} className="inline-flex items-center px-2.5 py-1 rounded-md text-[11px] font-semibold bg-stone-100 dark:bg-stone-800 text-stone-700 dark:text-stone-300 border border-stone-200 dark:border-stone-700 uppercase tracking-wider">
                                            {topic}
                                        </span>
                                    ))
                                ) : (
                                    <span className="inline-flex items-center px-2.5 py-1 rounded-md text-[11px] font-semibold bg-stone-100 dark:bg-stone-800 text-stone-700 dark:text-stone-300 border border-stone-200 dark:border-stone-700 uppercase tracking-wider">
                                        {result.paper_and_subject_identification.secondary_domain}
                                    </span>
                                )
                            )}
                        </div>
                    )}
                    {(result.marks || result.word_count) && (
                        <div className="mt-4 pt-3 border-t border-[var(--card-border)] flex gap-5 text-[13px] text-[var(--text-muted)]">
                            {result.marks && <span className="font-semibold px-2 py-0.5 bg-[var(--card)] rounded-md border border-[var(--card-border)]">Marks: {result.marks}</span>}
                            {result.word_count && <span className="font-semibold px-2 py-0.5 bg-[var(--card)] rounded-md border border-[var(--card-border)]">Word Count: {result.word_count}</span>}
                        </div>
                    )}
                </CardContent>
            </Card>

            {!isCollapsed && (
                <>
                    {/* Examiner Expectation Blueprint */}
                    {feedback.examiner_expectation_blueprint && (
                        <Card className="border-[var(--card-border)] shadow-sm">
                            <CardHeader className="pb-3 border-b border-[var(--card-border)]/50 bg-[var(--bg-secondary)]">
                                <CardTitle className="text-base font-bold text-[var(--text)]">Examiner's expectation blueprint</CardTitle>
                                <CardDescription className="text-[13px] text-[var(--text-muted)] mt-1">What the examiner expects for this question</CardDescription>
                            </CardHeader>
                            <CardContent className="space-y-6 pt-5 text-[15px] text-[var(--text)]">
                                {feedback.examiner_expectation_blueprint.key_demands_of_the_question?.length > 0 && (
                                    <div>
                                        <h4 className="font-semibold text-[var(--text)] mb-3">Key demands of the question</h4>
                                        <ul className="list-disc pl-5 space-y-1.5 text-[var(--text-muted)]">
                                            {feedback.examiner_expectation_blueprint.key_demands_of_the_question.map((demand: string, i: number) => (
                                                <li key={i}>{demand}</li>
                                            ))}
                                        </ul>
                                    </div>
                                )}
                                {feedback.examiner_expectation_blueprint.ideal_logical_structure && (
                                    <div>
                                        <h4 className="font-semibold text-[var(--text)] mb-3">Ideal logical structure</h4>
                                        <div className="space-y-4 pl-4 border-l-2 border-stone-200 dark:border-stone-800">
                                            {['introduction', 'body', 'conclusion'].map((section: any) => (
                                                <div key={section} className="pl-2">
                                                    <span className="font-bold text-amber-600 capitalize text-sm uppercase tracking-wider">{section}</span>
                                                    <div className="text-[var(--text-muted)] whitespace-pre-line mt-1.5 leading-relaxed">
                                                        {formatBlueprintText(feedback.examiner_expectation_blueprint.ideal_logical_structure[section])}
                                                    </div>
                                                </div>
                                            ))}
                                        </div>
                                    </div>
                                )}
                                {feedback.examiner_expectation_blueprint.non_negotiables?.length > 0 && (
                                    <div>
                                        <h4 className="font-semibold text-[var(--text)] mb-3">Non-negotiable elements</h4>
                                        <ul className="list-disc pl-5 space-y-1.5 text-[var(--text-muted)]">
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
                        <Card className="border-[var(--card-border)] shadow-sm">
                            <CardHeader className="pb-3 border-b border-[var(--card-border)]/50 bg-[var(--bg-secondary)]">
                                <CardTitle className="text-base font-bold text-[var(--text)] flex items-center gap-2">
                                    <BookOpen className="h-5 w-5 text-amber-600" />
                                    Margin comments
                                </CardTitle>
                            </CardHeader>
                            <CardContent className="pt-5">
                                <div className="space-y-4">
                                    {feedback.margin_comments.map((comment: any, idx: number) => (
                                        <div key={idx} className={cn(
                                            "p-4 rounded-xl border border-[var(--card-border)]",
                                            (comment.severity === "high" ? "bg-red-50/50 dark:bg-red-950/20" :
                                                comment.severity === "medium" ? "bg-amber-50/30 dark:bg-amber-950/20" :
                                                    "bg-[var(--bg-tertiary)]")
                                        )}>
                                            <div className="flex items-center gap-2 mb-2">
                                                <span className="text-[10px] font-bold px-2 py-1 rounded bg-[var(--card)] border border-[var(--card-border)] uppercase tracking-wider text-[var(--text)]">
                                                    {comment.comment_type.replace(/_/g, ' ')}
                                                </span>
                                                <span className={cn(
                                                    "text-[10px] font-bold uppercase tracking-wider",
                                                    comment.severity === 'high' ? "text-red-600" :
                                                        comment.severity === 'medium' ? "text-amber-600" : "text-stone-500"
                                                )}>{comment.severity?.toUpperCase()} SEVERITY</span>
                                            </div>
                                            <p className="text-[15px] font-medium text-[var(--text)] mb-2 italic">"{comment.anchor_text}"</p>
                                            <p className="text-[14px] text-[var(--text-muted)] leading-relaxed">{comment.comment}</p>
                                            {comment.suggested_fix && (
                                                <div className="mt-3 pt-3 border-t border-[var(--card-border)]">
                                                    <p className="text-xs font-bold text-[var(--text)] mb-1 uppercase tracking-wide">Suggested fix</p>
                                                    <p className="text-[14px] text-amber-700 dark:text-amber-500">{comment.suggested_fix}</p>
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
                        <Card className="border-[var(--card-border)] shadow-sm">
                            <CardHeader className="pb-3 border-b border-[var(--card-border)]/50 bg-[var(--bg-secondary)]">
                                <CardTitle className="text-base font-bold text-[var(--text)]">Directive alignment</CardTitle>
                            </CardHeader>
                            <CardContent className="space-y-4 pt-5 text-[15px] text-[var(--text)]">
                                <div>
                                    <span className="font-semibold text-[var(--text-muted)]">Directive: </span>
                                    <span className="text-amber-600 font-bold px-2 py-0.5 bg-amber-50 dark:bg-amber-900/20 rounded border border-amber-100 dark:border-amber-900/50">{feedback.directive_alignment.directive_identified}</span>
                                </div>
                                <p className="text-[var(--text-muted)] leading-relaxed">{feedback.directive_alignment.alignment_assessment}</p>
                                <div className="bg-[var(--bg-secondary)] p-4 rounded-xl border border-[var(--card-border)]">
                                    <h4 className="font-semibold text-[var(--text)] mb-2 uppercase tracking-wide text-xs">How to improve</h4>
                                    <p className="text-[var(--text-muted)]">{feedback.directive_alignment.how_to_improve}</p>
                                </div>
                            </CardContent>
                        </Card>
                    )}

                    {/* Current Affairs Evaluation */}

                    {/* Strengths & Gaps */}
                    <div className="grid gap-6 md:grid-cols-2">
                        <Card className="border-[var(--card-border)] shadow-sm">
                            <CardHeader className="pb-3 border-b border-[var(--card-border)]/50 bg-[var(--bg-secondary)]">
                                <CardTitle className="text-base font-bold text-[var(--text)] flex items-center gap-2">
                                    <div className="w-2 h-2 rounded-full bg-green-500" />
                                    Strengths
                                </CardTitle>
                            </CardHeader>
                            <CardContent className="pt-5">
                                {feedback.strengths?.length > 0 ? (
                                    <ul className="list-disc pl-5 space-y-2 text-[15px] text-[var(--text-muted)]">
                                        {feedback.strengths.map((item: string, i: number) => <li key={i}>{item}</li>)}
                                    </ul>
                                ) : <p className="text-[15px] text-[var(--text-faint)] italic">No strengths identified</p>}
                            </CardContent>
                        </Card>
                        <Card className="border-[var(--card-border)] shadow-sm">
                            <CardHeader className="pb-3 border-b border-[var(--card-border)]/50 bg-[var(--bg-secondary)]">
                                <CardTitle className="text-base font-bold text-[var(--text)] flex items-center gap-2">
                                    <div className="w-2 h-2 rounded-full bg-red-500" />
                                    Critical gaps & remedies
                                </CardTitle>
                            </CardHeader>
                            <CardContent className="space-y-4 pt-5">
                                {feedback.critical_gaps_and_remedies?.map((item: any, i: number) => (
                                    <div key={i} className="p-4 bg-[var(--bg-secondary)] rounded-xl border border-[var(--card-border)]">
                                        <p className="text-[14px] text-[var(--text)] mb-2"><span className="text-[11px] font-bold uppercase tracking-wider text-red-600 dark:text-red-400 mr-2">Gap</span> {item.gap}</p>
                                        <p className="text-[14px] text-[var(--text-muted)] mt-2 pt-2 border-t border-[var(--card-border)]"><span className="text-[11px] font-bold uppercase tracking-wider text-emerald-600 dark:text-emerald-500 mr-2">Remedy</span> {item.remedy}</p>
                                    </div>
                                )) || (
                                        (feedback.missing_elements?.length > 0 || feedback.improvements_needed?.length > 0) ? (
                                            <div className="space-y-3">
                                                {feedback.missing_elements?.map((item: string, i: number) => (
                                                    <div key={i} className="p-3 text-[14px] text-red-700 bg-red-50/50 dark:bg-red-950/20 border border-red-100 dark:border-red-900/50 rounded-lg"><span className="font-semibold mr-2">Missing:</span>{item}</div>
                                                ))}
                                                {feedback.improvements_needed?.map((item: string, i: number) => (
                                                    <div key={i} className="p-3 text-[14px] text-emerald-700 bg-emerald-50/50 dark:bg-emerald-950/20 border border-emerald-100 dark:border-emerald-900/50 rounded-lg"><span className="font-semibold mr-2">Better:</span>{item}</div>
                                                ))}
                                            </div>
                                        ) : <p className="text-[15px] text-[var(--text-faint)] italic">No gaps identified</p>
                                    )}
                            </CardContent>
                        </Card>
                    </div>

                    {/* Current Affairs Evaluation */}
                    {feedback.current_affairs_feedback && (
                        <Card className="border-[var(--card-border)] shadow-sm bg-[var(--bg-secondary)]/30">
                            <CardHeader className="pb-3 border-b border-[var(--card-border)]/50 bg-[var(--bg-secondary)]">
                                <CardTitle className="text-base font-bold text-[var(--text)] flex items-center gap-2">
                                    <RefreshCw className="h-5 w-5 text-amber-600" />
                                    Current affairs evaluation
                                </CardTitle>
                                <CardDescription className="text-[13px] text-[var(--text-muted)] mt-1">Assessment of contemporary relevance and recent developments</CardDescription>
                            </CardHeader>
                            <CardContent className="space-y-6 pt-5 text-[15px] text-[var(--text)]">
                                <div className="flex items-center gap-3">
                                    <span className="font-semibold text-[var(--text-muted)]">Contemporary relevance expected:</span>
                                    <span className={cn(
                                        "px-2.5 py-1 rounded-md text-[11px] font-bold uppercase tracking-wider border",
                                        feedback.current_affairs_feedback.relevance_expected === "yes" ? "bg-emerald-50 dark:bg-emerald-950/20 text-emerald-700 dark:text-emerald-500 border-emerald-200 dark:border-emerald-900/50" :
                                            feedback.current_affairs_feedback.relevance_expected === "partial" ? "bg-amber-50 dark:bg-amber-950/20 text-amber-700 dark:text-amber-500 border-amber-200 dark:border-amber-900/50" :
                                                "bg-[var(--card)] text-[var(--text-muted)] border-[var(--card-border)]"
                                    )}>
                                        {feedback.current_affairs_feedback.relevance_expected}
                                    </span>
                                </div>

                                {feedback.current_affairs_feedback.used_contemporary_references?.length > 0 && (
                                    <div className="bg-[var(--card)] p-4 rounded-xl border border-[var(--card-border)]">
                                        <h4 className="text-[11px] font-bold text-[var(--text)] uppercase tracking-wider mb-2">Contemporary references used</h4>
                                        <ul className="list-disc pl-5 space-y-1.5 text-[var(--text-muted)]">
                                            {feedback.current_affairs_feedback.used_contemporary_references.map((item: string, i: number) => (
                                                <li key={i}>{item}</li>
                                            ))}
                                        </ul>
                                    </div>
                                )}

                                {feedback.current_affairs_feedback.critical_misses?.length > 0 && (
                                    <div>
                                        <h4 className="text-[11px] font-bold text-red-600 dark:text-red-400 uppercase tracking-wider mb-2">Missing developments/reports</h4>
                                        <ul className="list-disc pl-5 space-y-1.5 text-[var(--text-muted)]">
                                            {feedback.current_affairs_feedback.critical_misses.map((item: string, i: number) => (
                                                <li key={i}>{item}</li>
                                            ))}
                                        </ul>
                                    </div>
                                )}

                                {feedback.current_affairs_feedback.examiner_impact && (
                                    <div>
                                        <h4 className="text-[11px] font-bold text-red-600 dark:text-red-400 uppercase tracking-wider mb-2">Examiner impact</h4>
                                        <p className="text-[var(--text-muted)] italic leading-relaxed">"{feedback.current_affairs_feedback.examiner_impact}"</p>
                                    </div>
                                )}
                                {feedback.current_affairs_feedback?.how_to_fix?.length > 0 && (

                                    <div className="bg-amber-50/50 dark:bg-amber-950/20 border border-amber-200/60 dark:border-amber-900/30 p-4 rounded-xl shadow-sm">
                                        <h4 className="text-[11px] font-bold uppercase tracking-wider mb-2 text-amber-800 dark:text-amber-500">How to improve contemporary linkage</h4>
                                        <ul className="list-disc pl-5 space-y-1.5 text-amber-900/80 dark:text-amber-200/70">
                                            {feedback.current_affairs_feedback.how_to_fix.map((item: string, i: number) => (
                                                <li key={i}>{item}</li>
                                            ))}
                                        </ul>
                                    </div>
                                )}
                            </CardContent>
                        </Card>
                    )}

                    {/* Overall Feedback */}
                    <Card className="border-[var(--card-border)] shadow-sm">
                        <CardContent className="p-6 md:p-8 space-y-6 text-[15px] text-[var(--text)]">
                            {feedback.section_wise_assessment && (
                                <div className="space-y-4">
                                    {['introduction', 'body', 'conclusion'].map((s: any) => (
                                        <div key={s}><h4 className="font-bold uppercase tracking-wider text-[11px] text-[var(--text-muted)] mb-1">{s}</h4><p className="text-[var(--text)] leading-relaxed">{feedback.section_wise_assessment[s]}</p></div>
                                    ))}
                                </div>
                            )}
                            <div className="pt-6 border-t border-[var(--card-border)] space-y-4">
                                <p className="text-[var(--text)]"><strong className="font-semibold text-[var(--text-muted)]">Evidence:</strong> {feedback.evidence_feedback}</p>
                                {feedback.visual_feedback && <p className="text-[var(--text)]"><strong className="font-semibold text-[var(--text-muted)]">Visuals:</strong> {feedback.visual_feedback}</p>}
                                {feedback.strategy_tip && (
                                    <div className="bg-amber-50/50 dark:bg-amber-950/20 p-4 rounded-xl border border-amber-200/50 dark:border-amber-900/30 text-amber-900 dark:text-amber-300">
                                        <strong className="font-bold text-amber-700 dark:text-amber-500 uppercase tracking-widest text-[11px] block mb-1">Strategy tip</strong>
                                        <span className="leading-relaxed">{feedback.strategy_tip}</span>
                                    </div>
                                )}
                                <div className="bg-[var(--bg-secondary)] p-4 rounded-xl italic text-[var(--text)] border border-[var(--card-border)]">
                                    <strong className="font-bold text-[var(--text-muted)] uppercase tracking-widest text-[11px] block mb-1 not-italic">Verdict</strong>
                                    {feedback.overall_assessment}
                                </div>
                            </div>
                        </CardContent>
                    </Card>

                    {/* Improved Answer Section */}
                    {!improvedAnswerResult ? (
                        <Card className="border-2 border-dashed border-[var(--card-border)] bg-[var(--bg-secondary)]/50">
                            <CardContent className="p-8 md:p-12 flex flex-col items-center text-center space-y-5 text-[var(--text)]">
                                <div className="bg-[var(--card)] p-4 rounded-full border border-[var(--card-border)] shadow-sm"><FileText className="h-8 w-8 text-amber-600" /></div>
                                <div>
                                    <h3 className="text-xl font-bold mb-2">Generate improved answer</h3>
                                    <p className="text-[15px] text-[var(--text-muted)] max-w-md mx-auto leading-relaxed">Optimize this answer with retrieval-based context and expert refinement based on the evaluation.</p>
                                </div>
                                <Button
                                    onClick={handleGenerateImprovedAnswer}
                                    disabled={['queued', 'processing', 'pending'].includes(improvedAnswerStatus || '')}
                                    className="bg-amber-600 hover:bg-amber-700 text-white font-bold h-12 px-6 shadow-sm transition-all duration-300"
                                >
                                    {['queued', 'processing', 'pending'].includes(improvedAnswerStatus || '') ? (
                                        <><Loader2 className="mr-2 h-5 w-5 animate-spin text-amber-200" /> Generating...</>
                                    ) : <><RefreshCw className="mr-2 h-5 w-5" /> Generate improved answer</>}
                                </Button>
                                {improvedAnswerError && <p className="text-sm font-medium text-red-600 mt-2">{improvedAnswerError}</p>}
                            </CardContent>
                        </Card>
                    ) : (
                        <div className="space-y-6">
                            {improvedAnswerResult.compressed_answer && (
                                <Card className="overflow-hidden border border-[var(--card-border)] shadow-sm">
                                    <button
                                        onClick={() => setShowCompressed(!showCompressed)}
                                        className="w-full flex items-center justify-between p-5 bg-[var(--bg-secondary)] hover:bg-[var(--bg-tertiary)] transition-colors border-b border-[var(--card-border)]/50"
                                    >
                                        <div className="flex items-center gap-3 text-[var(--text)] font-semibold text-base">
                                            <Minimize2 className="h-5 w-5 text-amber-600" /> Compressed model answer
                                        </div>
                                        <ChevronDown className={cn("h-5 w-5 text-[var(--text-muted)] transition-transform", showCompressed && "rotate-180")} />
                                    </button>
                                    {showCompressed && (
                                        <CardContent className="p-6 md:p-8 prose prose-stone dark:prose-invert max-w-none text-[var(--text)] bg-[var(--card)]">
                                            <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents} urlTransform={urlTransform}>
                                                {improvedAnswerResult.compressed_answer}
                                            </ReactMarkdown>
                                        </CardContent>
                                    )}
                                </Card>
                            )}
                            <Card className="overflow-hidden border border-[var(--card-border)] shadow-sm">
                                <button
                                    onClick={() => setShowOriginal(!showOriginal)}
                                    className="w-full flex items-center justify-between p-5 bg-[var(--bg-secondary)] hover:bg-[var(--bg-tertiary)] transition-colors border-b border-[var(--card-border)]/50"
                                >
                                    <div className="flex items-center gap-3 font-semibold text-[var(--text)] text-base">
                                        <FileText className="h-5 w-5 text-amber-600" /> Full model answer
                                    </div>
                                    <ChevronDown className={cn("h-5 w-5 text-[var(--text-muted)] transition-transform", (showOriginal || !improvedAnswerResult.compressed_answer) && "rotate-180")} />
                                </button>
                                {(showOriginal || !improvedAnswerResult.compressed_answer) && (
                                    <CardContent className="p-6 md:p-8 prose prose-stone dark:prose-invert max-w-none text-[var(--text)] bg-[var(--card)]">
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
