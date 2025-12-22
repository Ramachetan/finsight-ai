import { useState, useEffect, useCallback } from 'react';
import { Button } from './ui/Button.tsx';
import { Spinner } from './ui/Spinner.tsx';
import { Modal } from './ui/Modal.tsx';
import { ExtractResponse } from '../types.ts';
import {
    getExtractionSchema,
    updateExtractionSchema,
    deleteExtractionSchema,
    extractTransactions,
} from '../lib/api.ts';
import { useToast } from '../hooks/useToast.tsx';
import { Plus, Trash2, GripVertical, RotateCcw, Play, Save, ChevronDown, ChevronUp } from 'lucide-react';

interface SchemaField {
    name: string;
    type: 'string' | 'number' | 'boolean';
    description: string;
    required: boolean;
}

interface SchemaEditorProps {
    folderId: string;
    filename: string;
    onExtractionComplete?: (result: ExtractResponse) => void;
}

// Default fields for bank statement extraction
const DEFAULT_FIELDS: SchemaField[] = [
    { name: 'date', type: 'string', description: 'Date of the transaction (e.g., DD/MM/YYYY)', required: true },
    { name: 'amount', type: 'string', description: 'Transaction amount with sign (+/-)', required: true },
    { name: 'balance', type: 'string', description: 'Account balance after transaction', required: false },
    { name: 'remarks', type: 'string', description: 'Description or narration of the transaction', required: false },
    { name: 'transactionId', type: 'string', description: 'Reference number or transaction ID', required: false },
];

// Convert table fields to JSON Schema format
function fieldsToJsonSchema(fields: SchemaField[]): Record<string, unknown> {
    const properties: Record<string, unknown> = {};
    const required: string[] = [];

    fields.forEach(field => {
        properties[field.name] = {
            type: field.type,
            description: field.description,
            default: field.type === 'string' ? '' : (field.type === 'number' ? 0 : false),
        };
        if (field.required) {
            required.push(field.name);
        }
    });

    // Wrap in the transactions array structure expected by the backend
    return {
        type: 'object',
        properties: {
            transactions: {
                type: 'array',
                description: 'List of individual transaction records from the statement tables.',
                items: {
                    type: 'object',
                    properties,
                    required: required.length > 0 ? required : undefined,
                },
            },
        },
        required: ['transactions'],
        $defs: {},
    };
}

// Convert JSON Schema to table fields
function jsonSchemaToFields(schema: Record<string, unknown>): SchemaField[] {
    try {
        // Navigate to the transaction item properties
        const properties = schema.properties as Record<string, unknown> | undefined;
        if (!properties?.transactions) return DEFAULT_FIELDS;

        const transactions = properties.transactions as Record<string, unknown>;
        const items = transactions.items as Record<string, unknown> | undefined;
        if (!items?.properties) return DEFAULT_FIELDS;

        const itemProperties = items.properties as Record<string, unknown>;
        const requiredFields = (items.required as string[]) || [];

        const fields: SchemaField[] = [];

        for (const [name, prop] of Object.entries(itemProperties)) {
            const propObj = prop as Record<string, unknown>;
            fields.push({
                name,
                type: (propObj.type as 'string' | 'number' | 'boolean') || 'string',
                description: (propObj.description as string) || '',
                required: requiredFields.includes(name),
            });
        }

        return fields.length > 0 ? fields : DEFAULT_FIELDS;
    } catch (e) {
        console.error('Error parsing schema:', e);
        return DEFAULT_FIELDS;
    }
}

