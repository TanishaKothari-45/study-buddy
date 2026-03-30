/**
 * F4: useJobPoller — extracted from mains-answer/page.tsx god component
 *
 * Manages the async-job polling loop with:
 * - Cleanup on unmount (no memory leak)
 * - Named constants for intervals (C2)
 * - Correct ref-based staleness guard
 */
import { useRef, useEffect } from 'react';
import api from '@/lib/apiClient';
import { POLL_INTERVAL_MS, POLL_RETRY_INTERVAL_MS } from '@/lib/constants';
import type { MainsAnswerResponse } from '@/stores/types';

interface UseJobPollerOptions {
    jobId: string | null;
    jobStatus: string;
    setJobId: (id: string | null) => void;
    setJobStatus: (status: string) => void;
    setResult: (result: MainsAnswerResponse) => void;
    setError: (error: string | null) => void;
    setIsApiKeyValid?: (state: 'valid' | 'invalid' | 'unknown') => void;
    setShowBanner?: (show: boolean) => void;
    onCompleted?: () => void;
}

export function useJobPoller({
    jobId,
    jobStatus,
    setJobId,
    setJobStatus,
    setResult,
    setError,
    setIsApiKeyValid,
    setShowBanner,
    onCompleted,
}: UseJobPollerOptions) {
    const activeJobId = useRef<string | null>(null);
    const pollTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

    // Keep ref in sync with store so async callbacks can check staleness
    useEffect(() => {
        activeJobId.current = jobId;
    }, [jobId]);

    // On mount: resume polling if a job was in progress before navigation
    useEffect(() => {
        if (jobId && (jobStatus === 'pending' || jobStatus === 'processing' || jobStatus === 'queued')) {
            pollOnce(jobId);
        }
        return () => {
            if (pollTimerRef.current) clearTimeout(pollTimerRef.current);
        };
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);

    async function pollOnce(id: string) {
        if (activeJobId.current !== id) return;

        try {
            const data = await api.get<{
                status: string;
                result?: MainsAnswerResponse;
                error?: string;
            }>(`/mains-answer/status/${id}`);

            if (activeJobId.current !== id) return;

            if (data.status === 'completed') {
                if (data.result) {
                    const normalized = {
                        ...data.result,
                        compressed_answer: data.result.compressed_answer ?? null,
                        word_count_compressed: data.result.word_count_compressed ?? null,
                    };
                    if (
                        normalized.compressed_answer &&
                        normalized.answer &&
                        normalized.compressed_answer.trim() === normalized.answer.trim()
                    ) {
                        normalized.compressed_answer = null;
                        normalized.word_count_compressed = null;
                    }
                    setResult(normalized);
                    setJobId(null);
                    onCompleted?.();
                } else {
                    setError('Generation completed but returned no data.');
                    setJobId(null);
                }
            } else if (data.status === 'failed') {
                const cleanedError = data.error || 'Generation failed';
                setError(cleanedError);
                setJobStatus('failed');
                if (
                    cleanedError.toLowerCase().includes('api key') ||
                    cleanedError.includes('API_KEY_INVALID')
                ) {
                    setIsApiKeyValid?.('invalid');
                    setShowBanner?.(true);
                }
            } else {
                if (data.status === 'processing' && jobStatus !== 'processing') {
                    setJobStatus('processing');
                }
                pollTimerRef.current = setTimeout(() => pollOnce(id), POLL_INTERVAL_MS);
            }
        } catch (err) {
            if (activeJobId.current !== id) return;
            console.error('Polling error:', err);
            pollTimerRef.current = setTimeout(() => pollOnce(id), POLL_RETRY_INTERVAL_MS);
        }
    }

    function cancelPoll() {
        if (pollTimerRef.current) clearTimeout(pollTimerRef.current);
        activeJobId.current = null;
    }

    return { pollOnce, cancelPoll, activeJobId };
}
