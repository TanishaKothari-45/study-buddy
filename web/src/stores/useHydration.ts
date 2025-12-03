import { useEffect, useState } from 'react';

/**
 * Hook to prevent hydration mismatches with Zustand persist
 * Returns false during SSR/initial render, true after hydration
 * 
 * Usage:
 * const hasHydrated = useHydration();
 * if (!hasHydrated) return <LoadingSpinner />;
 */
export function useHydration() {
    const [hasHydrated, setHasHydrated] = useState(false);

    useEffect(() => {
        setHasHydrated(true);
    }, []);

    return hasHydrated;
}
