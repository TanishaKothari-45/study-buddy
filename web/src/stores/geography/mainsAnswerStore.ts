import { create } from 'zustand';
import { persist, createJSONStorage, devtools } from 'zustand/middleware';
import { MainsAnswerResponse } from '../types';
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
    result: MainsAnswerResponse | null;
    history: HistoryItem[];
    isLoadingHistory: boolean;
    historyHasMore: boolean;
    historySearch: string;
    historyTotal: number;
    setQuestion: (question: string) => void;
    setWordCount: (wordCount: string) => void;
    setResult: (result: MainsAnswerResponse | null) => void;
    setHistorySearch: (term: string) => void;
    fetchHistory: (opts?: { reset?: boolean }) => Promise<void>;
    clear: () => void;
}

export const useMainsAnswerStore = create<MainsAnswerState>()(
    devtools(
        persist(
            (set, get) => ({
                question: '',
                wordCount: '250',
                result: null,
                history: [],
                isLoadingHistory: false,
                historyHasMore: false,
                historySearch: "",
                historyTotal: 0,
                setQuestion: (question) => set({ question }),
                setWordCount: (wordCount) => set({ wordCount }),
                setResult: (result) => set({ result }),
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
                clear: () => set({ question: '', wordCount: '250', result: null }),
            }),
            {
                name: 'geography-mains-answer-storage',
                storage: createJSONStorage(() => localStorage),
                version: 5, // Bump version
                partialize: (state) => ({
                    // Persist only lightweight form fields; avoid persisting answers to keep storage small
                    question: state.question,
                    wordCount: state.wordCount
                }),
            }
        ),
        { name: 'MainsAnswerStore' }
    )
);
