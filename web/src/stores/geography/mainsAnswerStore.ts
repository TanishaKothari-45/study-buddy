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

// Persist form inputs, job tracking, and current result (only one at a time - cleared on "New Answer")
// History is NOT persisted - fetched from Redis/backend via /mains-answer/history
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
                version: 6, // Persist form inputs, job tracking, and current result (only one at a time due to clear())
                partialize: (state) => ({
                    // CRITICAL: Only persist form inputs, job tracking, and current result
                    // History (history array) is EXPLICITLY NOT persisted to prevent localStorage quota issues
                    // History is fetched from Redis/backend via /mains-answer/history endpoint
                    // Only ONE result is stored at a time (cleared on "New Answer" button and on regenerate)
                    // 
                    // NOTE: localStorage has 5-10MB capacity, so a single 20-50KB result is safe.
                    // Quota errors are more likely from:
                    // 1. chatStore persisting 50 messages (each can be large with markdown)
                    // 2. Accumulation of old data before clear() was properly implemented
                    // 3. Other stores (mockTestStore, evaluateAnswerStore) accumulating data
                    question: state.question,
                    wordCount: state.wordCount,
                    jobId: state.jobId,
                    jobStatus: state.jobStatus,
                    result: state.result // Current answer (cleared before each new generation via clear() in handleGenerate)
                    // NOTE: history, historyHasMore, historySearch, historyTotal are NOT persisted
                    // They are in-memory only and fetched from backend when needed
                }),
                // Migrate function to handle version transitions
                migrate: (persistedState: any, version: number) => {
                    if (version < 6) {
                        // Clean migration: explicitly exclude history and other non-persisted fields
                        return {
                            question: persistedState?.question || '',
                            wordCount: persistedState?.wordCount || '250',
                            jobId: persistedState?.jobId || null,
                            jobStatus: persistedState?.jobStatus || 'idle',
                            result: persistedState?.result || null
                            // Explicitly exclude: history, historyHasMore, historySearch, historyTotal
                            // These should never be persisted and will be reset to defaults on load
                        };
                    }
                    // For version 6+, ensure history is not accidentally persisted
                    const cleaned = { ...persistedState };
                    delete cleaned.history;
                    delete cleaned.historyHasMore;
                    delete cleaned.historySearch;
                    delete cleaned.historyTotal;
                    delete cleaned.isLoadingHistory;
                    return cleaned;
                },
            }
        ),
        { name: 'MainsAnswerStore' }
    )
);
