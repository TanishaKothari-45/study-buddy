import { create } from 'zustand';
import { persist, createJSONStorage, devtools } from 'zustand/middleware';
import { MainsAnswerResponse } from '../types';

// Only persist the result - form state stays local in component
interface MainsAnswerState {
    result: MainsAnswerResponse | null;
    setResult: (result: MainsAnswerResponse | null) => void;
    clear: () => void;
}

export const useMainsAnswerStore = create<MainsAnswerState>()(
    devtools(
        persist(
            (set) => ({
                result: null,
                setResult: (result) => set({ result }),
                clear: () => set({ result: null }),
            }),
            {
                name: 'geography-mains-answer-storage',
                storage: createJSONStorage(() => localStorage),
                version: 1,
            }
        ),
        { name: 'MainsAnswerStore' }
    )
);
