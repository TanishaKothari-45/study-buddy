import { create } from 'zustand';
import { persist, createJSONStorage, devtools } from 'zustand/middleware';
import { EvaluationResult, JobStatus } from '../types';

interface EvaluateAnswerState {
    // Form State
    question: string;
    setQuestion: (q: string) => void;

    // Job State
    jobId: string | null;
    jobStatus: JobStatus;
    result: EvaluationResult | null;
    error: string | null;

    setJobId: (id: string | null) => void;
    setJobStatus: (status: JobStatus) => void;
    setResult: (result: EvaluationResult | null) => void;
    setError: (error: string | null) => void;

    reset: () => void;
}

export const useEvaluateAnswerStore = create<EvaluateAnswerState>()(
    devtools(
        persist(
            (set) => ({
                question: '',
                setQuestion: (question) => set({ question }),

                jobId: null,
                jobStatus: 'idle',
                result: null,
                error: null,

                setJobId: (jobId) => set({ jobId }),
                setJobStatus: (jobStatus) => set({ jobStatus }),
                setResult: (result) => set({ result, jobStatus: 'completed' }),
                setError: (error) => set({ error, jobStatus: 'failed' }),

                reset: () => set({
                    question: '',
                    jobId: null,
                    jobStatus: 'idle',
                    result: null,
                    error: null
                }),
            }),
            {
                name: 'geography-evaluate-answer-storage',
                storage: createJSONStorage(() => localStorage),
                version: 1,
                partialize: (state) => ({
                    // Persist everything needed to resume/show result
                    question: state.question,
                    jobId: state.jobId,
                    jobStatus: state.jobStatus,
                    result: state.result
                }),
            }
        ),
        { name: 'EvaluateAnswerStore' }
    )
);
