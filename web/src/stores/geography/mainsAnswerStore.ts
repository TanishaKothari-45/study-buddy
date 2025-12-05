import { create } from 'zustand';
import { persist, createJSONStorage, devtools } from 'zustand/middleware';
import { MainsAnswerResponse } from '../types';

// History item for previous Q&As
interface HistoryItem {
    id: string;
    question: string;
    answer: string;
    compressed_answer: string | null;
    word_count_actual: number;
    word_count_compressed: number | null;
    timestamp: string;
}

// Persist result AND form inputs for tab switching
interface MainsAnswerState {
    question: string;
    wordCount: string;
    result: MainsAnswerResponse | null;
    history: HistoryItem[];
    setQuestion: (question: string) => void;
    setWordCount: (wordCount: string) => void;
    setResult: (result: MainsAnswerResponse | null) => void;
    addToHistory: (result: MainsAnswerResponse) => void;
    clearHistory: () => void;
    clear: () => void;
}

const MAX_HISTORY = 10;

export const useMainsAnswerStore = create<MainsAnswerState>()(
    devtools(
        persist(
            (set, get) => ({
                question: '',
                wordCount: '250',
                result: null,
                history: [],
                setQuestion: (question) => set({ question }),
                setWordCount: (wordCount) => set({ wordCount }),
                setResult: (result) => set({ result }),
                addToHistory: (result) => {
                    const newItem: HistoryItem = {
                        id: Date.now().toString(),
                        question: result.question,
                        answer: result.answer,
                        compressed_answer: result.compressed_answer,
                        word_count_actual: result.word_count_actual,
                        word_count_compressed: result.word_count_compressed,
                        timestamp: new Date().toISOString(),
                    };
                    const currentHistory = get().history;
                    // Add to front, keep max 10
                    const updatedHistory = [newItem, ...currentHistory].slice(0, MAX_HISTORY);
                    set({ history: updatedHistory });
                },
                clearHistory: () => set({ history: [] }),
                clear: () => set({ question: '', wordCount: '250', result: null }),
            }),
            {
                name: 'geography-mains-answer-storage',
                storage: createJSONStorage(() => localStorage),
                version: 3, // Bump version for history migration
            }
        ),
        { name: 'MainsAnswerStore' }
    )
);
