
import axios, { AxiosError } from 'axios';
import { Folder, FolderDetails, ApiError, FileMetadata } from '../types.ts';
import { API_BASE_URL } from '../constants.ts';

const apiClient = axios.create({
  baseURL: API_BASE_URL,
});

// Interceptor to handle API errors gracefully
apiClient.interceptors.response.use(
  response => response,
  (error: AxiosError<ApiError>) => {
    // Handle structured API errors (e.g., 422 Unprocessable Entity)
    if (error.response && error.response.data && Array.isArray(error.response.data.detail)) {
      return Promise.reject(error.response.data);
    }

    // Handle generic network or server errors
    return Promise.reject({
      detail: [{ msg: error.message || 'An unexpected network error occurred.' }],
    } as ApiError);
  }
);

// --- Folder Management ---

export const listFolders = async (): Promise<Folder[]> => {
  const { data } = await apiClient.get<Folder[]>('/folders/');
  return data;
};

export const createFolder = async (name: string): Promise<Folder> => {
  const { data } = await apiClient.post<Folder>('/folders/', { name });
  return data;
};

export const getFolderDetails = async (folderId: string): Promise<FolderDetails> => {
  const { data } = await apiClient.get<FolderDetails>(`/folders/${folderId}`);
  return data;
};

export const deleteFolder = async (folderId: string): Promise<void> => {
  await apiClient.delete(`/folders/${folderId}`);
};

// --- File Operations ---

export const uploadFiles = async (folderId: string, files: File[]): Promise<void> => {
  const formData = new FormData();
  files.forEach(file => {
    formData.append('files', file, file.name);
  });

  await apiClient.post(`/folders/${folderId}/upload`, formData, {
    headers: {
      'Content-Type': 'multipart/form-data',
    },
  });
};

export const startProcessing = async (folderId: string, filename: string): Promise<void> => {
  await apiClient.post(`/process/${folderId}/${filename}`);
};

export const downloadResult = async (folderId: string, filename: string): Promise<Blob> => {
  const response = await apiClient.get(`/process/${folderId}/${filename}/download`, {
    responseType: 'blob',
  });
  return response.data;
};

export const getOriginalFile = async (folderId: string, filename: string): Promise<Blob> => {
  const encodedFilename = encodeURIComponent(filename);
  const response = await apiClient.get(`/folders/${folderId}/files/${encodedFilename}`, {
    responseType: 'blob',
  });
  return response.data;
}

export const isProcessed = async (folderId: string, filename: string): Promise<boolean> => {
  try {
    const processedFilename = `${filename}.csv`;
    const encodedFilename = encodeURIComponent(processedFilename);
    const response = await apiClient.head(`/process/${folderId}/${encodedFilename}/download`);
    return response.status === 200;
  } catch (error) {
    return false;
  }
};

export const deleteFile = async (folderId: string, filename: string): Promise<void> => {
  const encodedFilename = encodeURIComponent(filename);
  await apiClient.delete(`/folders/${folderId}/files/${encodedFilename}`);
};

export const getFileMetadata = async (folderId: string, filename: string): Promise<FileMetadata> => {
  const encodedFilename = encodeURIComponent(filename);
  const { data } = await apiClient.get<FileMetadata>(`/process/${folderId}/${encodedFilename}/metadata`);
  return data;
};

export const getFileMarkdown = async (folderId: string, filename: string): Promise<string> => {
  const encodedFilename = encodeURIComponent(filename);
  const { data } = await apiClient.get(`/process/${folderId}/${encodedFilename}/markdown`);
  return data;
};
