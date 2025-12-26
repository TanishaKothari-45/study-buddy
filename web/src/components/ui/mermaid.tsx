'use client';

import { useEffect, useRef, useState } from 'react';
import mermaid from 'mermaid';
import { Map } from './map';
import { ZoomIn, ZoomOut, RotateCcw } from 'lucide-react';

interface MermaidProps {
    chart: string;
    className?: string;
}

export function Mermaid({ chart, className = '' }: MermaidProps) {
    const ref = useRef<HTMLDivElement>(null);
    const containerRef = useRef<HTMLDivElement>(null);
    const [zoom, setZoom] = useState(1.4); // Start at 140% for better readability
    const [isPanning, setIsPanning] = useState(false);
    const [panStart, setPanStart] = useState({ x: 0, y: 0 });
    const [panOffset, setPanOffset] = useState({ x: 0, y: 0 });

    const handleZoomIn = () => {
        setZoom(prev => {
            const newZoom = Math.min(prev + 0.25, 3);
            // Scroll to top when zooming to ensure top is visible
            setTimeout(() => {
                if (containerRef.current) {
                    containerRef.current.scrollTop = 0;
                    containerRef.current.scrollLeft = 0;
                }
            }, 50);
            return newZoom;
        });
    };
    const handleZoomOut = () => {
        setZoom(prev => {
            const newZoom = Math.max(prev - 0.25, 0.5);
            // Scroll to top when zooming to ensure top is visible
            setTimeout(() => {
                if (containerRef.current) {
                    containerRef.current.scrollTop = 0;
                    containerRef.current.scrollLeft = 0;
                }
            }, 50);
            return newZoom;
        });
    };
    const handleReset = () => {
        setZoom(1.4); // Reset to default 140%
        setPanOffset({ x: 0, y: 0 });
        // Scroll to top when resetting
        if (containerRef.current) {
            containerRef.current.scrollTop = 0;
            containerRef.current.scrollLeft = 0;
        }
    };

    const handleMouseDown = (e: React.MouseEvent) => {
        if (zoom > 1) {
            setIsPanning(true);
            setPanStart({ x: e.clientX - panOffset.x, y: e.clientY - panOffset.y });
        }
    };

    const handleMouseMove = (e: React.MouseEvent) => {
        if (isPanning && zoom > 1) {
            setPanOffset({
                x: e.clientX - panStart.x,
                y: e.clientY - panStart.y
            });
        }
    };

    const handleMouseUp = () => setIsPanning(false);

    useEffect(() => {
        // Initialize mermaid with improved configuration for readability
        mermaid.initialize({
            startOnLoad: false,
            theme: 'base',
            themeVariables: {
                primaryColor: '#e5e7eb',
                primaryTextColor: '#111827',
                primaryBorderColor: '#4b5563',
                lineColor: '#374151',
                secondaryColor: '#f3f4f6',
                tertiaryColor: '#ffffff',
                fontFamily: 'system-ui, -apple-system, sans-serif',
                fontSize: '18px', // Larger base font
                // Node styling
                nodeBorder: '#4b5563',
                mainBkg: '#f3f4f6',
                nodeTextColor: '#111827',
            },
            securityLevel: 'loose',
            flowchart: {
                htmlLabels: true,
                curve: 'basis',
                padding: 25, // More padding
                nodeSpacing: 80, // More horizontal spacing
                rankSpacing: 70, // More vertical spacing
                useMaxWidth: false,
                defaultRenderer: 'dagre-wrapper',
                wrappingWidth: 180,
            },
            mindmap: {
                padding: 20,
                useMaxWidth: false,
            },
        });

        // Render the diagram
        if (ref.current) {
            try {
                const id = `mermaid-${Math.random().toString(36).substr(2, 9)}`;

                mermaid.render(id, chart).then(({ svg }) => {
                    if (ref.current) {
                        ref.current.innerHTML = svg;
                        const svgElement = ref.current.querySelector('svg');
                        if (svgElement) {
                            // Remove fixed dimensions to allow natural sizing
                            svgElement.removeAttribute('width');
                            svgElement.removeAttribute('height');
                            svgElement.style.maxWidth = 'none';
                            svgElement.style.width = 'auto';
                            svgElement.style.height = 'auto';
                            svgElement.style.minWidth = '300px';
                            svgElement.style.overflow = 'visible';

                            // Increase font size on all text elements for better readability
                            const textElements = svgElement.querySelectorAll('text, .nodeLabel, .edgeLabel, tspan');
                            textElements.forEach((el) => {
                                (el as HTMLElement).style.fontSize = '16px';
                                (el as HTMLElement).style.fontWeight = '600';
                                (el as HTMLElement).style.letterSpacing = '0.01em';
                            });

                            // Remove nested/duplicate small rectangles
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

                            // Fix text overflow in foreignObjects
                            const foreignObjects = svgElement.querySelectorAll('foreignObject');
                            foreignObjects.forEach((fo) => {
                                const innerDiv = fo.querySelector('div');
                                if (!innerDiv) return;

                                const textContent = innerDiv.textContent || '';
                                const estimatedTextWidth = textContent.length * 10;
                                const requiredWidth = Math.max(estimatedTextWidth + 40, 120);
                                const currentFOWidth = parseFloat(fo.getAttribute('width') || '0');
                                const newWidth = Math.max(currentFOWidth * 1.5, requiredWidth);

                                fo.setAttribute('width', newWidth.toString());
                                innerDiv.style.width = '100%';
                                innerDiv.style.textAlign = 'center';
                                innerDiv.style.whiteSpace = 'nowrap';
                                innerDiv.style.overflow = 'visible';
                                innerDiv.style.fontSize = '16px';
                                innerDiv.style.fontWeight = '600';
                                innerDiv.style.padding = '6px 12px';
                                innerDiv.style.color = '#111827';
                                innerDiv.style.letterSpacing = '0.01em';

                                // Update corresponding rectangle
                                const parent = fo.parentElement;
                                if (parent) {
                                    const rect = parent.querySelector('rect');
                                    if (rect) {
                                        const currentRectWidth = parseFloat(rect.getAttribute('width') || '0');
                                        const currentX = parseFloat(rect.getAttribute('x') || '0');
                                        const rectNewWidth = Math.max(currentRectWidth, newWidth);
                                        const widthDiff = rectNewWidth - currentRectWidth;
                                        rect.setAttribute('width', rectNewWidth.toString());
                                        rect.setAttribute('x', (currentX - widthDiff / 2).toString());
                                    }
                                }
                            });

                            // Adjust viewBox with comfortable padding
                            const bbox = svgElement.getBBox();
                            const padding = 30;
                            svgElement.setAttribute('viewBox',
                                `${bbox.x - padding} ${bbox.y - padding} ${bbox.width + padding * 2} ${bbox.height + padding * 2}`
                            );
                            
                            // Scroll container to top after rendering to ensure top is visible
                            if (containerRef.current) {
                                // Use setTimeout to ensure DOM is fully updated
                                setTimeout(() => {
                                    if (containerRef.current) {
                                        containerRef.current.scrollTop = 0;
                                        containerRef.current.scrollLeft = 0;
                                    }
                                }, 100);
                            }
                        }
                    }
                }).catch((error) => {
                    console.error('Mermaid rendering error:', error);
                    if (ref.current) {
                        ref.current.innerHTML = `<div class="text-red-500 text-sm p-4 border border-red-200 rounded bg-red-50">Diagram rendering error: ${error.message || 'Unknown error'}</div>`;
                    }
                });
            } catch (error) {
                console.error('Mermaid error:', error);
            }
        }
    }, [chart]);

    return (
        <div className={`mermaid-wrapper ${className}`}>
            {/* Zoom Controls */}
            <div className="mermaid-controls">
                <button
                    onClick={handleZoomOut}
                    className="mermaid-control-btn"
                    title="Zoom Out"
                    aria-label="Zoom out"
                >
                    <ZoomOut className="w-4 h-4" />
                </button>
                <span className="mermaid-zoom-level">{Math.round(zoom * 100)}%</span>
                <button
                    onClick={handleZoomIn}
                    className="mermaid-control-btn"
                    title="Zoom In"
                    aria-label="Zoom in"
                >
                    <ZoomIn className="w-4 h-4" />
                </button>
                <button
                    onClick={handleReset}
                    className="mermaid-control-btn"
                    title="Reset View"
                    aria-label="Reset zoom and pan"
                >
                    <RotateCcw className="w-4 h-4" />
                </button>
            </div>

            {/* Diagram Container */}
            <div
                ref={containerRef}
                className="mermaid-container"
                onMouseDown={handleMouseDown}
                onMouseMove={handleMouseMove}
                onMouseUp={handleMouseUp}
                onMouseLeave={handleMouseUp}
                style={{
                    cursor: zoom > 1 ? (isPanning ? 'grabbing' : 'grab') : 'default'
                }}
            >
                <div
                    ref={ref}
                    className="mermaid-diagram"
                    style={{
                        transform: `scale(${zoom}) translate(${panOffset.x / zoom}px, ${panOffset.y / zoom}px)`,
                        transformOrigin: 'top center',
                    }}
                />
            </div>
        </div>
    );
}

// Custom markdown components for ReactMarkdown
export const markdownComponents = {
    p({ children, ...props }: any) {
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
    code({ inline, className, children, ...props }: any) {
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
    img({ src, alt, ...props }: any) {
        // Handle base64 SVG maps
        if (src && src.startsWith('data:image/svg+xml;base64,')) {
            return <Map src={src} alt={alt} />;
        }

        if (!src) return null;

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

// URL transform function to allow data URLs
export const urlTransform = (url: string) => {
    if (url.startsWith('data:')) return url;
    if (url.startsWith('http:') || url.startsWith('https:')) return url;
    if (url.startsWith('/')) return url;
    if (url.startsWith('#')) return url;
    return url;
};
