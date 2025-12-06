'use client';

import { useEffect, useState } from 'react';

interface MapProps {
    src: string;
    alt?: string;
    className?: string;
}

/**
 * Custom Map component to render base64 SVG maps
 * Bypasses ReactMarkdown's data URL restrictions
 */
export function Map({ src, alt, className = '' }: MapProps) {
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        console.log('🗺️ Map component mounted');

        // Validate that this is a base64 SVG
        if (!src || !src.startsWith('data:image/svg+xml;base64,')) {
            console.error('❌ Invalid map data format');
            setError('Invalid map data format');
            return;
        }

        // Decode and validate the SVG
        try {
            const base64Data = src.split(',')[1];
            const svgContent = atob(base64Data);

            if (!svgContent.includes('<svg')) {
                console.error('❌ Invalid SVG content');
                setError('Invalid SVG content');
            } else {
                console.log('✅ Valid SVG detected');
            }
        } catch (e) {
            console.error('❌ Failed to decode map data:', e);
            setError('Failed to decode map data');
        }
    }, [src]);

    if (error) {
        return (
            <div className="my-6 p-4 border border-red-200 rounded-lg bg-red-50 text-red-700">
                <p className="text-sm font-medium">Map Rendering Error</p>
                <p className="text-xs mt-1">{error}</p>
            </div>
        );
    }

    // Render immediately, let the browser handle the image loading
    return (
        <div className="my-6">
            <img
                src={src}
                alt={alt || 'Generated Map'}
                className={`w-full h-auto rounded-lg border border-gray-200 shadow-sm ${className}`}
                style={{ display: 'block', maxWidth: '100%', height: 'auto' }}
                onError={(e) => {
                    console.error('❌ Failed to load map image:', e);
                    setError('Failed to load map image');
                }}
            />
        </div>
    );
}
