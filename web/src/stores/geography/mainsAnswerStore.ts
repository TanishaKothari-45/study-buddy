import { create } from 'zustand';
import { persist, createJSONStorage, devtools } from 'zustand/middleware';
import { MainsAnswerResponse } from '../types';

// Persist result AND form inputs for tab switching
interface MainsAnswerState {
    question: string;
    wordCount: string;
    result: MainsAnswerResponse | null;
    setQuestion: (question: string) => void;
    setWordCount: (wordCount: string) => void;
    setResult: (result: MainsAnswerResponse | null) => void;
    clear: () => void;
}

export const useMainsAnswerStore = create<MainsAnswerState>()(
    devtools(
        persist(
            (set) => ({
                question: '',
                wordCount: '250',
                result: null,
                setQuestion: (question) => set({ question }),
                setWordCount: (wordCount) => set({ wordCount }),
                setResult: (result) => set({ result }),
                clear: () => set({ question: '', wordCount: '250', result: null }),
            }),
            {
                name: 'geography-mains-answer-storage',
                storage: createJSONStorage(() => localStorage),
                version: 2, // Bump version to handle migration
            }
        ),
        { name: 'MainsAnswerStore' }
    )
);
