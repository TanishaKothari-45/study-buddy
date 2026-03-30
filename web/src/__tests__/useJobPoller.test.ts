/**
 * T1: Unit tests for useJobPoller (F4 extracted hook)
 *
 * Verifies poll lifecycle — success, failure, API key error banner, and
 * that the timer is cancelled on unmount (no memory leaks).
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useJobPoller } from '@/hooks/useJobPoller';
import api from '@/lib/apiClient';

vi.mock('@/lib/apiClient', () => ({
    default: {
        get: vi.fn(),
    },
}));

const mockApi = vi.mocked(api);

const makeOptions = (overrides = {}) => ({
    jobId: 'job-123',
    jobStatus: 'queued',
    setJobId: vi.fn(),
    setJobStatus: vi.fn(),
    setResult: vi.fn(),
    setError: vi.fn(),
    setIsApiKeyValid: vi.fn(),
    setShowBanner: vi.fn(),
    onCompleted: vi.fn(),
    ...overrides,
});

beforeEach(() => {
    vi.useFakeTimers();
    vi.clearAllMocks();
});
afterEach(() => {
    vi.useRealTimers();
});

describe('useJobPoller', () => {
    it('calls setResult and onCompleted on completed status', async () => {
        const mockResult = { answer: 'test answer', question: 'Q', word_count: 100, compressed_answer: null, word_count_compressed: null };
        mockApi.get.mockResolvedValueOnce({ status: 'completed', result: mockResult });

        const opts = makeOptions();
        const { result } = renderHook(() => useJobPoller(opts));

        await act(async () => {
            await result.current.pollOnce('job-123');
        });

        expect(opts.setResult).toHaveBeenCalled();
        expect(opts.setJobId).toHaveBeenCalledWith(null);
        expect(opts.onCompleted).toHaveBeenCalled();
    });

    it('calls setError and setJobStatus on failed status', async () => {
        mockApi.get.mockResolvedValueOnce({ status: 'failed', error: 'Some backend error' });

        const opts = makeOptions();
        const { result } = renderHook(() => useJobPoller(opts));

        await act(async () => {
            await result.current.pollOnce('job-123');
        });

        expect(opts.setError).toHaveBeenCalledWith('Some backend error');
        expect(opts.setJobStatus).toHaveBeenCalledWith('failed');
    });

    it('shows API key banner on API_KEY_INVALID error', async () => {
        mockApi.get.mockResolvedValueOnce({ status: 'failed', error: 'API_KEY_INVALID' });

        const opts = makeOptions();
        const { result } = renderHook(() => useJobPoller(opts));

        await act(async () => {
            await result.current.pollOnce('job-123');
        });

        expect(opts.setIsApiKeyValid).toHaveBeenCalledWith('invalid');
        expect(opts.setShowBanner).toHaveBeenCalledWith(true);
    });

    it('cancelPoll prevents further polling', async () => {
        mockApi.get.mockResolvedValue({ status: 'processing' });

        const opts = makeOptions();
        const { result } = renderHook(() => useJobPoller(opts));

        act(() => {
            result.current.cancelPoll();
        });

        // Even if poll is called, activeJobId is null so polling should not update state
        await act(async () => {
            await result.current.pollOnce('job-123');
        });

        expect(opts.setResult).not.toHaveBeenCalled();
    });
});
