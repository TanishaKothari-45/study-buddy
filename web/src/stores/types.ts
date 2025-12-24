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

export interface Feedback {
    examiner_expectation_blueprint?: ExaminerExpectationBlueprint;
    strengths: string[];
    missing_elements: string[];
    improvements_needed: string[];
    section_wise_assessment?: SectionWiseAssessment;
    directive_alignment?: DirectiveAlignment;
    evidence_feedback: string;
    visual_feedback?: string;
    examiner_expectation_gap?: string;
    strategy_tip?: string;
    overall_assessment: string;
    // Legacy fields for backward compatibility
    structure_feedback?: string;
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
    success?: boolean;
}
