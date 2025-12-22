
export interface Folder {
  id: string;
  name: string;
  status: 'New' | 'Processing' | 'Complete';
  fileCount: number;
  file_count?: number;
}

export interface FolderDetails extends Folder {
  files: string[];
}

export type ApiError = {
  detail: { msg: string }[];
};

// Chunk bounding box coordinates (normalized 0-1)
export interface BoundingBox {
  left: number;
  top: number;
  right: number;
  bottom: number;
}

// Grounding info for a chunk (page + bounding box)
export interface ChunkGrounding {
  page: number;
  box?: BoundingBox;
}

// A single parsed chunk from ADE
export interface ParsedChunk {
  id?: string;
  markdown?: string;
  type?: 'text' | 'table' | 'image' | string;
  page_number?: number;
  grounding?: ChunkGrounding;
}

// File metadata response from /process/{folder_id}/{filename}/metadata
export interface FileMetadata {
  filename: string;
  chunks_count: number;
  pages_count: number;
  pages: number[];
  has_markdown: boolean;
  chunk_types: Record<string, number>;
  chunks: ParsedChunk[];
}

// Schema response from /process/{folder_id}/{filename}/schema
export interface SchemaResponse {
  schema: Record<string, unknown>;
  is_custom: boolean;
  message: string;
}

// Parse response from /process/{folder_id}/{filename}/parse
export interface ParseResponse {
  message: string;
  filename: string;
  chunks_count: number;
  pages_count: number;
  pages: number[];
  has_markdown: boolean;
  chunk_types: Record<string, number>;
  used_cache: boolean;
}

// Extract response from /process/{folder_id}/{filename}/extract
export interface ExtractResponse {
  message: string;
  output_file: string;
  transactions_count: number;
  used_custom_schema: boolean;
  csv_content: string;
}
