
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
