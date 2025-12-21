
import React, { useState, useEffect, useCallback } from 'react';
import { useParams, Link, useNavigate } from 'react-router-dom';
import { FolderDetails as FolderDetailsType } from '../types.ts';
import * as api from '../lib/api.ts';
import { useToast } from '../hooks/useToast.tsx';
import FileUploader from '../components/FileUploader.tsx';
import { Button } from '../components/ui/Button.tsx';
import { Spinner } from '../components/ui/Spinner.tsx';
import { Skeleton } from '../components/ui/Skeleton.tsx';
import { Home, ChevronRight, FileText, Download, Eye, Trash2, CheckCircle, AlertCircle, Clock } from 'lucide-react';
import { Modal } from '../components/ui/Modal.tsx';

type ProcessingStatus = 'idle' | 'processing' | 'processed' | 'error';

const FolderWorkspace: React.FC = () => {
  const { folderId } = useParams<{ folderId: string }>();
  const [folder, setFolder] = useState<FolderDetailsType | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isUploading, setIsUploading] = useState(false);
  const [processingStatus, setProcessingStatus] = useState<{ [filename: string]: ProcessingStatus }>({});
  const [deleteModalOpen, setDeleteModalOpen] = useState(false);
  const [fileToDelete, setFileToDelete] = useState<string | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);
  const { addToast } = useToast();
  const navigate = useNavigate();

  const fetchFolderDetails = useCallback(async () => {
    if (!folderId) return;
    try {
      const data = await api.getFolderDetails(folderId);
      setFolder(data);

      const statusPromises = data.files.map(async (filename) => {
        const isProcessed = await api.isProcessed(folderId, filename);
        return { filename, status: isProcessed ? 'processed' : 'idle' } as const;
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
    setProcessingStatus(prev => ({ ...prev, [filename]: 'processing' }));
    try {
      await api.startProcessing(folderId, filename);
      setProcessingStatus(prev => ({ ...prev, [filename]: 'processed' }));
      addToast({ message: `Analysis complete for ${filename}.`, type: 'success' });
    } catch (error: any) {
      setProcessingStatus(prev => ({ ...prev, [filename]: 'error' }));
      addToast({ message: error.detail?.[0]?.msg || `Analysis failed for ${filename}.`, type: 'error' });
    }
  };

  const handleDownload = async (filename: string) => {
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
      addToast({ message: error.detail?.[0]?.msg || 'Download failed.', type: 'error' });
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

  const getStatusBadge = (status: ProcessingStatus) => {
    switch (status) {
      case 'processing':
        return (
          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800">
            <Spinner size="sm" className="mr-1.5" /> Processing
          </span>
        );
      case 'processed':
        return (
          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-800">
            <CheckCircle size={12} className="mr-1.5" /> Completed
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
            <Clock size={12} className="mr-1.5" /> Ready to Analyze
          </span>
        );
    }
  };

  const renderActionButton = (filename: string) => {
    const status = processingStatus[filename] || 'idle';
    switch (status) {
      case 'processing':
        return <Button size="sm" disabled className="opacity-75">Analyzing...</Button>;
      case 'processed':
        return (
          <div className="flex gap-2 justify-end">
            <Button size="sm" variant="secondary" onClick={() => handlePreview(filename)}>
              <Eye size={16} className="mr-2" />Preview
            </Button>
            <Button size="sm" onClick={() => handleDownload(filename)}>
              <Download size={16} className="mr-2" />Download
            </Button>
          </div>
        );
      case 'error':
        return (
          <Button size="sm" variant="danger" onClick={() => handleAnalyze(filename)}>Retry</Button>
        );
      case 'idle':
      default:
        return (
          <Button size="sm" onClick={() => handleAnalyze(filename)}>Analyze</Button>
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

            <div className="bg-white rounded-xl shadow-sm border border-secondary-200 overflow-hidden">
              {folder.files.length > 0 ? (
                <ul className="divide-y divide-secondary-100">
                  {folder.files.map(filename => (
                    <li key={filename} className="group p-4 hover:bg-secondary-50 transition-colors duration-200">
                      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                        <div className="flex items-start gap-4">
                          <div className="p-2 bg-primary-50 rounded-lg text-primary-600 group-hover:bg-primary-100 transition-colors">
                            <FileText className="w-6 h-6" />
                          </div>
                          <div>
                            <h3 className="font-medium text-secondary-900 break-all">{filename}</h3>
                            <div className="mt-1">
                              {getStatusBadge(processingStatus[filename] || 'idle')}
                            </div>
                          </div>
                        </div>

                        <div className="flex items-center gap-2 self-end sm:self-center">
                          {renderActionButton(filename)}
                          <button
                            onClick={() => handleDeleteClick(filename)}
                            className="p-2 text-secondary-400 hover:text-red-600 hover:bg-red-50 rounded-lg transition-all"
                            title="Delete file"
                          >
                            <Trash2 size={18} />
                          </button>
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
    </div>
  );
};

export default FolderWorkspace;
