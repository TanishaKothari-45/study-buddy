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
}

// Persist result AND form inputs for tab switching
interface MainsAnswerState {
    question: string;
    wordCount: string;
    result: MainsAnswerResponse | null;
    history: HistoryItem[];
    isLoadingHistory: boolean;
    setQuestion: (question: string) => void;
    setWordCount: (wordCount: string) => void;
    setResult: (result: MainsAnswerResponse | null) => void;
    fetchHistory: () => Promise<void>;
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
                setQuestion: (question) => set({ question }),
                setWordCount: (wordCount) => set({ wordCount }),
                setResult: (result) => set({ result }),
                fetchHistory: async () => {
                    set({ isLoadingHistory: true });
                    try {
                        const data = await api.get<{ history: HistoryItem[] }>('/mains-answer/history');
                        set({ history: data.history || [] });
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
                    // Persist everything EXCEPT history
                    question: state.question,
                    wordCount: state.wordCount,
                    result: state.result
                }),
            }
        ),
        { name: 'MainsAnswerStore' }
    )
);
