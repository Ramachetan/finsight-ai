
import React, { useEffect, useCallback, useRef, useState } from 'react';
import { useParams, Link, useNavigate } from 'react-router-dom';
import { FolderDetails as FolderDetailsType } from '../types.ts';
import * as api from '../lib/api.ts';
import { useToast } from '../hooks/useToast.tsx';
import FileUploader from '../components/FileUploader.tsx';
import ProcessingProgress from '../components/ProcessingProgress.tsx';
import { Button } from '../components/ui/Button.tsx';
import { Spinner } from '../components/ui/Spinner.tsx';
import { Skeleton } from '../components/ui/Skeleton.tsx';
import {
  AlertCircle,
  CheckCircle,
  ChevronRight,
  Clock,
  Download,
  Eye,
  FileSearch,
  FileText,
  Home,
  MoreVertical,
  Trash2,
} from 'lucide-react';
import { Modal } from '../components/ui/Modal.tsx';
// Removed Info/metadata preview as markdown is available in the Preview page

type ProcessingStatus = 'idle' | 'parsing' | 'parsed' | 'extracted' | 'error';

// Removed FileMetadata type and related Info modal state

const FolderWorkspace: React.FC = () => {
  const { folderId } = useParams<{ folderId: string }>();
  const [folder, setFolder] = useState<FolderDetailsType | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isUploading, setIsUploading] = useState(false);
  const [processingStatus, setProcessingStatus] = useState<{ [filename: string]: ProcessingStatus }>({});
  const [parsingFile, setParsingFile] = useState<string | null>(null);
  const [deleteModalOpen, setDeleteModalOpen] = useState(false);
  const [fileToDelete, setFileToDelete] = useState<string | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);

  const [openActionsFor, setOpenActionsFor] = useState<string | null>(null);
  const actionsMenuRef = useRef<HTMLDivElement | null>(null);
  const [actionsMenuDirection, setActionsMenuDirection] = useState<'down' | 'up'>('down');

  // Info modal removed

  const { addToast } = useToast();
  const navigate = useNavigate();

  const fetchFolderDetails = useCallback(async () => {
    if (!folderId) return;
    try {
      const data = await api.getFolderDetails(folderId);
      setFolder(data);

      // Check both parsed and processed status for each file
      const statusPromises = data.files.map(async (filename) => {
        const isExtracted = await api.isProcessed(folderId, filename);
        if (isExtracted) {
          return { filename, status: 'extracted' as const };
        }
        const isParsed = await api.isParsed(folderId, filename);
        if (isParsed) {
          return { filename, status: 'parsed' as const };
        }
        return { filename, status: 'idle' as const };
      });

      const statuses = await Promise.all(statusPromises);
      const initialStatus = statuses.reduce((acc, { filename, status }) => {
        acc[filename] = status;
        return acc;
      }, {} as { [filename: string]: ProcessingStatus });

      setProcessingStatus(initialStatus);

    } catch (error: any) {
      addToast({ message: error.detail?.[0]?.msg || 'Failed to load project details.', type: 'error' });
    } finally {
      setIsLoading(false);
    }
  }, [folderId, addToast]);

  useEffect(() => {
    setIsLoading(true);
    fetchFolderDetails();
  }, [fetchFolderDetails]);

  useEffect(() => {
    if (!openActionsFor) return;

    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpenActionsFor(null);
    };

    const onMouseDown = (e: MouseEvent) => {
      const target = e.target as Node | null;
      if (!target) return;
      if (actionsMenuRef.current && actionsMenuRef.current.contains(target)) return;
      setOpenActionsFor(null);
    };

    document.addEventListener('keydown', onKeyDown);
    document.addEventListener('mousedown', onMouseDown);

    return () => {
      document.removeEventListener('keydown', onKeyDown);
      document.removeEventListener('mousedown', onMouseDown);
    };
  }, [openActionsFor]);

  useEffect(() => {
    if (!openActionsFor) return;
    if (!actionsMenuRef.current) return;

    // Decide whether to open the menu upward or downward based on viewport space.
    // This prevents the menu from being cut off for items near the bottom.
    const rect = actionsMenuRef.current.getBoundingClientRect();
    const spaceBelow = window.innerHeight - rect.bottom;
    const spaceAbove = rect.top;

    // Approx menu height: 140-180px depending on whether CSV is present.
    const estimatedMenuHeight = 180;

    if (spaceBelow < estimatedMenuHeight && spaceAbove > spaceBelow) {
      setActionsMenuDirection('up');
    } else {
      setActionsMenuDirection('down');
    }
  }, [openActionsFor]);

  const handleUpload = async (files: File[]) => {
    if (!folderId) return;
    setIsUploading(true);
    try {
      await api.uploadFiles(folderId, files);
      addToast({ message: `${files.length} file(s) uploaded successfully.`, type: 'success' });
      fetchFolderDetails();
    } catch (error: any) {
      addToast({ message: error.detail?.[0]?.msg || 'Upload failed.', type: 'error' });
    } finally {
      setIsUploading(false);
    }
  };

  const handleAnalyze = async (filename: string) => {
    if (!folderId) return;

    // Show progress immediately
    setParsingFile(filename);
    setProcessingStatus(prev => ({ ...prev, [filename]: 'parsing' }));

    try {
      // Call parse endpoint (not the combined process endpoint)
      await api.parseFile(folderId, filename);
      setProcessingStatus(prev => ({ ...prev, [filename]: 'parsed' }));
      addToast({ message: `Parsing complete for ${filename}. Ready for schema review.`, type: 'success' });

      // Navigate to preview page for schema editing and extraction
      navigate(`/folder/${folderId}/preview/${encodeURIComponent(filename)}`);
    } catch (error: any) {
      setProcessingStatus(prev => ({ ...prev, [filename]: 'error' }));
      addToast({ message: error.detail?.[0]?.msg || `Parsing failed for ${filename}.`, type: 'error' });
    } finally {
      setParsingFile(null);
    }
  };

  const handleDownloadCsv = async (filename: string) => {
    if (!folderId) return;
    try {
      // The backend saves processed files as {filename}.csv
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
      addToast({ message: error.detail?.[0]?.msg || 'Download CSV failed.', type: 'error' });
    }
  };

  const handleDownloadPdf = async (filename: string) => {
    if (!folderId) return;
    try {
      const blob = await api.getOriginalFile(folderId, filename);
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(url);
    } catch (error: any) {
      addToast({ message: error.detail?.[0]?.msg || 'Download PDF failed.', type: 'error' });
    }
  };

  const handlePreview = (filename: string) => {
    if (!folderId) return;
    navigate(`/folder/${folderId}/preview/${filename}`);
  }

  const handleDeleteClick = (filename: string) => {
    setFileToDelete(filename);
    setDeleteModalOpen(true);
  };

  const handleDeleteConfirm = async () => {
    if (!folderId || !fileToDelete) return;
    setIsDeleting(true);
    try {
      await api.deleteFile(folderId, fileToDelete);
      addToast({ message: `${fileToDelete} deleted successfully.`, type: 'success' });
      setDeleteModalOpen(false);
      setFileToDelete(null);
      fetchFolderDetails();
    } catch (error: any) {
      addToast({ message: error.detail?.[0]?.msg || 'Failed to delete file.', type: 'error' });
    } finally {
      setIsDeleting(false);
    }
  };

  const handleDeleteCancel = () => {
    setDeleteModalOpen(false);
    setFileToDelete(null);
  };

  // Removed metadata fetching/view logic

  // Removed metadata modal close handler

  const getStatusBadge = (status: ProcessingStatus) => {
    switch (status) {
      case 'parsing':
        return (
          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800">
            <Spinner size="sm" className="mr-1.5" /> Parsing
          </span>
        );
      case 'parsed':
        return (
          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-amber-100 text-amber-800">
            <FileSearch size={12} className="mr-1.5" /> Ready for Extraction
          </span>
        );
      case 'extracted':
        return (
          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-800">
            <CheckCircle size={12} className="mr-1.5" /> Extracted
          </span>
        );
      case 'error':
        return (
          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-red-100 text-red-800">
            <AlertCircle size={12} className="mr-1.5" /> Failed
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-secondary-100 text-secondary-800">
            <Clock size={12} className="mr-1.5" /> Ready to Parse
          </span>
        );
    }
  };

  const renderPrimaryAction = (filename: string) => {
    const status = processingStatus[filename] || 'idle';
    switch (status) {
      case 'parsing':
        return (
          <Button size="sm" disabled className="opacity-75">
            Parsing...
          </Button>
        );
      case 'parsed':
        return (
          <Button size="sm" onClick={() => handlePreview(filename)}>
            <Eye size={16} className="mr-2" />
            Review & Extract
          </Button>
        );
      case 'extracted':
        return (
          <Button size="sm" variant="secondary" onClick={() => handlePreview(filename)}>
            <Eye size={16} className="mr-2" />
            Preview
          </Button>
        );
      case 'error':
        return (
          <Button size="sm" variant="danger" onClick={() => handleAnalyze(filename)}>
            Retry Parse
          </Button>
        );
      case 'idle':
      default:
        return (
          <Button size="sm" onClick={() => handleAnalyze(filename)}>
            <FileSearch size={16} className="mr-2" />
            Parse
          </Button>
        );
    }
  };

  if (isLoading) {
    return (
      <div className="container mx-auto p-8">
        <Skeleton className="h-6 w-1/3 mb-8" />
        <Skeleton className="h-40 w-full mb-8" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  if (!folder) {
    return <div className="text-center p-20">Project not found.</div>;
  }

  return (
    <div className="container mx-auto p-4 sm:p-6 lg:p-8">
      <nav className="flex items-center text-sm text-secondary-500 mb-8 bg-white/50 backdrop-blur-sm p-3 rounded-lg inline-flex border border-secondary-200" aria-label="Breadcrumb">
        <Link to="/" className="hover:text-primary-600 flex items-center transition-colors">
          <Home size={16} className="mr-2" /> Home
        </Link>
        <ChevronRight size={16} className="mx-2 text-secondary-400" />
        <span className="font-medium text-secondary-800 truncate max-w-[200px]">{folder.name}</span>
      </nav>

      <header className="mb-8">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-bold text-secondary-900 truncate mb-2">{folder.name}</h1>
            <p className="text-secondary-600">Manage your documents and run analysis.</p>
          </div>
          <div className="bg-primary-50 px-4 py-2 rounded-lg border border-primary-100">
            <span className="text-sm font-medium text-primary-800">
              {folder.files.length} Document{folder.files.length !== 1 ? 's' : ''}
            </span>
          </div>
        </div>
      </header>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        <div className="lg:col-span-2 space-y-8">
          <section id="file-list">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-xl font-bold text-secondary-800">Documents</h2>
            </div>

            <div className="bg-white rounded-xl shadow-sm border border-secondary-200 overflow-visible">
              {folder.files.length > 0 ? (
                <ul className="divide-y divide-secondary-100">
                  {folder.files.map(filename => (
                    <li key={filename} className="group p-4 hover:bg-secondary-50 transition-colors duration-200">
                      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                        <div className="flex items-start gap-4 flex-1">
                          <div className="p-2 bg-primary-50 rounded-lg text-primary-600 group-hover:bg-primary-100 transition-colors">
                            <FileText className="w-6 h-6" />
                          </div>
                          <div className="flex-1 min-w-0">
                            <h3 className="font-medium text-secondary-900 break-all">{filename}</h3>
                            <div className="mt-2">
                              {parsingFile === filename ? (
                                <ProcessingProgress
                                  folderId={folderId!}
                                  filename={filename}
                                  onComplete={() => {
                                    setParsingFile(null);
                                  }}
                                />
                              ) : (
                                getStatusBadge(processingStatus[filename] || 'idle')
                              )}
                            </div>
                          </div>
                        </div>

                        <div className="flex items-center gap-2 self-end sm:self-center">
                          {renderPrimaryAction(filename)}

                          <div className="relative" ref={openActionsFor === filename ? actionsMenuRef : undefined}>
                            <button
                              onClick={() => {
                                setOpenActionsFor(prev => (prev === filename ? null : filename));
                              }}
                              className="p-2 text-secondary-500 hover:text-secondary-800 hover:bg-secondary-100 rounded-lg transition-all"
                              title="More actions"
                              aria-haspopup="menu"
                              aria-expanded={openActionsFor === filename}
                            >
                              <MoreVertical size={18} />
                            </button>

                            {openActionsFor === filename && (
                              <div
                                className={`absolute right-0 w-48 bg-white border border-secondary-200 rounded-xl shadow-lg overflow-hidden z-50 ${actionsMenuDirection === 'up' ? 'bottom-full mb-2' : 'top-full mt-2'
                                  }`}
                                role="menu"
                              >
                                <button
                                  onClick={() => {
                                    setOpenActionsFor(null);
                                    handleDownloadPdf(filename);
                                  }}
                                  className="w-full px-3 py-2 text-sm text-secondary-700 hover:bg-secondary-50 flex items-center gap-2"
                                  role="menuitem"
                                >
                                  <Download size={16} className="text-secondary-500" />
                                  Download PDF
                                </button>

                                {(processingStatus[filename] || 'idle') === 'extracted' && (
                                  <button
                                    onClick={() => {
                                      setOpenActionsFor(null);
                                      handleDownloadCsv(filename);
                                    }}
                                    className="w-full px-3 py-2 text-sm text-secondary-700 hover:bg-secondary-50 flex items-center gap-2"
                                    role="menuitem"
                                  >
                                    <Download size={16} className="text-secondary-500" />
                                    Download CSV
                                  </button>
                                )}

                                <div className="h-px bg-secondary-100" />

                                <button
                                  onClick={() => {
                                    setOpenActionsFor(null);
                                    handleDeleteClick(filename);
                                  }}
                                  className="w-full px-3 py-2 text-sm text-red-700 hover:bg-red-50 flex items-center gap-2"
                                  role="menuitem"
                                >
                                  <Trash2 size={16} className="text-red-600" />
                                  Delete
                                </button>
                              </div>
                            )}
                          </div>
                        </div>
                      </div>
                    </li>
                  ))}
                </ul>
              ) : (
                <div className="text-center py-16 px-4">
                  <div className="bg-secondary-50 w-16 h-16 rounded-full flex items-center justify-center mx-auto mb-4">
                    <FileText className="w-8 h-8 text-secondary-400" />
                  </div>
                  <h3 className="text-lg font-medium text-secondary-900 mb-1">No documents yet</h3>
                  <p className="text-secondary-500">Upload your bank statements to get started.</p>
                </div>
              )}
            </div>
          </section>
        </div>

        <div className="lg:col-span-1">
          <section id="upload-zone" className="sticky top-24">
            <h2 className="text-xl font-bold text-secondary-800 mb-4">Upload</h2>
            <FileUploader onUpload={handleUpload} isUploading={isUploading} />

            <div className="mt-6 bg-blue-50 rounded-xl p-4 border border-blue-100">
              <h3 className="font-semibold text-blue-900 mb-2 flex items-center">
                <div className="w-1.5 h-1.5 rounded-full bg-blue-500 mr-2"></div>
                Tips
              </h3>
              <ul className="text-sm text-blue-800 space-y-2 pl-3.5">
                <li>• Upload PDF bank statements only</li>
                <li>• Ensure text is readable and clear</li>
                <li>• Larger files may take longer to process</li>
              </ul>
            </div>
          </section>
        </div>
      </div>

      <Modal
        isOpen={deleteModalOpen}
        onClose={handleDeleteCancel}
        title="Delete File"
      >
        <div className="space-y-4">
          <p className="text-secondary-700">
            Are you sure you want to delete <strong>{fileToDelete}</strong>?
          </p>
          <p className="text-sm text-secondary-500">
            This will also delete the associated processed CSV file if it exists. This action cannot be undone.
          </p>
          <div className="flex justify-end gap-3 mt-6">
            <Button
              variant="secondary"
              onClick={handleDeleteCancel}
              disabled={isDeleting}
            >
              Cancel
            </Button>
            <Button
              variant="danger"
              onClick={handleDeleteConfirm}
              disabled={isDeleting}
            >
              {isDeleting ? (
                <>
                  <Spinner size="sm" className="mr-2" />
                  Deleting...
                </>
              ) : (
                'Delete'
              )}
            </Button>
          </div>
        </div>
      </Modal>

      {/* Info/Metadata modal removed */}
    </div>
  );
};

export default FolderWorkspace;
