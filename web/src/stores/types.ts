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

export type JobStatus = 'idle' | 'pending' | 'processing' | 'completed' | 'failed';

export interface Feedback {
    strengths: string[];
    missing_elements: string[];
    improvements_needed: string[];
    structure_feedback: string;
    evidence_feedback: string;
    overall_assessment: string;
}

export interface EvaluationResult {
    question: string;
    student_answer: string;
    improved_answer: string;
    feedback: Feedback;
    sources: any[];
    current_affairs_count: number;
}
