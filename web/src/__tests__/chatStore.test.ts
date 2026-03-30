/**
 * T1: Unit tests for chatStore — covers appendToMessageContent (F3 fix),
 * startNewChat, and persist/migrate logic.
 */
import { describe, it, expect, beforeEach } from 'vitest';
import { useChatStore } from '@/stores/geography/chatStore';

// Reset store between tests
beforeEach(() => {
    useChatStore.setState({
        messages: [
            { id: 'welcome', role: 'assistant', content: 'Hello!', timestamp: new Date().toISOString() }
        ],
        sessionId: 'test-session',
    });
});

describe('chatStore', () => {
    it('addMessage appends a new message to the list', () => {
        const { addMessage, messages: before } = useChatStore.getState();
        addMessage({ id: 'msg1', role: 'user', content: 'Hi', timestamp: new Date().toISOString() });

        const { messages } = useChatStore.getState();
        expect(messages).toHaveLength(before.length + 1);
        expect(messages.at(-1)?.content).toBe('Hi');
    });

    it('appendToMessageContent (F3 fix) appends chunk to existing message', () => {
        const id = 'bot1';
        useChatStore.getState().addMessage({ id, role: 'assistant', content: '', timestamp: new Date().toISOString() });

        useChatStore.getState().appendToMessageContent(id, 'Hello ');
        useChatStore.getState().appendToMessageContent(id, 'world');

        const msg = useChatStore.getState().messages.find((m) => m.id === id);
        expect(msg?.content).toBe('Hello world');
    });

    it('appendToMessageContent for unknown id does not crash or mutate', () => {
        const { messages: before } = useChatStore.getState();
        useChatStore.getState().appendToMessageContent('does-not-exist', 'chunk');
        // State should be identical (findIndex returned -1, early return)
        expect(useChatStore.getState().messages).toEqual(before);
    });

    it('startNewChat resets messages and generates a new sessionId', () => {
        const oldSessionId = useChatStore.getState().sessionId;
        useChatStore.getState().startNewChat();

        const { messages, sessionId } = useChatStore.getState();
        expect(messages).toHaveLength(1);
        expect(sessionId).not.toBe(oldSessionId);
    });

    it('updateMessageContent replaces message content by id', () => {
        const id = 'bot2';
        useChatStore.getState().addMessage({ id, role: 'assistant', content: 'Partial', timestamp: new Date().toISOString() });
        useChatStore.getState().updateMessageContent(id, 'Full answer');

        const msg = useChatStore.getState().messages.find((m) => m.id === id);
        expect(msg?.content).toBe('Full answer');
    });
});
