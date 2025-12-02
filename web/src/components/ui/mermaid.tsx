'use client';

import { useEffect, useRef } from 'react';
import mermaid from 'mermaid';
import { Map } from './map';

interface MermaidProps {
    chart: string;
    className?: string;
}

export function Mermaid({ chart, className = '' }: MermaidProps) {
    const ref = useRef<HTMLDivElement>(null);

    useEffect(() => {
        // Initialize mermaid with configuration
        mermaid.initialize({
            startOnLoad: false,
            theme: 'base', // Use base theme for better customization
            themeVariables: {
                primaryColor: '#f3f4f6', // Light grey (gray-100)
                primaryTextColor: '#1f2937', // Dark grey (gray-800)
                primaryBorderColor: '#9ca3af', // Medium grey (gray-400)
                lineColor: '#4b5563', // Darker grey (gray-600)
                secondaryColor: '#f9fafb', // Very light grey (gray-50)
                tertiaryColor: '#ffffff', // White
                fontFamily: 'inherit',
                fontSize: '10px', // Further reduced for compact size
            },
            securityLevel: 'loose',
            flowchart: {
                htmlLabels: true,
                curve: 'basis',
                padding: 8, // Further reduced
                nodeSpacing: 25, // More compact node spacing
                rankSpacing: 25, // More compact rank spacing
                useMaxWidth: true,
            },
            mindmap: {
                padding: 8, // Further reduced
                useMaxWidth: true,
            },
        });

        // Render the diagram
        if (ref.current) {
            try {
                // Generate unique ID for this diagram
                const id = `mermaid-${Math.random().toString(36).substr(2, 9)}`;

                // Render the diagram
                mermaid.render(id, chart).then(({ svg }) => {
                    if (ref.current) {
                        ref.current.innerHTML = svg;
                        const svgElement = ref.current.querySelector('svg');
                        if (svgElement) {
                            svgElement.style.maxWidth = '400px';
                            svgElement.style.height = 'auto';
                            svgElement.style.overflow = 'visible';
                            svgElement.setAttribute('width', '100%');

                            // Remove nested/duplicate rectangles
                            const allRects = svgElement.querySelectorAll('rect');
                            const rectsToRemove: Element[] = [];
                            allRects.forEach((rect) => {
                                const width = parseFloat(rect.getAttribute('width') || '0');
                                const height = parseFloat(rect.getAttribute('height') || '0');
                                if (width < 30 || height < 20) {
                                    rectsToRemove.push(rect);
                                }
                            });
                            rectsToRemove.forEach(rect => rect.remove());

                            // CRITICAL: Fix text overflow by coordinating rect and foreignObject widths
                            const foreignObjects = svgElement.querySelectorAll('foreignObject');
                            foreignObjects.forEach((fo) => {
                                // Get the text content from the div inside foreignObject
                                const innerDiv = fo.querySelector('div');
                                if (!innerDiv) return;

                                const textContent = innerDiv.textContent || '';

                                // Calculate required width based on text length
                                // Use 12px per character to be safe (10px font needs more space)
                                const estimatedTextWidth = textContent.length * 12;
                                const requiredWidth = estimatedTextWidth + 60; // Add more padding

                                const currentFOWidth = parseFloat(fo.getAttribute('width') || '0');

                                // Take the maximum of: current width, calculated width, or 2x current width
                                const newWidth = Math.max(currentFOWidth * 2, requiredWidth);

                                // Update foreignObject width
                                fo.setAttribute('width', newWidth.toString());

                                // Style the inner div
                                innerDiv.style.width = '100%';
                                innerDiv.style.textAlign = 'center';
                                innerDiv.style.whiteSpace = 'nowrap';
                                innerDiv.style.overflow = 'visible';

                                // Find the corresponding rectangle and update its width too
                                let parent = fo.parentElement;
                                if (parent) {
                                    const rect = parent.querySelector('rect');
                                    if (rect) {
                                        const currentRectWidth = parseFloat(rect.getAttribute('width') || '0');
                                        const currentX = parseFloat(rect.getAttribute('x') || '0');

                                        // Make rectangle match the foreignObject width
                                        const rectNewWidth = Math.max(currentRectWidth, newWidth);
                                        const widthDiff = rectNewWidth - currentRectWidth;

                                        rect.setAttribute('width', rectNewWidth.toString());
                                        rect.setAttribute('x', (currentX - widthDiff / 2).toString());
                                    }
                                }
                            });
                            // Trim viewBox to remove excessive whitespace
                            const bbox = svgElement.getBBox();
                            const padding = 15;
                            svgElement.setAttribute('viewBox',
                                `${bbox.x - padding} ${bbox.y - padding} ${bbox.width + padding * 2} ${bbox.height + padding * 2}`
                            );
                            svgElement.removeAttribute('height');
                        }
                    }
                }).catch((error) => {
                    console.error('Mermaid rendering error:', error);
                    if (ref.current) {
                        ref.current.innerHTML = `<div class="text-red-500 text-sm p-4 border border-red-200 rounded bg-red-50">Mermaid rendering error: ${error.message || 'Unknown error'}</div>`;
                    }
                });
            } catch (error) {
                console.error('Mermaid error:', error);
            }
        }
    }, [chart]);

    return (
        <div
            ref={ref}
            className={`mermaid-diagram ${className}`}
        />
    );
}

// Custom markdown components for ReactMarkdown
export const markdownComponents = {
    p({ node, children, ...props }: any) {
        // Check if children contains an image or map (which renders as div)
        // If so, render as div to avoid "div inside p" hydration error
        const hasImage = Array.isArray(children)
            ? children.some((child: any) =>
                child?.type === 'img' ||
                (child?.props && (child.props.src?.startsWith('data:') || child.type?.name === 'Map'))
            )
            : children?.type === 'img' ||
            (children?.props && (children.props.src?.startsWith('data:') || children.type?.name === 'Map'));

        if (hasImage) {
            return <div className="my-4" {...props}>{children}</div>;
        }
        return <p className="mb-4 leading-relaxed" {...props}>{children}</p>;
    },
    code({ node, inline, className, children, ...props }: any) {
        const match = /language-mermaid/.test(className || '');
        const code = String(children).replace(/\n$/, '');

        return !inline && match ? (
            <Mermaid chart={code} />
        ) : (
            <code className={className} {...props}>
                {children}
            </code>
        );
    },
    img({ node, src, alt, ...props }: any) {
        console.log('📸 img handler called:', {
            hasSrc: !!src,
            srcLength: src?.length || 0,
            srcStart: src?.substring(0, 50),
            alt
        });

        // Handle base64 SVG maps (from map generation service)
        // Use custom Map component to bypass ReactMarkdown's data URL restrictions
        if (src && src.startsWith('data:image/svg+xml;base64,')) {
            console.log('✅ Detected base64 SVG map, rendering Map component');
            return <Map src={src} alt={alt} />;
        }

        // Handle regular images - don't render if src is empty
        if (!src) {
            console.log('⚠️ Empty src, returning null');
            return null;
        }

        console.log('📷 Rendering regular image');
        return (
            <img
                src={src}
                alt={alt || ''}
                className="max-w-full h-auto rounded-lg"
                {...props}
            />
        );
    },
};

// URL transform function to allow data URLs (for base64 maps)
export const urlTransform = (url: string) => {
    if (url.startsWith('data:')) return url;
    if (url.startsWith('http:') || url.startsWith('https:')) return url;
    if (url.startsWith('/')) return url;
    if (url.startsWith('#')) return url;
    return url;
};
