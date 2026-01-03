// Shared types across all stores

export interface Source {
    filename: string;
    chapter?: string;
    section?: string;
    page_number?: number;
    content_source?: string;
}

export interface ChatMessage {
    id: string;
    role: "user" | "assistant";
    content: string;
    sources?: Source[];
    timestamp: string; // Changed from Date to string for localStorage compatibility
}

export interface MockTestQuestion {
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

export interface MockTestResponse {
    questions: MockTestQuestion[];
    total_marks: number;
    time_allowed: string;
    instructions: string[];
}

export interface MainsAnswerResponse {
    question: string;
    answer: string;
    compressed_answer: string | null;
    sources: Source[];
    word_count_actual: number;
    word_count_compressed: number | null;
}

export type JobStatus = 'idle' | 'pending' | 'processing' | 'completed' | 'failed' | 'queued';

export interface ExaminerExpectationBlueprint {
    key_demands_of_the_question: string[];
    ideal_logical_structure: {
        introduction: string;
        body: string;
        conclusion: string;
    };
    non_negotiables: string[];
}

export interface SectionWiseAssessment {
    introduction: string;
    body: string;
    conclusion: string;
}

export interface DirectiveAlignment {
    directive_identified: string;
    alignment_assessment: string;
    issues_if_any: string[];
    how_to_improve: string;
}

export interface MarginComment {
    anchor_text: string;
    comment: string;
    comment_type: "strength" | "weakness" | "omission" | "directive_misalignment" | "evidence_gap" | "structure_issue" | "visual_gap";
    severity: "low" | "medium" | "high";
    suggested_fix?: string;
}

export interface CriticalGapAndRemedy {
    gap: string;
    remedy: string;
}

export interface Feedback {
    paper_and_subject_identification?: {
        gs_paper: string;
        primary_domain: string;
        secondary_domain?: string;
    };
    examiner_expectation_blueprint?: ExaminerExpectationBlueprint;
    strengths: string[];
    critical_gaps_and_remedies?: CriticalGapAndRemedy[];
    section_wise_assessment?: SectionWiseAssessment;
    directive_alignment?: DirectiveAlignment;
    evidence_feedback: string;
    visual_feedback?: string;
    strategy_tip?: string;
    overall_assessment: string;
    margin_comments?: MarginComment[];
    // Legacy fields for backward compatibility
    missing_elements?: string[];
    improvements_needed?: string[];
    examiner_expectation_gap?: string;
    structure_feedback?: string;
}

export interface BatchAnswerResult {
    answer_id: string;
    question_number: number;
    status: "completed" | "failed" | "fatal_error" | "processing";
    evaluation: EvaluationFeedbackResult | null;
    error: string | null;
    marks: number;
    word_count: number;
}

export interface BatchData {
    job_id: string;
    user_id: string;
    pdf_path: string;
    total_answers: number;
    completed_answers: number;
    failed_answers: number;
    answers: BatchAnswerResult[];
}

// Feedback-only result from evaluation
export interface EvaluationFeedbackResult {
    question: string;
    student_answer: string;
    feedback: Feedback;
    word_count: number;
    success: boolean;
}

// Improved answer result (separate from evaluation)
export interface ImprovedAnswerResult {
    improved_answer: string;
    compressed_answer?: string | null;
    sources: Source[];
    word_count_actual: number;
    word_count_compressed?: number | null;
    success: boolean;
}

// Legacy EvaluationResult (for backward compatibility)
export interface EvaluationResult {
    question: string;
    student_answer: string;
    improved_answer?: string;  // Optional now (may not be present)
    compressed_answer?: string | null;
    feedback: Feedback;
    sources?: any[];
    current_affairs_count?: number;
    word_count_actual?: number;
    word_count_compressed?: number | null;
    word_count?: number;  // Added for new format
    marks?: number;  // Added for extracted marks (10 or 15)
    paper_and_subject_identification?: {
        gs_paper: string;
        primary_domain: string;
        secondary_domain?: string;
    };
    success?: boolean;
}
