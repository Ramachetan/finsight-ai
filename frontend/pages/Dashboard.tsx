
import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { Folder as FolderType } from '../types.ts';
import * as api from '../lib/api.ts';
import { useToast } from '../hooks/useToast.tsx';
import { Card } from '../components/ui/Card.tsx';
import { Button } from '../components/ui/Button.tsx';
import { Modal } from '../components/ui/Modal.tsx';
import { Skeleton } from '../components/ui/Skeleton.tsx';
import { Plus, Folder, FileText, Trash2 } from 'lucide-react';

const Dashboard: React.FC = () => {
  const [folders, setFolders] = useState<FolderType[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [newFolderName, setNewFolderName] = useState('');
  const [isCreating, setIsCreating] = useState(false);
  const [selectedFolderIds, setSelectedFolderIds] = useState<Set<string>>(new Set());
  const navigate = useNavigate();
  const { addToast } = useToast();

  const fetchFolders = useCallback(async () => {
    setIsLoading(true);
    try {
      const data = await api.listFolders();
      setFolders(data);
    } catch (error) {
      addToast({ message: 'Failed to load projects.', type: 'error' });
    } finally {
      setIsLoading(false);
    }
  }, [addToast]);

  useEffect(() => {
    fetchFolders();
  }, [fetchFolders]);

  const handleCreateFolder = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newFolderName.trim()) {
      addToast({ message: 'Project name cannot be empty.', type: 'error' });
      return;
    }
    setIsCreating(true);
    try {
      await api.createFolder(newFolderName);
      addToast({ message: `Project "${newFolderName}" created.`, type: 'success' });
      setNewFolderName('');
      setIsModalOpen(false);
      fetchFolders();
    } catch (error: any) {
      addToast({ message: error.detail?.[0]?.msg || 'Failed to create project.', type: 'error' });
    } finally {
      setIsCreating(false);
    }
  };

  const handleDeleteFolder = async (e: React.MouseEvent, folderId: string, folderName: string) => {
    e.stopPropagation();
    if (window.confirm(`Are you sure you want to delete the project "${folderName}"?`)) {
      try {
        await api.deleteFolder(folderId);
        addToast({ message: `Project "${folderName}" deleted.`, type: 'success' });

        // Remove from selection if present
        setSelectedFolderIds(prev => {
          const newSet = new Set(prev);
          newSet.delete(folderId);
          return newSet;
        });

        fetchFolders();
      } catch (error: any) {
        addToast({ message: error.detail?.[0]?.msg || 'Failed to delete project.', type: 'error' });
      }
    }
  };

  const toggleSelection = (e: React.MouseEvent, folderId: string) => {
    e.stopPropagation();
    setSelectedFolderIds(prev => {
      const newSet = new Set(prev);
      if (newSet.has(folderId)) {
        newSet.delete(folderId);
      } else {
        newSet.add(folderId);
      }
      return newSet;
    });
  };

  const handleBulkDelete = async () => {
    if (selectedFolderIds.size === 0) return;

    if (window.confirm(`Are you sure you want to delete ${selectedFolderIds.size} projects?`)) {
      try {
        await Promise.all(Array.from(selectedFolderIds).map(id => api.deleteFolder(id)));
        addToast({ message: `${selectedFolderIds.size} projects deleted.`, type: 'success' });
        setSelectedFolderIds(new Set());
        fetchFolders();
      } catch (error: any) {
        addToast({ message: 'Failed to delete some projects.', type: 'error' });
        fetchFolders();
      }
    }
  };

  const toggleSelectAll = () => {
    if (selectedFolderIds.size === folders.length && folders.length > 0) {
      setSelectedFolderIds(new Set());
    } else {
      setSelectedFolderIds(new Set(folders.map(f => f.id)));
    }
  };

  const renderSkeletons = () => (
    Array.from({ length: 3 }).map((_, i) => (
      <Card key={i} className="p-6 relative min-h-[160px] flex flex-col justify-center">
        <div className="absolute top-4 right-4">
          <Skeleton className="h-5 w-5 rounded" />
        </div>
        <div className="flex items-center gap-5 pr-12">
          <Skeleton className="h-16 w-16 rounded-xl" />
          <div className="flex-1">
            <Skeleton className="h-7 w-3/4 mb-3" />
            <Skeleton className="h-5 w-1/4" />
          </div>
        </div>
      </Card>
    ))
  );

  return (
    <div className="container mx-auto p-4 sm:p-6 lg:p-8">
      {/* Hero Section */}
      <div className="mb-8 text-center">
        <div className="inline-block">
          <h1 className="text-4xl sm:text-5xl font-bold mb-4 text-primary-900">
            Your Projects
          </h1>
          <div className="h-1 bg-gradient-to-r from-primary-600 to-primary-400 rounded-full"></div>
        </div>
        <p className="mt-4 text-secondary-600 text-lg max-w-2xl mx-auto">
          Manage and analyze bank statements with AI-powered insights
        </p>
      </div>

      <header className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-4">
          <div className="text-sm text-secondary-600">
            <span className="font-semibold text-2xl text-secondary-900">{folders.length}</span>
            <span className="ml-2">Total Projects</span>
          </div>
        </div>
        <div className="flex gap-3">
          {selectedFolderIds.size > 0 && (
            <Button variant="danger" onClick={handleBulkDelete}>
              <Trash2 size={18} className="mr-2" />
              Delete Selected ({selectedFolderIds.size})
            </Button>
          )}
          <Button variant="primary" onClick={() => setIsModalOpen(true)}>
            <Plus size={18} className="mr-2" />
            New Project
          </Button>
        </div>
      </header>

      <main>
        {folders.length > 0 && (
          <div className="flex items-center mb-6 pl-1 bg-secondary-50/50 p-2 rounded-lg w-fit">
            <input
              type="checkbox"
              id="selectAll"
              className="w-4 h-4 rounded border-secondary-300 text-primary-600 focus:ring-primary-500 mr-2.5 cursor-pointer"
              checked={folders.length > 0 && selectedFolderIds.size === folders.length}
              onChange={toggleSelectAll}
            />
            <label htmlFor="selectAll" className="text-secondary-600 cursor-pointer select-none text-sm font-semibold uppercase tracking-wider">
              Select All
            </label>
          </div>
        )}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
          {isLoading ? renderSkeletons() : folders.map(folder => (
            <Card key={folder.id} onClick={() => navigate(`/folder/${folder.id}`)} className="group h-full">
              <div className="p-6 relative min-h-[160px] flex flex-col justify-center h-full">
                <div className="absolute top-4 right-4 flex items-center gap-1">
                  <button
                    onClick={(e) => handleDeleteFolder(e, folder.id, folder.name)}
                    className="text-secondary-400 hover:text-red-600 hover:bg-red-50 p-1.5 rounded-md transition-all opacity-0 group-hover:opacity-100 focus:opacity-100"
                    aria-label={`Delete folder ${folder.name}`}
                  >
                    <Trash2 size={16} />
                  </button>
                  <div onClick={(e) => e.stopPropagation()} className="flex items-center ml-1">
                    <input
                      type="checkbox"
                      className="w-4 h-4 rounded border-secondary-300 text-primary-600 focus:ring-primary-500 cursor-pointer transition-transform group-hover:scale-110"
                      checked={selectedFolderIds.has(folder.id)}
                      onChange={(e) => toggleSelection(e as any, folder.id)}
                    />
                  </div>
                </div>

                <div className="flex items-center gap-5 pr-12">
                  <div className="p-4 bg-primary-50 rounded-xl group-hover:bg-primary-100 transition-colors duration-300 shadow-sm">
                    <Folder className="w-10 h-10 text-primary-600" />
                  </div>
                  <div className="min-w-0 flex-1">
                    <h2 className="text-xl font-bold text-secondary-900 truncate group-hover:text-primary-700 transition-colors leading-tight" title={folder.name}>
                      {folder.name}
                    </h2>
                    <div className="flex items-center text-sm text-secondary-500 mt-2">
                      <FileText size={14} className="mr-2 text-secondary-400" />
                      <span className="font-medium">{folder.fileCount || folder.file_count || 0} files</span>
                    </div>
                  </div>
                </div>
              </div>
            </Card>
          ))}
        </div>
        {!isLoading && folders.length === 0 && (
          <div className="text-center py-20 bg-white rounded-lg shadow-md">
            <Folder size={48} className="mx-auto text-secondary-300" />
            <h3 className="mt-4 text-lg font-semibold text-secondary-800">No projects yet</h3>
            <p className="mt-1 text-sm text-secondary-500">Get started by creating a new project.</p>
          </div>
        )}
      </main>

      <Modal isOpen={isModalOpen} onClose={() => setIsModalOpen(false)} title="Create New Project">
        <form onSubmit={handleCreateFolder}>
          <div className="space-y-4">
            <div>
              <label htmlFor="folderName" className="block text-sm font-medium text-secondary-700">
                Project Name
              </label>
              <input
                type="text"
                id="folderName"
                value={newFolderName}
                onChange={e => setNewFolderName(e.target.value)}
                className="mt-1 block w-full px-3 py-2 border border-secondary-300 rounded-md shadow-sm focus:outline-none focus:ring-primary-500 focus:border-primary-500 sm:text-sm"
                placeholder="e.g., My Bank Statements"
                required
              />
            </div>
            <div className="flex justify-end gap-3 pt-2">
              <Button type="button" variant="secondary" onClick={() => setIsModalOpen(false)}>
                Cancel
              </Button>
              <Button type="submit" disabled={isCreating}>
                {isCreating ? 'Creating...' : 'Create Project'}
              </Button>
            </div>
          </div>
        </form>
      </Modal>
    </div>
  );
};

export default Dashboard;
