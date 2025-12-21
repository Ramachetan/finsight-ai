

import React, { useState, useEffect, useCallback } from 'react';
import { useParams, Link } from 'react-router-dom';
import * as api from '../lib/api';
import { useToast } from '../hooks/useToast';
import { Spinner } from '../components/ui/Spinner';
import { Home, ChevronRight, ZoomIn, ZoomOut, Maximize2, RotateCcw } from 'lucide-react';
import { Document, Page, pdfjs } from 'react-pdf';
import Papa from 'papaparse';

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
  const [isLoading, setIsLoading] = useState(true);
  const [numPages, setNumPages] = useState<number>(0);
  const [scale, setScale] = useState<number>(1.0);
  const [containerWidth, setContainerWidth] = useState<number>(0);
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
      const processedFilename = `${filename}.csv`;
      const csvBlob = await api.downloadResult(folderId, processedFilename);
      const csvText = await csvBlob.text();

      Papa.parse<string[]>(csvText, {
        complete: (results) => {
          const [headerRow, ...rows] = results.data;
          setCsvData({ headers: headerRow, rows });
        },
        error: (error: any) => {
          addToast({ message: `Failed to parse CSV: ${error.message}`, type: 'error' } as any);
        }
      });

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

  if (!pdfUrl || !csvData) {
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
          <div id="pdf-container" className="p-4 overflow-y-auto flex-grow">
            <Document file={pdfUrl} onLoadSuccess={onDocumentLoadSuccess}>
              {Array.from(new Array(numPages), (el, index) => (
                <Page
                  key={`page_${index + 1}`}
                  pageNumber={index + 1}
                  renderTextLayer={false}
                  scale={scale}
                  className="mb-4"
                />
              ))}
            </Document>
          </div>
        </div>

        {/* CSV Viewer */}
        <div className="bg-white rounded-lg shadow-md overflow-y-auto">
          <div className="p-2 border-b border-secondary-200">
            <h2 className="font-semibold text-lg">Analysis Result</h2>
          </div>
          <div className="p-4">
            <table className="w-full text-sm text-left">
              <thead className="bg-secondary-100">
                <tr>
                  {csvData.headers.map(header => <th key={header} className="p-2">{header}</th>)}
                </tr>
              </thead>
              <tbody>
                {csvData.rows.map((row, i) => (
                  <tr key={i} className="border-b border-secondary-200">
                    {row.map((cell, j) => <td key={j} className="p-2">{cell}</td>)}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </main>
    </div>
  );
};

export default Preview;
