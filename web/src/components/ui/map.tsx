'use client';

import { useEffect, useState } from 'react';

interface MapProps {
    src: string;
    alt?: string;
    className?: string;
}

/**
 * Map component rendering base64 images (PNG preferred).
 * Keep simple to avoid heavy inline SVG parsing.
 */
export function Map({ src, alt, className = '' }: MapProps) {
    if (!src || !src.startsWith('data:image/')) {
        return null;
    }

    return (
        <div className="my-6">
            <img
                src={src}
                alt={alt || 'Generated Map'}
                className={`w-full h-auto rounded-lg border border-gray-200 shadow-sm max-h-[600px] object-contain ${className}`}
                loading="lazy"
            />
        </div>
    );
}
