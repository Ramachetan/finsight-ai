import React, { useCallback } from 'react';
import { useDropzone } from 'react-dropzone';
import { UploadCloud, File as FileIcon, Loader } from 'lucide-react';

interface FileUploaderProps {
  onUpload: (files: File[]) => void;
  isUploading: boolean;
}

const FileUploader: React.FC<FileUploaderProps> = ({ onUpload, isUploading }) => {
  const onDrop = useCallback((acceptedFiles: File[]) => {
    if (acceptedFiles.length > 0) {
      onUpload(acceptedFiles);
    }
  }, [onUpload]);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: { 'application/pdf': ['.pdf'] },
    disabled: isUploading,
  });

  return (
    <div
      {...getRootProps()}
      className={`
        relative border-2 border-dashed rounded-2xl p-10 text-center cursor-pointer transition-all duration-300 overflow-hidden
        ${isDragActive ? 'border-primary-500 bg-primary-50 scale-105 shadow-lg' : 'border-secondary-300 bg-white shadow-md'}
        ${isUploading ? 'cursor-not-allowed bg-secondary-50' : 'hover:border-primary-400 hover:shadow-xl hover:scale-102'}
      `}
    >
      <input {...getInputProps()} />

      {/* Animated background gradient on drag */}
      {isDragActive && (
        <div className="absolute inset-0 bg-gradient-to-r from-primary-100 via-purple-100 to-primary-100 opacity-50 animate-pulse"></div>
      )}

      <div className="relative z-10">
        {isUploading ? (
          <div className="flex flex-col items-center justify-center text-secondary-600">
            <div className="relative">
              <Loader className="animate-spin text-primary-600" size={48} />
              <div className="absolute inset-0 animate-ping">
                <Loader className="text-primary-300" size={48} />
              </div>
            </div>
            <p className="font-semibold mt-4 text-lg">Uploading...</p>
            <p className="text-sm text-secondary-500 mt-1">Please wait while we process your files.</p>
          </div>
        ) : (
          <div className="flex flex-col items-center justify-center text-secondary-600">
            <div className={`transition-all duration-300 ${isDragActive ? 'scale-110 rotate-6' : ''}`}>
              <div className="relative">
                <UploadCloud className={`text-primary-500 transition-all duration-300 ${isDragActive ? 'animate-bounce' : ''}`} size={56} />
                {isDragActive && (
                  <div className="absolute inset-0 bg-primary-400 rounded-full blur-xl opacity-50 animate-pulse"></div>
                )}
              </div>
            </div>
            <p className="font-bold text-lg mt-4 text-secondary-800">
              {isDragActive ? 'Drop your files here!' : 'Drag & drop bank statements'}
            </p>
            <p className="text-sm text-secondary-500 mt-2">
              or <span className="text-primary-600 font-semibold">click to browse</span> (PDF only)
            </p>
            <div className="mt-4 flex items-center gap-2 text-xs text-secondary-400">
              <FileIcon size={14} />
              <span>Supports PDF documents</span>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default FileUploader;
