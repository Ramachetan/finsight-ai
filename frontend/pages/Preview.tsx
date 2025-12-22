
import React, { useState, useEffect, useCallback, useRef } from 'react';
import { useParams, Link } from 'react-router-dom';
import * as api from '../lib/api';
import { useToast } from '../hooks/useToast';
import { Spinner } from '../components/ui/Spinner';
import { Button } from '../components/ui/Button.tsx';
import SchemaEditorTable from '../components/SchemaEditorTable.tsx';
import { FileMetadata, ParsedChunk, ExtractResponse } from '../types.ts';
import {
    Home, ChevronRight, ZoomIn, ZoomOut, Maximize2, RotateCcw,
    FileText, Table, Download, Layers, Type, Image, Grid3X3,
    ChevronDown, ChevronUp, Eye, EyeOff, Settings
} from 'lucide-react';
import { Document, Page, pdfjs } from 'react-pdf';
import Papa from 'papaparse';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import rehypeRaw from 'rehype-raw';

// Configure PDF.js worker using react-pdf's bundled worker
pdfjs.GlobalWorkerOptions.workerSrc = new URL(
    'react-pdf/node_modules/pdfjs-dist/build/pdf.worker.mjs',
    import.meta.url
).href;

type CsvData = {
    headers: string[];
    rows: string[][];
};

type ActiveView = 'csv' | 'markdown' | 'chunks' | 'schema';

const ChunkTypeIcon: React.FC<{ type?: string; className?: string }> = ({ type, className = '' }) => {
    switch (type) {
        case 'table':
            return <Grid3X3 size={14} className={className} />;
        case 'image':
            return <Image size={14} className={className} />;
        case 'text':
        default:
            return <Type size={14} className={className} />;
    }
};

const ChunkTypeBadge: React.FC<{ type?: string }> = ({ type }) => {
    const getTypeStyles = () => {
        switch (type) {
            case 'table':
                return 'bg-purple-100 text-purple-700 border-purple-200';
            case 'image':
                return 'bg-amber-100 text-amber-700 border-amber-200';
            case 'text':
            default:
                return 'bg-blue-100 text-blue-700 border-blue-200';
        }
    };

    return (
        <span className={`inline-flex items-center gap-1 px-2 py-0.5 text-xs font-medium rounded-full border ${getTypeStyles()}`}>
            <ChunkTypeIcon type={type} />
            {type || 'unknown'}
        </span>
    );
};

