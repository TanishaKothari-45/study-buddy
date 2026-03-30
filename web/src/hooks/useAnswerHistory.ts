/**
 * F4: useAnswerHistory — extracted from mains-answer/page.tsx god component
 *
 * Manages history fetch, debounced search, and load-more pagination.
 * Encapsulates all 5 history-related useState + 1 useEffect calls.
 */
import { useEffect, useRef } from 'react';
import { useMainsAnswerStore } from '@/stores';

const HISTORY_DEBOUNCE_MS = 300;

export function useAnswerHistory() {
    const {
        history,
        isLoadingHistory,
        historyHasMore,
        historySearch,
        historyTotal,
        setHistorySearch,
        fetchHistory,
        clearHistory,
    } = useMainsAnswerStore();

    const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

    // Debounce search → auto-fetch on change
    useEffect(() => {
        if (debounceRef.current) clearTimeout(debounceRef.current);
        debounceRef.current = setTimeout(() => {
            fetchHistory({ reset: true });
        }, HISTORY_DEBOUNCE_MS);

        return () => {
            if (debounceRef.current) clearTimeout(debounceRef.current);
        };
    }, [historySearch, fetchHistory]);

    function loadMore() {
        if (!isLoadingHistory && historyHasMore) {
            fetchHistory({ reset: false });
        }
    }

    return {
        history,
        isLoadingHistory,
        historyHasMore,
        historySearch,
        historyTotal,
        setHistorySearch,
        clearHistory,
        loadMore,
        refresh: () => fetchHistory({ reset: true }),
    };
}
