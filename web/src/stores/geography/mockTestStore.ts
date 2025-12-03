import { create } from 'zustand';
import { persist, createJSONStorage, devtools } from 'zustand/middleware';
import { MockTestResponse, JobStatus } from '../types';

// Only persist: test data, answers, job info for resuming
interface MockTestState {
    // Test results (persisted)
    testData: MockTestResponse | null;
    userAnswers: Record<number, string>;
    submitted: boolean;
    score: number;

    // Job state (for resuming if navigated away during generation)
    jobId: string | null;
    jobStatus: JobStatus;

    // Actions
    setTestData: (data: MockTestResponse | null) => void;
    setUserAnswers: (answers: Record<number, string>) => void;
    updateUserAnswer: (questionIndex: number, option: string) => void;
    setSubmitted: (submitted: boolean) => void;
    setScore: (score: number) => void;
    setJobId: (jobId: string | null) => void;
    setJobStatus: (status: JobStatus) => void;
    submitTest: () => void;
    resetTest: () => void;
}

export const useMockTestStore = create<MockTestState>()(
    devtools(
        persist(
            (set, get) => ({
                testData: null,
                userAnswers: {},
                submitted: false,
                score: 0,
                jobId: null,
                jobStatus: 'idle',

                setTestData: (data) => set({ testData: data }),
                setUserAnswers: (answers) => set({ userAnswers: answers }),
                updateUserAnswer: (questionIndex, option) => {
                    const { submitted, userAnswers } = get();
                    if (submitted) return;
                    set({ userAnswers: { ...userAnswers, [questionIndex]: option } });
                },
                setSubmitted: (submitted) => set({ submitted }),
                setScore: (score) => set({ score }),
                setJobId: (jobId) => set({ jobId }),
                setJobStatus: (status) => set({ jobStatus: status }),

                submitTest: () => {
                    const { testData, userAnswers } = get();
                    if (!testData) return;

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

                    set({
                        score: parseFloat(calculatedScore.toFixed(2)),
                        submitted: true,
                    });
                },

                resetTest: () => set({
                    testData: null,
                    userAnswers: {},
                    submitted: false,
                    score: 0,
                    jobId: null,
                    jobStatus: 'idle',
                }),
            }),
            {
                name: 'geography-mock-test-storage',
                storage: createJSONStorage(() => localStorage),
                version: 1,
                // Only persist what's necessary
                partialize: (state) => ({
                    testData: state.testData,
                    userAnswers: state.userAnswers,
                    submitted: state.submitted,
                    score: state.score,
                    jobId: state.jobId,
                    jobStatus: state.jobStatus,
                }),
            }
        ),
        { name: 'MockTestStore' }
    )
);