const Preview: React.FC = () => {
    const { folderId, filename } = useParams<{ folderId: string; filename: string }>();
    const [pdfUrl, setPdfUrl] = useState<string | null>(null);
    const [csvData, setCsvData] = useState<CsvData | null>(null);
    const [markdownContent, setMarkdownContent] = useState<string | null>(null);
    const [metadata, setMetadata] = useState<FileMetadata | null>(null);
    const [isLoading, setIsLoading] = useState(true);
    const [numPages, setNumPages] = useState<number>(0);
    const [scale, setScale] = useState<number>(1.0);
    const [containerWidth, setContainerWidth] = useState<number>(0);
    const [activeView, setActiveView] = useState<ActiveView>('csv');
    const [selectedChunkId, setSelectedChunkId] = useState<string | null>(null);
    const [expandedChunks, setExpandedChunks] = useState<Set<string>>(new Set());
    const [showBoundingBoxes, setShowBoundingBoxes] = useState(true);
    const [pageDimensions, setPageDimensions] = useState<Map<number, { width: number; height: number }>>(new Map());
    const pdfContainerRef = useRef<HTMLDivElement>(null);
    const pageRefs = useRef<Map<number, HTMLDivElement>>(new Map());
    const { addToast } = useToast();

    const loadData = useCallback(async () => {
        if (!folderId || !filename) return;

        setIsLoading(true);
        try {
            // Fetch PDF
            const pdfBlob = await api.getOriginalFile(folderId, filename);
            const pdfUrl = URL.createObjectURL(pdfBlob);
            setPdfUrl(pdfUrl);

            // Fetch and parse CSV
            try {
                const processedFilename = `${filename}.csv`;
                const csvBlob = await api.downloadResult(folderId, processedFilename);
                const csvText = await csvBlob.text();

                Papa.parse<string[]>(csvText, {
                    complete: (results) => {
                        const [headerRow, ...rows] = results.data;
                        setCsvData({ headers: headerRow, rows });
                    },
                    error: (error: Error) => {
                        console.error('CSV Parse Error:', error);
                    }
                });
            } catch {
                console.warn('CSV not available');
            }

            // Fetch Markdown
            try {
                const markdown = await api.getFileMarkdown(folderId, filename);
                setMarkdownContent(markdown);
            } catch {
                console.warn('Markdown not available');
            }

            // Fetch Metadata with chunks
            try {
                const meta = await api.getFileMetadata(folderId, filename);
                setMetadata(meta);
            } catch {
                console.warn('Metadata not available');
            }

        } catch (error: unknown) {
            const apiError = error as { detail?: { msg: string }[] };
            addToast({ message: apiError.detail?.[0]?.msg || 'Failed to load preview.', type: 'error' });
        } finally {
            setIsLoading(false);
        }
    }, [folderId, filename, addToast]);

    useEffect(() => {
        loadData();
        return () => {
            if (pdfUrl) {
                URL.revokeObjectURL(pdfUrl);
            }
        };
    }, [loadData]);

    // After loading, if no CSV exists (not yet extracted), default to schema view
    useEffect(() => {
        if (!isLoading && !csvData && metadata?.has_markdown) {
            // File is parsed but not extracted - show schema editor by default
            setActiveView('schema');
        }
    }, [isLoading, csvData, metadata]);

    function onDocumentLoadSuccess({ numPages }: { numPages: number }): void {
        setNumPages(numPages);
    }

    // Handle extraction complete - parse CSV content and switch to CSV view
    const handleExtractionComplete = useCallback((result: ExtractResponse) => {
        if (result.csv_content) {
            Papa.parse<string[]>(result.csv_content, {
                complete: (results) => {
                    const [headerRow, ...rows] = results.data;
                    setCsvData({ headers: headerRow, rows });
                },
                error: (error: Error) => {
                    console.error('CSV Parse Error:', error);
                }
            });
        }
        // Switch to CSV view to show results
        setActiveView('csv');
    }, []);

    const handleZoomIn = () => {
        setScale(prev => Math.min(prev + 0.25, 3.0));
    };

    const handleZoomOut = () => {
        setScale(prev => Math.max(prev - 0.25, 0.5));
    };

    const handleResetZoom = () => {
        setScale(1.0);
    };

    const handleFitToWidth = () => {
        if (containerWidth > 0) {
            setScale(containerWidth / 850);
        }
    };

    const handleDownloadCsv = async () => {
        if (!folderId || !filename) return;
        try {
            const processedFilename = `${filename}.csv`;
            const blob = await api.downloadResult(folderId, processedFilename);
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `${filename.replace('.pdf', '')}_result.csv`;
            document.body.appendChild(a);
            a.click();
            a.remove();
            window.URL.revokeObjectURL(url);
        } catch (error: unknown) {
            const apiError = error as { detail?: { msg: string }[] };
            addToast({ message: apiError.detail?.[0]?.msg || 'Download failed.', type: 'error' });
        }
    };

    const handleChunkClick = (chunk: ParsedChunk) => {
        const chunkId = chunk.id || '';
        setSelectedChunkId(chunkId);

        // Navigate to the page containing this chunk
        const page = chunk.grounding?.page ?? chunk.page_number ?? 0;

        // Scroll to the page in the PDF viewer
        if (pdfContainerRef.current) {
            const pageElement = pdfContainerRef.current.querySelector(`[data-page-number="${page + 1}"]`);
            if (pageElement) {
                pageElement.scrollIntoView({ behavior: 'smooth', block: 'center' });
            }
        }
    };

    const toggleChunkExpanded = (chunkId: string) => {
        setExpandedChunks(prev => {
            const next = new Set(prev);
            if (next.has(chunkId)) {
                next.delete(chunkId);
            } else {
                next.add(chunkId);
            }
            return next;
        });
    };

    const getChunksForPage = (pageNum: number): ParsedChunk[] => {
        if (!metadata?.chunks) return [];
        return metadata.chunks.filter(chunk => {
            const page = chunk.grounding?.page ?? chunk.page_number ?? 0;
            return page === pageNum;
        });
    };

    // Handler called when a PDF page finishes rendering - captures actual dimensions
    const handlePageRenderSuccess = (pageIndex: number) => {
        const pageWrapper = pageRefs.current.get(pageIndex);
        if (pageWrapper) {
            // Find the canvas element inside the Page component
            const canvas = pageWrapper.querySelector('canvas');
            if (canvas) {
                // Use getBoundingClientRect for actual CSS rendered dimensions
                // canvas.width/height are internal bitmap dimensions (scaled by devicePixelRatio)
                const rect = canvas.getBoundingClientRect();
                setPageDimensions(prev => {
                    const next = new Map(prev);
                    next.set(pageIndex, { width: rect.width, height: rect.height });
                    return next;
                });
            }
        }
    };

    useEffect(() => {
        const updateWidth = () => {
            const container = document.getElementById('pdf-container');
            if (container) {
                setContainerWidth(container.clientWidth - 32);
            }
        };

        updateWidth();
        window.addEventListener('resize', updateWidth);
        return () => window.removeEventListener('resize', updateWidth);
    }, []);

    // Recapture page dimensions when scale changes (after a brief delay for re-render)
    useEffect(() => {
        const timer = setTimeout(() => {
            pageRefs.current.forEach((_, pageIndex) => {
                handlePageRenderSuccess(pageIndex);
            });
        }, 100);
        return () => clearTimeout(timer);
    }, [scale]);

    if (isLoading) {
        return (
            <div className="h-screen flex items-center justify-center">
                <Spinner size="lg" />
                <p className="ml-4 text-lg">Loading documents...</p>
            </div>
        );
    }

    if (!pdfUrl) {
        return <div className="text-center p-20">Could not load documents for preview.</div>;
    }

    return (
        <div className="flex flex-col h-screen bg-secondary-50">
            <header className="flex-shrink-0 bg-white border-b border-secondary-200">
                <div className="container mx-auto p-4 flex items-center justify-between">
                    <nav className="flex items-center text-sm text-secondary-500" aria-label="Breadcrumb">
                        <Link to="/" className="hover:text-primary-600 flex items-center">
                            <Home size={16} className="mr-2" /> Home
                        </Link>
                        <ChevronRight size={16} className="mx-2" />
                        <Link to={`/folder/${folderId}`} className="hover:text-primary-600 truncate">
                            Project
                        </Link>
                        <ChevronRight size={16} className="mx-2" />
                        <span className="font-medium text-secondary-700 truncate">{filename}</span>
                    </nav>

                    {/* Metadata Stats */}
                    {metadata && (
                        <div className="flex items-center gap-4 text-sm text-secondary-600">
                            <span className="flex items-center gap-1">
                                <Layers size={14} />
                                {metadata.chunks_count} chunks
                            </span>
                            <span className="flex items-center gap-1">
                                <FileText size={14} />
                                {metadata.pages_count} pages
                            </span>
                            {metadata.chunk_types && Object.entries(metadata.chunk_types).map(([type, count]) => (
                                <span key={type} className="flex items-center gap-1">
                                    <ChunkTypeIcon type={type} />
                                    {count} {type}
                                </span>
                            ))}
                        </div>
                    )}
                </div>
            </header>

            <main className="flex-grow grid grid-cols-1 md:grid-cols-2 gap-4 p-4 overflow-hidden">
                {/* PDF Viewer */}
                <div className="bg-white rounded-lg shadow-md overflow-hidden flex flex-col">
                    <div className="p-2 border-b border-secondary-200 flex items-center justify-between">
                        <h2 className="font-semibold text-lg">Original Document</h2>
                        <div className="flex items-center gap-2">
                            <button
                                onClick={() => setShowBoundingBoxes(!showBoundingBoxes)}
                                className={`p-1.5 rounded transition-colors ${showBoundingBoxes ? 'bg-primary-100 text-primary-600' : 'hover:bg-secondary-100'}`}
                                title={showBoundingBoxes ? 'Hide Bounding Boxes' : 'Show Bounding Boxes'}
                            >
                                {showBoundingBoxes ? <Eye size={18} /> : <EyeOff size={18} />}
                            </button>
                            <div className="w-px h-6 bg-secondary-300 mx-1"></div>
                            <button
                                onClick={handleZoomOut}
                                className="p-1.5 hover:bg-secondary-100 rounded transition-colors"
                                title="Zoom Out"
                                disabled={scale <= 0.5}
                            >
                                <ZoomOut size={18} />
                            </button>
                            <span className="text-sm font-medium min-w-[60px] text-center">
                                {Math.round(scale * 100)}%
                            </span>
                            <button
                                onClick={handleZoomIn}
                                className="p-1.5 hover:bg-secondary-100 rounded transition-colors"
                                title="Zoom In"
                                disabled={scale >= 3.0}
                            >
                                <ZoomIn size={18} />
                            </button>
                            <div className="w-px h-6 bg-secondary-300 mx-1"></div>
                            <button
                                onClick={handleFitToWidth}
                                className="p-1.5 hover:bg-secondary-100 rounded transition-colors"
                                title="Fit to Width"
                            >
                                <Maximize2 size={18} />
                            </button>
                            <button
                                onClick={handleResetZoom}
                                className="p-1.5 hover:bg-secondary-100 rounded transition-colors"
                                title="Reset Zoom"
                            >
                                <RotateCcw size={18} />
                            </button>
                        </div>
                    </div>
                    <div
                        id="pdf-container"
                        ref={pdfContainerRef}
                        className="p-4 overflow-y-auto flex-grow bg-secondary-100"
                    >
                        <Document file={pdfUrl} onLoadSuccess={onDocumentLoadSuccess}>
                            {Array.from(new Array(numPages), (_, index) => {
                                const dims = pageDimensions.get(index);
                                return (
                                    <div
                                        key={`page_${index + 1}`}
                                        className="relative mb-4 inline-block"
                                        ref={(el) => {
                                            if (el) pageRefs.current.set(index, el);
                                        }}
                                    >
                                        <Page
                                            pageNumber={index + 1}
                                            renderTextLayer={false}
                                            renderAnnotationLayer={false}
                                            scale={scale}
                                            className="shadow-md"
                                            onRenderSuccess={() => handlePageRenderSuccess(index)}
                                        />
                                        {/* Overlay container - sized to match the canvas exactly */}
                                        {showBoundingBoxes && dims && (
                                            <div
                                                className="absolute top-0 left-0 pointer-events-none"
                                                style={{
                                                    width: dims.width,
                                                    height: dims.height,
                                                }}
                                            >
                                                {getChunksForPage(index).map((chunk) => {
                                                    const box = chunk.grounding?.box;
                                                    if (!box) return null;
                                                    const isSelected = chunk.id === selectedChunkId;
                                                    return (
                                                        <div
                                                            key={chunk.id}
                                                            className={`absolute border-2 transition-all cursor-pointer pointer-events-auto ${isSelected
                                                                ? 'border-primary-500 bg-primary-500/20'
                                                                : chunk.type === 'table'
                                                                    ? 'border-purple-400 bg-purple-400/10 hover:bg-purple-400/20'
                                                                    : 'border-blue-400 bg-blue-400/10 hover:bg-blue-400/20'
                                                                }`}
                                                            style={{
                                                                left: `${box.left * 100}%`,
                                                                top: `${box.top * 100}%`,
                                                                width: `${(box.right - box.left) * 100}%`,
                                                                height: `${(box.bottom - box.top) * 100}%`,
                                                            }}
                                                            onClick={() => handleChunkClick(chunk)}
                                                            title={`${chunk.type || 'text'} chunk: ${chunk.id?.slice(0, 8)}...`}
                                                        >
                                                            <span className={`absolute -top-5 left-0 text-xs px-1 py-0.5 rounded whitespace-nowrap ${isSelected ? 'bg-primary-500 text-white' : 'bg-secondary-700 text-white'
                                                                }`}>
                                                                {chunk.type || 'text'}
                                                            </span>
                                                        </div>
                                                    );
                                                })}
                                            </div>
                                        )}
                                    </div>
                                );
                            })}
                        </Document>
                    </div>
                </div>

                {/* Analysis Result Viewer */}
                <div className="bg-white rounded-lg shadow-md overflow-hidden flex flex-col">
                    <div className="p-2 border-b border-secondary-200 flex items-center justify-between">
                        <h2 className="font-semibold text-lg">Analysis Result</h2>
                        <div className="flex items-center gap-2">
                            <div className="flex bg-secondary-100 rounded-lg p-1">
                                <button
                                    onClick={() => setActiveView('csv')}
                                    className={`flex items-center px-3 py-1.5 rounded-md text-sm font-medium transition-all ${activeView === 'csv'
                                        ? 'bg-white text-primary-600 shadow-sm'
                                        : 'text-secondary-600 hover:text-secondary-900'
                                        }`}
                                >
                                    <Table size={16} className="mr-2" />
                                    CSV
                                    {csvData && (
                                        <span className="ml-1.5 bg-green-100 text-green-700 text-xs px-1.5 py-0.5 rounded-full">
                                            {csvData.rows.filter(r => r && r.length > 0 && r.some(c => (c ?? '').trim() !== '')).length}
                                        </span>
                                    )}
                                </button>
                                <button
                                    onClick={() => setActiveView('markdown')}
                                    className={`flex items-center px-3 py-1.5 rounded-md text-sm font-medium transition-all ${activeView === 'markdown'
                                        ? 'bg-white text-primary-600 shadow-sm'
                                        : 'text-secondary-600 hover:text-secondary-900'
                                        }`}
                                >
                                    <FileText size={16} className="mr-2" />
                                    Raw Text
                                </button>
                                <button
                                    onClick={() => setActiveView('chunks')}
                                    className={`flex items-center px-3 py-1.5 rounded-md text-sm font-medium transition-all ${activeView === 'chunks'
                                        ? 'bg-white text-primary-600 shadow-sm'
                                        : 'text-secondary-600 hover:text-secondary-900'
                                        }`}
                                >
                                    <Layers size={16} className="mr-2" />
                                    Chunks
                                </button>
                                <button
                                    onClick={() => setActiveView('schema')}
                                    className={`flex items-center px-3 py-1.5 rounded-md text-sm font-medium transition-all ${activeView === 'schema'
                                        ? 'bg-white text-primary-600 shadow-sm'
                                        : 'text-secondary-600 hover:text-secondary-900'
                                        }`}
                                >
                                    <Settings size={16} className="mr-2" />
                                    Schema
                                </button>
                            </div>
                            {csvData && (
                                <Button size="sm" onClick={handleDownloadCsv}>
                                    <Download size={16} className="mr-2" />
                                    Download CSV
                                </Button>
                            )}
                        </div>
                    </div>

                    <div className="flex-grow overflow-y-auto p-4">
                        {activeView === 'csv' ? (
                            csvData ? (
                                <div className="relative overflow-x-auto">
                                    <table className="w-full text-sm text-left table-auto">
                                        <thead>
                                            <tr>
                                                {csvData.headers.map((header, idx) => (
                                                    <th
                                                        key={`${header}-${idx}`}
                                                        className="p-2 font-semibold text-secondary-700 bg-secondary-100 sticky top-0 z-10"
                                                    >
                                                        {header}
                                                    </th>
                                                ))}
                                            </tr>
                                        </thead>
                                        <tbody className="divide-y divide-secondary-100">
                                            {csvData.rows
                                                .filter(row => row && row.length > 0 && row.some(cell => (cell ?? '').trim() !== ''))
                                                .map((row, i) => (
                                                    <tr key={i} className="hover:bg-secondary-50">
                                                        {row.map((cell, j) => (
                                                            <td key={j} className="p-2 text-secondary-600">
                                                                {cell}
                                                            </td>
                                                        ))}
                                                    </tr>
                                                ))}
                                        </tbody>
                                    </table>
                                </div>
                            ) : (
                                <div className="flex flex-col items-center justify-center h-full text-secondary-500">
                                    <div className="bg-amber-50 border border-amber-200 rounded-lg p-6 max-w-md text-center">
                                        <Settings size={48} className="mx-auto mb-4 text-amber-500" />
                                        <h3 className="text-lg font-semibold text-secondary-800 mb-2">Ready to Extract Transactions</h3>
                                        <p className="text-secondary-600 mb-4">
                                            Your document has been parsed. Go to the <strong>Schema</strong> tab to review or customize the extraction fields, then click <strong>Extract Transactions</strong>.
                                        </p>
                                        <Button size="sm" onClick={() => setActiveView('schema')}>
                                            <Settings size={16} className="mr-2" />
                                            Go to Schema
                                        </Button>
                                    </div>
                                </div>
                            )
                        ) : activeView === 'chunks' ? (
                            metadata?.chunks && metadata.chunks.length > 0 ? (
                                <div className="space-y-3">
                                    {/* Chunk Type Legend */}
                                    <div className="flex items-center gap-4 p-3 bg-secondary-50 rounded-lg text-sm">
                                        <span className="font-medium text-secondary-700">Legend:</span>
                                        <ChunkTypeBadge type="text" />
                                        <ChunkTypeBadge type="table" />
                                        <ChunkTypeBadge type="image" />
                                    </div>

                                    {/* Chunks List */}
                                    {metadata.chunks.map((chunk, idx) => {
                                        const chunkId = chunk.id || `chunk-${idx}`;
                                        const isExpanded = expandedChunks.has(chunkId);
                                        const isSelected = chunk.id === selectedChunkId;
                                        const page = chunk.grounding?.page ?? chunk.page_number ?? 0;

                                        return (
                                            <div
                                                key={chunkId}
                                                className={`border rounded-lg overflow-hidden transition-all ${isSelected
                                                    ? 'border-primary-400 ring-2 ring-primary-200'
                                                    : 'border-secondary-200 hover:border-secondary-300'
                                                    }`}
                                            >
                                                <div
                                                    className={`flex items-center justify-between p-3 cursor-pointer ${isSelected ? 'bg-primary-50' : 'bg-white hover:bg-secondary-50'
                                                        }`}
                                                    onClick={() => handleChunkClick(chunk)}
                                                >
                                                    <div className="flex items-center gap-3">
                                                        <span className="text-xs font-mono text-secondary-400 w-8">
                                                            #{idx + 1}
                                                        </span>
                                                        <ChunkTypeBadge type={chunk.type} />
                                                        <span className="text-sm text-secondary-500">
                                                            Page {page + 1}
                                                        </span>
                                                        {chunk.grounding?.box && (
                                                            <span className="text-xs text-secondary-400">
                                                                ({Math.round(chunk.grounding.box.left * 100)}%, {Math.round(chunk.grounding.box.top * 100)}%)
                                                            </span>
                                                        )}
                                                    </div>
                                                    <button
                                                        onClick={(e) => {
                                                            e.stopPropagation();
                                                            toggleChunkExpanded(chunkId);
                                                        }}
                                                        className="p-1 hover:bg-secondary-200 rounded transition-colors"
                                                    >
                                                        {isExpanded ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
                                                    </button>
                                                </div>

                                                {isExpanded && chunk.markdown && (
                                                    <div className="border-t border-secondary-200 p-3 bg-secondary-50">
                                                        <div className="prose prose-sm max-w-none">
                                                            <ReactMarkdown
                                                                remarkPlugins={[remarkGfm]}
                                                                rehypePlugins={[rehypeRaw]}
                                                                components={{
                                                                    table: ({ ...props }) => (
                                                                        <div className="overflow-x-auto my-2 border border-secondary-200 rounded">
                                                                            <table className="min-w-full divide-y divide-secondary-200" {...props} />
                                                                        </div>
                                                                    ),
                                                                    thead: ({ ...props }) => <thead className="bg-secondary-100" {...props} />,
                                                                    tbody: ({ ...props }) => <tbody className="bg-white divide-y divide-secondary-200" {...props} />,
                                                                    tr: ({ ...props }) => <tr className="hover:bg-secondary-50" {...props} />,
                                                                    th: ({ ...props }) => <th className="px-2 py-1 text-left text-xs font-medium text-secondary-500 uppercase" {...props} />,
                                                                    td: ({ ...props }) => <td className="px-2 py-1 text-sm text-secondary-700" {...props} />,
                                                                }}
                                                            >
                                                                {chunk.markdown}
                                                            </ReactMarkdown>
                                                        </div>
                                                        {chunk.id && (
                                                            <div className="mt-2 pt-2 border-t border-secondary-200">
                                                                <code className="text-xs text-secondary-400 font-mono">
                                                                    ID: {chunk.id}
                                                                </code>
                                                            </div>
                                                        )}
                                                    </div>
                                                )}
                                            </div>
                                        );
                                    })}
                                </div>
                            ) : (
                                <div className="flex flex-col items-center justify-center h-full text-secondary-400">
                                    <Layers size={48} className="mb-4 opacity-50" />
                                    <p>No chunk data available.</p>
                                    <p className="text-sm mt-1">Process the file to see parsed chunks.</p>
                                </div>
                            )
                        ) : activeView === 'schema' ? (
                            folderId && filename ? (
                                <SchemaEditorTable
                                    folderId={folderId}
                                    filename={filename}
                                    onExtractionComplete={handleExtractionComplete}
                                />
                            ) : (
                                <div className="flex flex-col items-center justify-center h-full text-secondary-400">
                                    <Settings size={48} className="mb-4 opacity-50" />
                                    <p>Unable to load schema editor.</p>
                                </div>
                            )
                        ) : (
                            markdownContent ? (
                                <div className="prose prose-sm max-w-none prose-headings:text-secondary-800 prose-p:text-secondary-600 prose-pre:bg-secondary-800 prose-pre:text-secondary-50">
                                    <ReactMarkdown
                                        remarkPlugins={[remarkGfm]}
                                        rehypePlugins={[rehypeRaw]}
                                        components={{
                                            table: ({ ...props }) => (
                                                <div className="overflow-x-auto my-4 border border-secondary-200 rounded-lg">
                                                    <table className="min-w-full divide-y divide-secondary-200" {...props} />
                                                </div>
                                            ),
                                            thead: ({ ...props }) => <thead className="bg-secondary-50" {...props} />,
                                            tbody: ({ ...props }) => <tbody className="bg-white divide-y divide-secondary-200" {...props} />,
                                            tr: ({ ...props }) => <tr className="hover:bg-secondary-50 transition-colors" {...props} />,
                                            th: ({ ...props }) => <th className="px-3 py-2 text-left text-xs font-medium text-secondary-500 uppercase tracking-wider border-b border-secondary-200" {...props} />,
                                            td: ({ ...props }) => <td className="px-3 py-2 whitespace-nowrap text-sm text-secondary-700 border-b border-secondary-100" {...props} />,
                                        }}
                                    >
                                        {markdownContent}
                                    </ReactMarkdown>
                                </div>
                            ) : (
                                <div className="flex flex-col items-center justify-center h-full text-secondary-400">
                                    <FileText size={48} className="mb-4 opacity-50" />
                                    <p>No markdown content available.</p>
                                </div>
                            )
                        )}
                    </div>
                </div>
            </main>
        </div>
    );
};

export default Preview;
