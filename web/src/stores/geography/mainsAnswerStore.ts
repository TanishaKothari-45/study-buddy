import { create } from 'zustand';
import { persist, createJSONStorage, devtools } from 'zustand/middleware';
import { MainsAnswerResponse, JobStatus } from '../types';
import api from '../../lib/apiClient';

// History item for previous Q&As
interface HistoryItem {
    id: string;
    question: string;
    preview?: string; // Short preview provided by backend
    word_count?: number;
    timestamp: string;
    q_hash?: string;
}

// Persist result AND form inputs for tab switching
interface MainsAnswerState {
    question: string;
    wordCount: string;

    // Async Job handling
    jobId: string | null;
    jobStatus: JobStatus;

    result: MainsAnswerResponse | null;
    error: string | null;

    history: HistoryItem[];
    isLoadingHistory: boolean;
    historyHasMore: boolean;
    historySearch: string;
    historyTotal: number;

    setQuestion: (question: string) => void;
    setWordCount: (wordCount: string) => void;

    setJobId: (id: string | null) => void;
    setJobStatus: (status: JobStatus) => void;

    setResult: (result: MainsAnswerResponse | null) => void;
    setError: (error: string | null) => void;

    setHistorySearch: (term: string) => void;
    fetchHistory: (opts?: { reset?: boolean }) => Promise<void>;
    clear: () => void;
    clearHistory: () => void;
}

export const useMainsAnswerStore = create<MainsAnswerState>()(
    devtools(
        persist(
            (set, get) => ({
                question: '',
                wordCount: '250',

                jobId: null,
                jobStatus: 'idle',

                result: null,
                error: null,

                history: [],
                isLoadingHistory: false,
                historyHasMore: false,
                historySearch: "",
                historyTotal: 0,

                setQuestion: (question) => set({ question }),
                setWordCount: (wordCount) => set({ wordCount }),

                setJobId: (jobId) => set({ jobId }),
                setJobStatus: (jobStatus) => set({ jobStatus }),

                setResult: (result) => set({ result, jobStatus: 'completed' }),
                setError: (error) => set({ error, jobStatus: 'failed' }),

                setHistorySearch: (term) => set({ historySearch: term }),
                fetchHistory: async (opts?: { reset?: boolean }) => {
                    const { reset } = opts || {};
                    set({ isLoadingHistory: true });
                    try {
                        const state = get();
                        const limit = 20;
                        const offset = reset ? 0 : state.history.length;
                        const search = state.historySearch || "";
                        const data = await api.get<{ history: HistoryItem[]; limit: number; offset: number; search: string; total: number; has_more: boolean }>(
                            `/mains-answer/history?limit=${limit}&offset=${offset}&search=${encodeURIComponent(search)}`
                        );
                        const newItems = data.history || [];
                        const merged = reset ? newItems : [...state.history, ...newItems];
                        set({
                            history: merged,
                            historyHasMore: data.has_more ?? (newItems.length === limit),
                            historyTotal: data.total ?? merged.length,
                        });
                    } catch (error) {
                        console.error("Failed to fetch history:", error);
                    } finally {
                        set({ isLoadingHistory: false });
                    }
                },
                clear: () => set({
                    question: '',
                    wordCount: '250',
                    result: null,
                    jobId: null,
                    jobStatus: 'idle',
                    error: null
                }),
                clearHistory: () => set({
                    history: [],
                    historyHasMore: false,
                    historySearch: "",
                    historyTotal: 0,
                    isLoadingHistory: false
                }),
            }),
            {
                name: 'geography-mains-answer-storage',
                storage: createJSONStorage(() => localStorage),
                version: 6, // Bump version
                partialize: (state) => ({
                    // Persist form + job state + result for seamless tab switching
                    question: state.question,
                    wordCount: state.wordCount,
                    jobId: state.jobId,
                    jobStatus: state.jobStatus,
                    result: state.result
                }),
                // Migrate function to handle version transitions
                migrate: (persistedState: any, version: number) => {
                    if (version < 6) {
                        return {
                            question: persistedState?.question || '',
                            wordCount: persistedState?.wordCount || '250',
                            jobId: null,
                            jobStatus: 'idle',
                            result: null
                        };
                    }
                    return persistedState;
                },
            }
        ),
        { name: 'MainsAnswerStore' }
    )
);
