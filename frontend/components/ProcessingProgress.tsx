import React, { useEffect, useState } from 'react';
import { getProcessingStatus } from '../lib/api';

interface ProcessingProgressProps {
    folderId: string;
    filename: string;
    onComplete: () => void;
}

export default function ProcessingProgress({ folderId, filename, onComplete }: ProcessingProgressProps) {
    const [status, setStatus] = useState<{
        phase: string | null;
        message: string;
        progress: number;
    }>({
        phase: 'Parsing',
        message: 'Starting...',
        progress: 0,
    });

    useEffect(() => {
        // Stop polling if not processing
        if (status.phase === null) {
            onComplete();
            return;
        }

        const interval = setInterval(async () => {
            try {
                const newStatus = await getProcessingStatus(folderId, filename);
                setStatus(newStatus);

                if (newStatus.phase === null) {
                    onComplete();
                }
            } catch (error) {
                console.error('Error fetching status:', error);
            }
        }, 500);

        return () => clearInterval(interval);
    }, [status.phase, folderId, filename, onComplete]);

    return (
        <div className="w-full space-y-2">
            <div className="flex justify-between items-center">
                <span className="text-sm font-medium text-secondary-700">
                    {status.phase || 'Processing'}
                </span>
                <span className="text-sm text-secondary-600">{status.progress}%</span>
            </div>
            <div className="w-full bg-secondary-200 rounded-full h-2">
                <div
                    className="bg-primary-500 h-2 rounded-full transition-all duration-300"
                    style={{ width: `${status.progress}%` }}
                />
            </div>
            <p className="text-xs text-secondary-600">{status.message}</p>
        </div>
    );
}
