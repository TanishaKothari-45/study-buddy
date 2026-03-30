import { create } from 'zustand';
import { persist, createJSONStorage, devtools } from 'zustand/middleware';
import { ChatMessage } from '../types';
import { CHAT_STORE_KEY, CHAT_MAX_PERSISTED_MESSAGES } from '@/lib/constants';

// Only persist messages and session - input/loading stays local
interface ChatState {
    messages: ChatMessage[];
    sessionId: string;

    addMessage: (message: ChatMessage) => void;
    updateMessageContent: (id: string, content: string) => void;
    appendToMessageContent: (id: string, content: string) => void;
    setMessageSources: (id: string, sources: ChatMessage['sources']) => void;
    startNewChat: () => void;
}

const generateSessionId = () =>
    `session_${Date.now()}_${Math.random().toString(36).substring(2, 9)}`;

const createWelcomeMessage = (content = "Hello! I'm your Geography Study Buddy. Ask me anything about your study materials, and I'll explain it simply with examples."): ChatMessage => ({
    id: "welcome",
    role: "assistant",
    content,
    timestamp: new Date().toISOString(), // Store as ISO string for persistence
});

export const useChatStore = create<ChatState>()(
    devtools(
        persist(
            (set) => ({
                messages: [createWelcomeMessage()],
                sessionId: generateSessionId(),

                addMessage: (message) => set((state) => ({
                    messages: [...state.messages, message]
                })),

                updateMessageContent: (id, content) => set((state) => ({
                    messages: state.messages.map((msg) =>
                        msg.id === id ? { ...msg, content } : msg
                    ),
                })),

                // F3: O(1) lookup instead of O(n) map — avoids recreating all message objects on every chunk
                appendToMessageContent: (id, chunk) => set((state) => {
                    const idx = state.messages.findIndex((m) => m.id === id);
                    if (idx === -1) return state;
                    const updated = [...state.messages];
                    updated[idx] = { ...updated[idx], content: updated[idx].content + chunk };
                    return { messages: updated };
                }),

                setMessageSources: (id, sources) => set((state) => ({
                    messages: state.messages.map((msg) =>
                        msg.id === id ? { ...msg, sources } : msg
                    ),
                })),

                startNewChat: () => set({
                    messages: [createWelcomeMessage("New chat started! How can I help you now?")],
                    sessionId: generateSessionId(),
                }),
            }),
            {
                name: CHAT_STORE_KEY, // C3: single source of truth
                storage: createJSONStorage(() => localStorage),
                version: 1,
                // C2: use named constant instead of magic number 50
                partialize: (state) => ({
                    messages: state.messages.slice(-CHAT_MAX_PERSISTED_MESSAGES),
                    sessionId: state.sessionId,
                }),
                // Migrate function to handle version transitions
                migrate: (persistedState: any, version: number) => {
                    // For version 1, ensure messages array exists
                    if (!persistedState?.messages || !Array.isArray(persistedState.messages)) {
                        return {
                            messages: [createWelcomeMessage()],
                            sessionId: generateSessionId(),
                        };
                    }
                    return persistedState;
                },
                onRehydrateStorage: () => (state, error) => {
                    if (error) {
                        console.warn('Failed to rehydrate chat store:', error);
                    }
                },
            }
        ),
        { name: 'ChatStore' }
    )
);
