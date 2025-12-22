import { useState, useEffect, useCallback } from 'react';
import { Button } from './ui/Button.tsx';
import { Spinner } from './ui/Spinner.tsx';
import { SchemaResponse, ExtractResponse } from '../types.ts';
import {
    getExtractionSchema,
    updateExtractionSchema,
    deleteExtractionSchema,
    extractTransactions,
} from '../lib/api.ts';
import { useToast } from '../hooks/useToast.tsx';

interface SchemaEditorProps {
    folderId: string;
    filename: string;
    onExtractionComplete?: (result: ExtractResponse) => void;
}

export default function SchemaEditor({
    folderId,
    filename,
    onExtractionComplete,
}: SchemaEditorProps) {
    const [schemaData, setSchemaData] = useState<SchemaResponse | null>(null);
    const [editedSchema, setEditedSchema] = useState<string>('');
    const [isLoading, setIsLoading] = useState(true);
    const [isSaving, setIsSaving] = useState(false);
    const [isExtracting, setIsExtracting] = useState(false);
    const [parseError, setParseError] = useState<string | null>(null);
    const [hasChanges, setHasChanges] = useState(false);
    const { addToast } = useToast();

    // Fetch schema on mount
    const fetchSchema = useCallback(async () => {
        setIsLoading(true);
        try {
            const response = await getExtractionSchema(folderId, filename);
            setSchemaData(response);
            setEditedSchema(JSON.stringify(response.schema, null, 2));
            setParseError(null);
            setHasChanges(false);
        } catch (error) {
            console.error('Error fetching schema:', error);
            addToast({ message: 'Failed to load extraction schema', type: 'error' });
        } finally {
            setIsLoading(false);
        }
    }, [folderId, filename, addToast]);

    useEffect(() => {
        fetchSchema();
    }, [fetchSchema]);

    // Validate JSON on change
    const handleSchemaChange = (value: string) => {
        setEditedSchema(value);
        setHasChanges(true);

        try {
            JSON.parse(value);
            setParseError(null);
        } catch (e) {
            if (e instanceof Error) {
                setParseError(e.message);
            } else {
                setParseError('Invalid JSON');
            }
        }
    };

    // Save schema
    const handleSave = async () => {
        if (parseError) {
            addToast({ message: 'Please fix JSON errors before saving', type: 'error' });
            return;
        }

        setIsSaving(true);
        try {
            const schema = JSON.parse(editedSchema);
            await updateExtractionSchema(folderId, filename, schema);
            setSchemaData((prev) => prev ? { ...prev, is_custom: true, schema } : null);
            setHasChanges(false);
            addToast({ message: 'Schema saved successfully', type: 'success' });
        } catch (error) {
            console.error('Error saving schema:', error);
            addToast({ message: 'Failed to save schema', type: 'error' });
        } finally {
            setIsSaving(false);
        }
    };

    // Reset to default schema
    const handleResetToDefault = async () => {
        if (!schemaData?.is_custom) {
            addToast({ message: 'Already using default schema', type: 'info' });
            return;
        }

        setIsSaving(true);
        try {
            await deleteExtractionSchema(folderId, filename);
            await fetchSchema(); // Reload the default schema
            addToast({ message: 'Reset to default schema', type: 'success' });
        } catch (error) {
            console.error('Error resetting schema:', error);
            addToast({ message: 'Failed to reset schema', type: 'error' });
        } finally {
            setIsSaving(false);
        }
    };

    // Extract with current schema
    const handleExtract = async () => {
        // Save if there are unsaved changes
        if (hasChanges && !parseError) {
            await handleSave();
        }

        setIsExtracting(true);
        try {
            const result = await extractTransactions(folderId, filename, true);
            addToast({
                message: `Extracted ${result.transactions_count} transactions`,
                type: 'success'
            });
            onExtractionComplete?.(result);
        } catch (error) {
            console.error('Error extracting:', error);
            addToast({ message: 'Extraction failed', type: 'error' });
        } finally {
            setIsExtracting(false);
        }
    };

    if (isLoading) {
        return (
            <div className="flex items-center justify-center py-12">
                <Spinner />
                <span className="ml-3 text-secondary-600">Loading schema...</span>
            </div>
        );
    }

    return (
        <div className="flex flex-col h-full">
            {/* Header with status and actions */}
            <div className="flex items-center justify-between mb-4 px-1">
                <div className="flex items-center gap-3">
                    <span
                        className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${schemaData?.is_custom
                                ? 'bg-purple-100 text-purple-800'
                                : 'bg-gray-100 text-gray-800'
                            }`}
                    >
                        {schemaData?.is_custom ? 'Custom Schema' : 'Default Schema'}
                    </span>
                    {hasChanges && (
                        <span className="text-xs text-amber-600 font-medium">
                            Unsaved changes
                        </span>
                    )}
                    {parseError && (
                        <span className="text-xs text-red-600 font-medium">
                            JSON Error
                        </span>
                    )}
                </div>

                <div className="flex items-center gap-2">
                    {schemaData?.is_custom && (
                        <Button
                            variant="secondary"
                            size="sm"
                            onClick={handleResetToDefault}
                            disabled={isSaving || isExtracting}
                        >
                            Reset to Default
                        </Button>
                    )}
                    <Button
                        variant="secondary"
                        size="sm"
                        onClick={handleSave}
                        disabled={isSaving || isExtracting || !!parseError || !hasChanges}
                    >
                        {isSaving ? (
                            <>
                                <Spinner className="w-4 h-4 mr-2" />
                                Saving...
                            </>
                        ) : (
                            'Save Schema'
                        )}
                    </Button>
                    <Button
                        variant="primary"
                        size="sm"
                        onClick={handleExtract}
                        disabled={isExtracting || !!parseError}
                    >
                        {isExtracting ? (
                            <>
                                <Spinner className="w-4 h-4 mr-2" />
                                Extracting...
                            </>
                        ) : (
                            'Extract Transactions'
                        )}
                    </Button>
                </div>
            </div>

            {/* JSON Editor */}
            <div className="flex-1 relative">
                <textarea
                    className={`w-full h-full min-h-[400px] p-4 font-mono text-sm border rounded-lg resize-none focus:outline-none focus:ring-2 ${parseError
                            ? 'border-red-300 focus:ring-red-500 bg-red-50'
                            : 'border-secondary-200 focus:ring-primary-500 bg-white'
                        }`}
                    value={editedSchema}
                    onChange={(e) => handleSchemaChange(e.target.value)}
                    spellCheck={false}
                    placeholder="JSON Schema..."
                />
                {parseError && (
                    <div className="absolute bottom-2 left-2 right-2 px-3 py-2 bg-red-100 border border-red-300 rounded text-xs text-red-700">
                        <strong>Parse Error:</strong> {parseError}
                    </div>
                )}
            </div>

            {/* Help text */}
            <p className="text-xs text-secondary-500 mt-3 px-1">
                Edit the JSON Schema above to customize what data is extracted from the
                parsed document. Changes will be used on next extraction.
            </p>
        </div>
    );
}
