
import axios, { AxiosError } from 'axios';
import { Folder, FolderDetails, ApiError, FileMetadata, SchemaResponse, ParseResponse, ExtractResponse } from '../types.ts';
import { API_BASE_URL } from '../constants.ts';

const apiClient = axios.create({
  baseURL: API_BASE_URL,
  timeout: 30000, // 30 seconds default timeout
});

// Extended timeout client for long-running operations (parsing, extraction)
// Extraction can take up to 8 minutes for large documents
const longRunningClient = axios.create({
  baseURL: API_BASE_URL,
  timeout: 900000, // 15 minutes for large document extraction
});

// Apply the same error interceptor to long-running client
const errorInterceptor = (error: AxiosError<ApiError>) => {
  const data = error.response?.data as any;

  // Pass through FastAPI validation errors (detail is an array)
  if (data && Array.isArray(data.detail)) {
    return Promise.reject(data as ApiError);
  }

  // Normalize FastAPI HTTPException(detail="...") where detail is a string
  if (data && typeof data.detail === 'string') {
    return Promise.reject({
      detail: [{ msg: data.detail }],
    } as ApiError);
  }

  // Fallback: network error or unexpected shape
  return Promise.reject({
    detail: [{ msg: error.message || 'An unexpected network error occurred.' }],
  } as ApiError);
};

longRunningClient.interceptors.response.use(response => response, errorInterceptor);

// Interceptor to handle API errors gracefully
apiClient.interceptors.response.use(response => response, errorInterceptor);

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

export const getProcessingStatus = async (folderId: string, filename: string) => {
  const encodedFilename = encodeURIComponent(filename);
  const { data } = await apiClient.get(`/process/${folderId}/${encodedFilename}/status`);
  return data;
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

export const isParsed = async (folderId: string, filename: string): Promise<boolean> => {
  try {
    const encodedFilename = encodeURIComponent(filename);
    const response = await apiClient.get<FileMetadata>(`/process/${folderId}/${encodedFilename}/metadata`);
    return response.data.has_markdown === true;
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

// --- Parse & Extract Workflow ---

export const parseFile = async (folderId: string, filename: string, forceReparse: boolean = false): Promise<ParseResponse> => {
  const encodedFilename = encodeURIComponent(filename);
  // Use long-running client for parsing (can take several minutes for large docs)
  const { data } = await longRunningClient.post<ParseResponse>(
    `/process/${folderId}/${encodedFilename}/parse`,
    null,
    { params: { force_reparse: forceReparse } }
  );
  return data;
};

export const getExtractionSchema = async (folderId: string, filename: string): Promise<SchemaResponse> => {
  const encodedFilename = encodeURIComponent(filename);
  const { data } = await apiClient.get<SchemaResponse>(`/process/${folderId}/${encodedFilename}/schema`);
  return data;
};

export const updateExtractionSchema = async (folderId: string, filename: string, schema: Record<string, unknown>): Promise<void> => {
  const encodedFilename = encodeURIComponent(filename);
  await apiClient.put(`/process/${folderId}/${encodedFilename}/schema`, { schema });
};

export const deleteExtractionSchema = async (folderId: string, filename: string): Promise<void> => {
  const encodedFilename = encodeURIComponent(filename);
  await apiClient.delete(`/process/${folderId}/${encodedFilename}/schema`);
};

export const extractTransactions = async (folderId: string, filename: string, useCustomSchema: boolean = true): Promise<ExtractResponse> => {
  const encodedFilename = encodeURIComponent(filename);
  // Use long-running client for extraction (can take up to 8 minutes for large docs)
  const { data } = await longRunningClient.post<ExtractResponse>(
    `/process/${folderId}/${encodedFilename}/extract`,
    null,
    { params: { use_custom_schema: useCustomSchema } }
  );
  return data;
};
