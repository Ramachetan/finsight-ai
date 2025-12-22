

import React, { useState, useEffect, useCallback } from 'react';
import { useParams, Link } from 'react-router-dom';
import * as api from '../lib/api';
import { useToast } from '../hooks/useToast';
import { Spinner } from '../components/ui/Spinner';
import { Button } from '../components/ui/Button.tsx';
import { Home, ChevronRight, ZoomIn, ZoomOut, Maximize2, RotateCcw, FileText, Table, Download } from 'lucide-react';
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

const Preview: React.FC = () => {
  const { folderId, filename } = useParams<{ folderId: string; filename: string }>();
  const [pdfUrl, setPdfUrl] = useState<string | null>(null);
  const [csvData, setCsvData] = useState<CsvData | null>(null);
  const [markdownContent, setMarkdownContent] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [numPages, setNumPages] = useState<number>(0);
  const [scale, setScale] = useState<number>(1.0);
  const [containerWidth, setContainerWidth] = useState<number>(0);
  const [activeView, setActiveView] = useState<'csv' | 'markdown'>('csv');
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
          error: (error: any) => {
            console.error('CSV Parse Error:', error);
          }
        });
      } catch (e) {
        console.warn('CSV not available');
      }

      // Fetch Markdown
      try {
        const markdown = await api.getFileMarkdown(folderId, filename);
        setMarkdownContent(markdown);
      } catch (e) {
        console.warn('Markdown not available');
      }

    } catch (error: any) {
      addToast({ message: error.detail?.[0]?.msg || 'Failed to load preview.', type: 'error' } as any);
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

  function onDocumentLoadSuccess({ numPages }: { numPages: number }): void {
    setNumPages(numPages);
  }

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
      // Approximate fit to width (accounting for padding)
      setScale(containerWidth / 850); // Assuming default PDF width is 850px
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
    } catch (error: any) {
      addToast({ message: error.detail?.[0]?.msg || 'Download failed.', type: 'error' } as any);
    }
  };

  useEffect(() => {
    const updateWidth = () => {
      const container = document.getElementById('pdf-container');
      if (container) {
        setContainerWidth(container.clientWidth - 32); // Subtract padding
      }
    };

    updateWidth();
    window.addEventListener('resize', updateWidth);
    return () => window.removeEventListener('resize', updateWidth);
  }, []);

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
        </div>
      </header>

      <main className="flex-grow grid grid-cols-1 md:grid-cols-2 gap-4 p-4 overflow-hidden">
        {/* PDF Viewer */}
        <div className="bg-white rounded-lg shadow-md overflow-hidden flex flex-col">
          <div className="p-2 border-b border-secondary-200 flex items-center justify-between">
            <h2 className="font-semibold text-lg">Original Document</h2>
            <div className="flex items-center gap-2">
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
          <div id="pdf-container" className="p-4 overflow-y-auto flex-grow bg-secondary-100">
            <Document file={pdfUrl} onLoadSuccess={onDocumentLoadSuccess}>
              {Array.from(new Array(numPages), (el, index) => (
                <Page
                  key={`page_${index + 1}`}
                  pageNumber={index + 1}
                  renderTextLayer={false}
                  scale={scale}
                  className="mb-4 shadow-md"
                />
              ))}
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
                  CSV Data
                </button>
                <button
                  onClick={() => setActiveView('markdown')}
                  className={`flex items-center px-3 py-1.5 rounded-md text-sm font-medium transition-all ${activeView === 'markdown'
                    ? 'bg-white text-primary-600 shadow-sm'
                    : 'text-secondary-600 hover:text-secondary-900'
                    }`}
                >
                  <FileText size={16} className="mr-2" />
                  Markdown
                </button>
              </div>
              <Button size="sm" onClick={handleDownloadCsv} disabled={!csvData}>
                <Download size={16} className="mr-2" />
                CSV
              </Button>
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
                <div className="flex flex-col items-center justify-center h-full text-secondary-400">
                  <Table size={48} className="mb-4 opacity-50" />
                  <p>No CSV data available.</p>
                </div>
              )
            ) : (
              markdownContent ? (
                <div className="prose prose-sm max-w-none prose-headings:text-secondary-800 prose-p:text-secondary-600 prose-pre:bg-secondary-800 prose-pre:text-secondary-50">
                  <ReactMarkdown
                    remarkPlugins={[remarkGfm]}
                    rehypePlugins={[rehypeRaw]}
                    components={{
                      table: ({ node, ...props }) => (
                        <div className="overflow-x-auto my-4 border border-secondary-200 rounded-lg">
                          <table className="min-w-full divide-y divide-secondary-200" {...props} />
                        </div>
                      ),
                      thead: ({ node, ...props }) => <thead className="bg-secondary-50" {...props} />,
                      tbody: ({ node, ...props }) => <tbody className="bg-white divide-y divide-secondary-200" {...props} />,
                      tr: ({ node, ...props }) => <tr className="hover:bg-secondary-50 transition-colors" {...props} />,
                      th: ({ node, ...props }) => <th className="px-3 py-2 text-left text-xs font-medium text-secondary-500 uppercase tracking-wider border-b border-secondary-200" {...props} />,
                      td: ({ node, ...props }) => <td className="px-3 py-2 whitespace-nowrap text-sm text-secondary-700 border-b border-secondary-100" {...props} />,
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
