import { create } from 'zustand';
import { persist, createJSONStorage, devtools } from 'zustand/middleware';
import { EvaluationResult, ImprovedAnswerResult, JobStatus } from '../types';

interface EvaluateAnswerState {
    // Form State
    question: string;
    setQuestion: (q: string) => void;
    evaluationMode: "single" | "batch";
    setEvaluationMode: (mode: "single" | "batch") => void;

    // Evaluation Job State
    jobId: string | null;
    jobStatus: JobStatus;
    result: EvaluationResult | null;
    error: string | null;

    setJobId: (id: string | null) => void;
    setJobStatus: (status: JobStatus) => void;
    setResult: (result: EvaluationResult | null) => void;
    setError: (error: string | null) => void;

    // Improved Answer Generation State
    improvedAnswerJobId: string | null;
    improvedAnswerStatus: JobStatus;
    improvedAnswerResult: ImprovedAnswerResult | null;
    improvedAnswerError: string | null;

    setImprovedAnswerJobId: (id: string | null) => void;
    setImprovedAnswerStatus: (status: JobStatus) => void;
    setImprovedAnswerResult: (result: ImprovedAnswerResult | null) => void;
    setImprovedAnswerError: (error: string | null) => void;

    generateImprovedAnswer: (question: string, studentAnswer: string | null, feedback: any, wordCount?: number, files?: File[]) => Promise<void>;

    reset: () => void;
    resetImprovedAnswer: () => void;
}

export const useEvaluateAnswerStore = create<EvaluateAnswerState>()(
    devtools(
        persist(
            (set, get) => ({
                question: '',
                setQuestion: (question) => set({ question }),
                evaluationMode: 'single',
                setEvaluationMode: (evaluationMode) => set({ evaluationMode }),

                jobId: null,
                jobStatus: 'idle',
                result: null,
                error: null,

                setJobId: (jobId) => set({ jobId }),
                setJobStatus: (jobStatus) => set({ jobStatus }),
                setResult: (result) => set({ result, jobStatus: 'completed' }),
                setError: (error) => set({ error, jobStatus: 'failed' }),

                // Improved Answer State
                improvedAnswerJobId: null,
                improvedAnswerStatus: 'idle',
                improvedAnswerResult: null,
                improvedAnswerError: null,

                setImprovedAnswerJobId: (jobId) => set({ improvedAnswerJobId: jobId }),
                setImprovedAnswerStatus: (status) => set({ improvedAnswerStatus: status }),
                setImprovedAnswerResult: (result) => set({ improvedAnswerResult: result, improvedAnswerStatus: 'completed' }),
                setImprovedAnswerError: (error) => set({ improvedAnswerError: error, improvedAnswerStatus: 'failed' }),

                generateImprovedAnswer: async (question: string, studentAnswer: string | null, feedback: any, wordCount: number = 250, files?: File[]) => {
                    const state = get();
                    set({ improvedAnswerStatus: 'pending', improvedAnswerError: null });

                    try {
                        // Import API client dynamically
                        const { apiClient } = await import('../../lib/apiClient');

                        // Create FormData
                        const formData = new FormData();
                        formData.append('question', question);
                        formData.append('feedback', JSON.stringify(feedback));
                        formData.append('word_count', wordCount.toString());

                        if (studentAnswer) {
                            formData.append('student_answer', studentAnswer);
                        }

                        if (files && files.length > 0) {
                            files.forEach((file) => {
                                formData.append('files', file);
                            });
                        }

                        // Call API with FormData (bypass JSON.stringify)
                        const response = await apiClient<{ job_id: string; status: string }>(
                            '/evaluate-answer/generate-improved',
                            {
                                method: 'POST',
                                body: formData,
                                // Don't set Content-Type header - browser will set it with boundary for FormData
                            }
                        );

                        set({
                            improvedAnswerJobId: response.job_id,
                            improvedAnswerStatus: 'queued'
                        });
                    } catch (error: any) {
                        console.error('Failed to generate improved answer:', error);
                        set({
                            improvedAnswerError: error.message || 'Failed to generate improved answer',
                            improvedAnswerStatus: 'failed'
                        });
                    }
                },

                reset: () => set({
                    question: '',
                    evaluationMode: 'single',
                    jobId: null,
                    jobStatus: 'idle',
                    result: null,
                    error: null,
                    improvedAnswerJobId: null,
                    improvedAnswerStatus: 'idle',
                    improvedAnswerResult: null,
                    improvedAnswerError: null
                }),

                resetImprovedAnswer: () => set({
                    improvedAnswerJobId: null,
                    improvedAnswerStatus: 'idle',
                    improvedAnswerResult: null,
                    improvedAnswerError: null
                }),
            }),
            {
                name: 'geography-evaluate-answer-storage',
                storage: createJSONStorage(() => localStorage),
                version: 2, // Bump version for new fields
                partialize: (state) => ({
                    // Persist everything needed to resume/show result
                    question: state.question,
                    evaluationMode: state.evaluationMode,
                    jobId: state.jobId,
                    jobStatus: state.jobStatus,
                    result: state.result,
                    improvedAnswerJobId: state.improvedAnswerJobId,
                    improvedAnswerStatus: state.improvedAnswerStatus,
                    improvedAnswerResult: state.improvedAnswerResult
                }),
            }
        ),
        { name: 'EvaluateAnswerStore' }
    )
);