export default function SchemaEditorTable({
    folderId,
    filename,
    onExtractionComplete,
}: SchemaEditorProps) {
    const [fields, setFields] = useState<SchemaField[]>(DEFAULT_FIELDS);
    const [isLoading, setIsLoading] = useState(true);
    const [isSaving, setIsSaving] = useState(false);
    const [isExtracting, setIsExtracting] = useState(false);
    const [isCustom, setIsCustom] = useState(false);
    const [hasChanges, setHasChanges] = useState(false);
    const [showAdvanced, setShowAdvanced] = useState(false);
    const [rawSchema, setRawSchema] = useState<string>('');
    const [showSavePrompt, setShowSavePrompt] = useState(false);
    const { addToast } = useToast();

    // Fetch schema on mount
    const fetchSchema = useCallback(async () => {
        setIsLoading(true);
        try {
            const response = await getExtractionSchema(folderId, filename);
            const parsedFields = jsonSchemaToFields(response.schema);
            setFields(parsedFields);
            setIsCustom(response.is_custom);
            setRawSchema(JSON.stringify(response.schema, null, 2));
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

    // Update raw schema when fields change
    useEffect(() => {
        if (!isLoading) {
            const schema = fieldsToJsonSchema(fields);
            setRawSchema(JSON.stringify(schema, null, 2));
        }
    }, [fields, isLoading]);

    const handleFieldChange = (index: number, key: keyof SchemaField, value: string | boolean) => {
        setFields(prev => {
            const updated = [...prev];
            updated[index] = { ...updated[index], [key]: value };
            return updated;
        });
        setHasChanges(true);
    };

    const handleAddField = () => {
        setFields(prev => [
            ...prev,
            { name: '', type: 'string', description: '', required: false },
        ]);
        setHasChanges(true);
    };

    const handleRemoveField = (index: number) => {
        setFields(prev => prev.filter((_, i) => i !== index));
        setHasChanges(true);
    };

    const handleMoveField = (index: number, direction: 'up' | 'down') => {
        const newIndex = direction === 'up' ? index - 1 : index + 1;
        if (newIndex < 0 || newIndex >= fields.length) return;

        setFields(prev => {
            const updated = [...prev];
            [updated[index], updated[newIndex]] = [updated[newIndex], updated[index]];
            return updated;
        });
        setHasChanges(true);
    };

    // Save schema
    const handleSave = async () => {
        // Validate field names
        const emptyNames = fields.some(f => !f.name.trim());
        if (emptyNames) {
            addToast({ message: 'All fields must have a name', type: 'error' });
            return;
        }

        const duplicateNames = fields.length !== new Set(fields.map(f => f.name)).size;
        if (duplicateNames) {
            addToast({ message: 'Field names must be unique', type: 'error' });
            return;
        }

        setIsSaving(true);
        try {
            const schema = fieldsToJsonSchema(fields);
            await updateExtractionSchema(folderId, filename, schema);
            setIsCustom(true);
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
        if (!isCustom) {
            addToast({ message: 'Already using default schema', type: 'info' });
            return;
        }

        setIsSaving(true);
        try {
            await deleteExtractionSchema(folderId, filename);
            setFields(DEFAULT_FIELDS);
            setIsCustom(false);
            setHasChanges(false);
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
        // Prompt to save if there are unsaved changes
        if (hasChanges) {
            setShowSavePrompt(true);
            return;
        }

        setIsExtracting(true);
        try {
            const result = await extractTransactions(folderId, filename, true);
            addToast({
                message: `Successfully extracted ${result.transactions_count} transactions`,
                type: 'success'
            });
            onExtractionComplete?.(result);
        } catch (error) {
            console.error('Error extracting:', error);
            addToast({ message: 'Extraction failed. Please try again.', type: 'error' });
        } finally {
            setIsExtracting(false);
        }
    };

    // Handle save and proceed with extraction
    const handleSaveAndExtract = async () => {
        setShowSavePrompt(false);
        await handleSave();

        setIsExtracting(true);
        try {
            const result = await extractTransactions(folderId, filename, true);
            addToast({
                message: `Successfully extracted ${result.transactions_count} transactions`,
                type: 'success'
            });
            onExtractionComplete?.(result);
        } catch (error) {
            console.error('Error extracting:', error);
            addToast({ message: 'Extraction failed. Please try again.', type: 'error' });
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
            <div className="flex flex-wrap items-center justify-between gap-3 mb-4 px-1">
                <div className="flex items-center gap-3">
                    <span
                        className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${isCustom
                            ? 'bg-purple-100 text-purple-800'
                            : 'bg-gray-100 text-gray-800'
                            }`}
                    >
                        {isCustom ? 'Custom Schema' : 'Default Schema'}
                    </span>
                    {hasChanges && (
                        <span className="inline-flex items-center gap-1.5 px-2 py-0.5 bg-amber-50 border border-amber-200 rounded-full text-xs font-medium text-amber-700">
                            <span className="w-1.5 h-1.5 bg-amber-500 rounded-full animate-pulse"></span>
                            Unsaved changes
                        </span>
                    )}
                </div>

                <div className="flex items-center gap-2">
                    {isCustom && (
                        <Button
                            variant="secondary"
                            size="sm"
                            onClick={handleResetToDefault}
                            disabled={isSaving || isExtracting}
                        >
                            <RotateCcw size={14} className="mr-1.5" />
                            Reset
                        </Button>
                    )}
                    <Button
                        variant={hasChanges ? "primary" : "secondary"}
                        size="sm"
                        onClick={handleSave}
                        disabled={isSaving || isExtracting || !hasChanges}
                        className={hasChanges ? '' : 'bg-secondary-100 hover:bg-secondary-100 cursor-not-allowed'}
                    >
                        {isSaving ? (
                            <>
                                <Spinner className="w-4 h-4 mr-1.5" />
                                Saving...
                            </>
                        ) : (
                            <>
                                <Save size={14} className="mr-1.5" />
                                Save
                            </>
                        )}
                    </Button>
                    <Button
                        variant="primary"
                        size="sm"
                        onClick={handleExtract}
                        disabled={isExtracting}
                    >
                        {isExtracting ? (
                            <>
                                <Spinner className="w-4 h-4 mr-1.5" />
                                Extracting...
                            </>
                        ) : (
                            <>
                                <Play size={14} className="mr-1.5" />
                                Extract Transactions
                            </>
                        )}
                    </Button>
                </div>
            </div>

            {/* Instructions */}
            <div className="mb-4 p-3 bg-blue-50 border border-blue-100 rounded-lg text-sm text-blue-800">
                <strong>Define extraction fields:</strong> Specify which data points to extract from the parsed document.
                Each field will become a column in your CSV output.
            </div>

            {/* Field Table */}
            <div className="flex-1 overflow-auto">
                <table className="w-full border-collapse">
                    <thead className="sticky top-0 bg-secondary-50 z-10">
                        <tr>
                            <th className="w-8 p-2"></th>
                            <th className="p-2 text-left text-xs font-semibold text-secondary-600 uppercase tracking-wider">
                                Field Name
                            </th>
                            <th className="p-2 text-left text-xs font-semibold text-secondary-600 uppercase tracking-wider w-28">
                                Type
                            </th>
                            <th className="p-2 text-left text-xs font-semibold text-secondary-600 uppercase tracking-wider">
                                Description (helps AI understand what to extract)
                            </th>
                            <th className="p-2 text-center text-xs font-semibold text-secondary-600 uppercase tracking-wider w-20">
                                Required
                            </th>
                            <th className="w-10 p-2"></th>
                        </tr>
                    </thead>
                    <tbody className="divide-y divide-secondary-100">
                        {fields.map((field, index) => (
                            <tr key={index} className="group hover:bg-secondary-50">
                                <td className="p-2 text-center">
                                    <div className="flex flex-col gap-0.5">
                                        <button
                                            onClick={() => handleMoveField(index, 'up')}
                                            disabled={index === 0}
                                            className="p-0.5 text-secondary-400 hover:text-secondary-600 disabled:opacity-30"
                                        >
                                            <ChevronUp size={14} />
                                        </button>
                                        <GripVertical size={14} className="text-secondary-300 mx-auto" />
                                        <button
                                            onClick={() => handleMoveField(index, 'down')}
                                            disabled={index === fields.length - 1}
                                            className="p-0.5 text-secondary-400 hover:text-secondary-600 disabled:opacity-30"
                                        >
                                            <ChevronDown size={14} />
                                        </button>
                                    </div>
                                </td>
                                <td className="p-2">
                                    <input
                                        type="text"
                                        value={field.name}
                                        onChange={(e) => handleFieldChange(index, 'name', e.target.value)}
                                        className="w-full px-2 py-1.5 text-sm border border-secondary-200 rounded focus:outline-none focus:ring-1 focus:ring-primary-500 focus:border-primary-500"
                                        placeholder="e.g., amount"
                                    />
                                </td>
                                <td className="p-2">
                                    <select
                                        value={field.type}
                                        onChange={(e) => handleFieldChange(index, 'type', e.target.value)}
                                        className="w-full px-2 py-1.5 text-sm border border-secondary-200 rounded focus:outline-none focus:ring-1 focus:ring-primary-500 focus:border-primary-500 bg-white"
                                    >
                                        <option value="string">Text</option>
                                        <option value="number">Number</option>
                                        <option value="boolean">Yes/No</option>
                                    </select>
                                </td>
                                <td className="p-2">
                                    <input
                                        type="text"
                                        value={field.description}
                                        onChange={(e) => handleFieldChange(index, 'description', e.target.value)}
                                        className="w-full px-2 py-1.5 text-sm border border-secondary-200 rounded focus:outline-none focus:ring-1 focus:ring-primary-500 focus:border-primary-500"
                                        placeholder="Describe what this field captures..."
                                    />
                                </td>
                                <td className="p-2 text-center">
                                    <input
                                        type="checkbox"
                                        checked={field.required}
                                        onChange={(e) => handleFieldChange(index, 'required', e.target.checked)}
                                        className="w-4 h-4 text-primary-600 border-secondary-300 rounded focus:ring-primary-500"
                                    />
                                </td>
                                <td className="p-2">
                                    <button
                                        onClick={() => handleRemoveField(index)}
                                        className="p-1.5 text-secondary-400 hover:text-red-600 hover:bg-red-50 rounded transition-colors opacity-0 group-hover:opacity-100"
                                        title="Remove field"
                                    >
                                        <Trash2 size={16} />
                                    </button>
                                </td>
                            </tr>
                        ))}
                    </tbody>
                </table>

                {/* Add Field Button */}
                <button
                    onClick={handleAddField}
                    className="w-full mt-2 p-2 border-2 border-dashed border-secondary-200 rounded-lg text-secondary-500 hover:text-primary-600 hover:border-primary-300 hover:bg-primary-50 transition-colors flex items-center justify-center gap-2"
                >
                    <Plus size={16} />
                    Add Field
                </button>
            </div>

            {/* Advanced: Raw JSON Toggle */}
            <div className="mt-4 border-t border-secondary-200 pt-4">
                <button
                    onClick={() => setShowAdvanced(!showAdvanced)}
                    className="flex items-center gap-2 text-sm text-secondary-500 hover:text-secondary-700"
                >
                    {showAdvanced ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
                    {showAdvanced ? 'Hide' : 'Show'} Raw JSON Schema
                </button>

                {showAdvanced && (
                    <pre className="mt-2 p-3 bg-secondary-50 border border-secondary-200 rounded-lg text-xs font-mono overflow-auto max-h-48 text-secondary-600">
                        {rawSchema}
                    </pre>
                )}
            </div>

            {/* Save Confirmation Dialog */}
            <Modal
                isOpen={showSavePrompt}
                onClose={() => setShowSavePrompt(false)}
                title="Unsaved Changes"
            >
                <div className="space-y-4">
                    <p className="text-secondary-600">
                        You have unsaved changes to your extraction schema. Would you like to save them before extracting?
                    </p>
                    <div className="flex gap-3 justify-end">
                        <Button
                            variant="secondary"
                            onClick={() => setShowSavePrompt(false)}
                        >
                            Cancel
                        </Button>
                        <Button
                            variant="secondary"
                            onClick={() => {
                                setShowSavePrompt(false);
                                // Proceed with extraction without saving
                                setIsExtracting(true);
                                extractTransactions(folderId, filename, true)
                                    .then(result => {
                                        addToast({
                                            message: `Successfully extracted ${result.transactions_count} transactions`,
                                            type: 'success'
                                        });
                                        onExtractionComplete?.(result);
                                    })
                                    .catch(error => {
                                        console.error('Error extracting:', error);
                                        addToast({ message: 'Extraction failed. Please try again.', type: 'error' });
                                    })
                                    .finally(() => setIsExtracting(false));
                            }}
                        >
                            Extract Without Saving
                        </Button>
                        <Button
                            variant="primary"
                            onClick={handleSaveAndExtract}
                            disabled={isSaving}
                        >
                            {isSaving ? (
                                <>
                                    <Spinner className="w-4 h-4 mr-1.5" />
                                    Saving...
                                </>
                            ) : (
                                'Save and Extract'
                            )}
                        </Button>
                    </div>
                </div>
            </Modal>
        </div>
    );
}
