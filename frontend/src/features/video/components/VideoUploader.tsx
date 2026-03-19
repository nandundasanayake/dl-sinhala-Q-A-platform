// src/features/video/components/VideoUploader.tsx
import React, { useState, useEffect } from 'react';
import { Upload, X, Loader2, CheckCircle, AlertCircle, PlayCircle, FileVideo } from 'lucide-react';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Progress } from '@/components/ui/progress';
import { useVideoStore } from '@/store/video.store';
import { cn } from '@/lib/utils';

interface VideoUploaderProps {
  isOpen: boolean;
  onClose: () => void;
  onUploadComplete?: (videoId: string) => void;
}

export const VideoUploader: React.FC<VideoUploaderProps> = ({
  isOpen,
  onClose,
  onUploadComplete,
}) => {
  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState('');
  const [uploadStatus, setUploadStatus] = useState<'idle' | 'uploading' | 'processing' | 'success' | 'error'>('idle');
  const [progress, setProgress] = useState(0);
  const [errorMessage, setErrorMessage] = useState('');
  const [isDragging, setIsDragging] = useState(false);
  const { addVideo } = useVideoStore();

  // Reset form when dialog closes
  useEffect(() => {
    if (!isOpen) {
      setTimeout(() => {
        setFile(null);
        setTitle('');
        setUploadStatus('idle');
        setProgress(0);
        setErrorMessage('');
      }, 200);
    }
  }, [isOpen]);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const selected = e.target.files?.[0];
    if (selected) {
      setFile(selected);
      if (!title) {
        setTitle(selected.name.replace(/\.[^/.]+$/, ''));
      }
    }
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    
    const droppedFile = e.dataTransfer.files[0];
    if (droppedFile && droppedFile.type.startsWith('video/')) {
      setFile(droppedFile);
      if (!title) {
        setTitle(droppedFile.name.replace(/\.[^/.]+$/, ''));
      }
    }
  };

  const handleUpload = async () => {
    if (!file) return;

    setUploadStatus('uploading');
    setProgress(0);
    setErrorMessage('');

    const formData = new FormData();
    formData.append('file', file);

    try {
      const interval = setInterval(() => {
        setProgress(prev => {
          if (prev >= 90) {
            clearInterval(interval);
            return 90;
          }
          return prev + 10;
        });
      }, 500);

      const response = await fetch('http://localhost:8000/api/upload-video', {
        method: 'POST',
        body: formData,
      });

      clearInterval(interval);
      setProgress(100);
      setUploadStatus('processing');

      const data = await response.json();

      if (response.ok) {
        setUploadStatus('success');

        // Generate a truly unique ID
        const uniqueId = `${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
        
        console.log('✅ Upload successful:', {
            videoId: uniqueId,
            s3Url: data.video_s3_url,
            filename: file.name
        });
        
        addVideo({
        //   id: data.video_id,
          id:uniqueId,
          originalVideoId: data.video_id,
          title: title || file.name,
          fileName: file.name,
          uploadedAt: new Date(),
          duration: data.duration || '00:00',
          thumbnail: data.thumbnail_url,
          status: 'ready',
          s3Url: data.video_s3_url,
          transcriptUrl: data.transcript_s3_url,
        });

        setTimeout(() => {
          onClose();
          onUploadComplete?.(data.video_id);
        }, 1500);
      } else {
        setUploadStatus('error');
        setErrorMessage(data.detail || 'Upload failed');
      }
    } catch (error) {
      setUploadStatus('error');
      setErrorMessage('Network error. Please check your connection.');
    }
  };

  const getStatusDisplay = () => {
    switch (uploadStatus) {
      case 'uploading':
        return {
          icon: <Loader2 className="w-5 h-5 animate-spin text-dopamine-accent" />,
          text: `Uploading... ${progress}%`,
          bgColor: 'bg-blue-50',
          textColor: 'text-blue-700',
          borderColor: 'border-blue-200'
        };
      case 'processing':
        return {
          icon: <Loader2 className="w-5 h-5 animate-spin text-dopamine-accent" />,
          text: 'Generating transcript & embeddings...',
          bgColor: 'bg-purple-50',
          textColor: 'text-purple-700',
          borderColor: 'border-purple-200'
        };
      case 'success':
        return {
          icon: <CheckCircle className="w-5 h-5 text-green-500" />,
          text: 'Upload complete!',
          bgColor: 'bg-green-50',
          textColor: 'text-green-700',
          borderColor: 'border-green-200'
        };
      case 'error':
        return {
          icon: <AlertCircle className="w-5 h-5 text-red-500" />,
          text: errorMessage,
          bgColor: 'bg-red-50',
          textColor: 'text-red-700',
          borderColor: 'border-red-200'
        };
      default:
        return null;
    }
  };

  const statusDisplay = getStatusDisplay();

  return (
    <Dialog open={isOpen} onOpenChange={onClose}>
      <DialogContent className="sm:max-w-md md:max-w-lg p-0 gap-0 overflow-hidden">
        {/* Header with gradient */}
        <DialogHeader className="bg-gradient-to-r from-dopamine-dark to-purple-900 p-6">
          <DialogTitle className="flex items-center gap-2 text-white text-xl">
            <div className="p-2 bg-white/10 rounded-lg">
              <Upload className="w-5 h-5 text-dopamine-accent" />
            </div>
            Upload New Video
          </DialogTitle>
          <DialogDescription className="text-white/70 text-sm mt-1">
            Share your video and let AI create smart transcripts & embeddings
          </DialogDescription>
        </DialogHeader>

        {/* Content */}
        <div className="p-6 bg-gray-50">
          {!file ? (
            // Upload Area
            <div
              onClick={() => document.getElementById('video-upload')?.click()}
              onDragOver={handleDragOver}
              onDragLeave={handleDragLeave}
              onDrop={handleDrop}
              className={cn(
                "border-2 border-dashed rounded-xl p-8 text-center transition-all cursor-pointer",
                isDragging 
                  ? "border-dopamine-accent bg-dopamine-light/30" 
                  : "border-gray-300 hover:border-dopamine-accent hover:bg-dopamine-light/10"
              )}
            >
              <div className={cn(
                "w-20 h-20 rounded-full mx-auto mb-4 flex items-center justify-center transition-all",
                isDragging ? "bg-dopamine-accent scale-110" : "bg-dopamine-light"
              )}>
                <Upload className={cn(
                  "w-8 h-8 transition-all",
                  isDragging ? "text-white" : "text-dopamine-accent"
                )} />
              </div>
              
              <p className="text-gray-700 font-medium mb-1">
                {isDragging ? "Drop your video here" : "Click to select or drag and drop"}
              </p>
              <p className="text-xs text-gray-500 mb-3">
                MP4, WebM, or MOV (max 500MB)
              </p>
              
              <div className="flex items-center justify-center gap-2 text-xs text-gray-400">
                <span className="flex items-center gap-1">
                  <FileVideo className="w-3 h-3" /> Any format
                </span>
                <span className="w-1 h-1 rounded-full bg-gray-300" />
                <span>Up to 4K</span>
              </div>
              
              <input
                id="video-upload"
                type="file"
                accept="video/*"
                className="hidden"
                onChange={handleFileChange}
              />
            </div>
          ) : (
            // File Selected View
            <div className="space-y-4">
              {/* Title Input */}
              <div className="space-y-2">
                <Label htmlFor="title" className="text-sm font-medium text-gray-700">
                  Video Title
                </Label>
                <Input
                  id="title"
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  placeholder="Enter a descriptive title"
                  disabled={uploadStatus !== 'idle'}
                  className="border-gray-300 focus:border-dopamine-accent focus:ring-dopamine-accent/20"
                />
              </div>

              {/* File Info Card */}
              <div className={cn(
                "rounded-lg p-4 flex items-start gap-3 border",
                uploadStatus === 'error' ? 'bg-red-50 border-red-200' : 'bg-white border-gray-200'
              )}>
                <div className="w-12 h-12 rounded-lg bg-dopamine-light flex items-center justify-center flex-shrink-0">
                  <PlayCircle className="w-6 h-6 text-dopamine-accent" />
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-gray-900 truncate">
                    {file.name}
                  </p>
                  <p className="text-xs text-gray-500">
                    {(file.size / (1024 * 1024)).toFixed(2)} MB
                  </p>
                  
                  {/* Status Message */}
                  {statusDisplay && uploadStatus !== 'idle' && (
                    <div className={cn(
                      "mt-2 p-2 rounded-md text-xs flex items-center gap-2",
                      statusDisplay.bgColor,
                      statusDisplay.textColor,
                      statusDisplay.borderColor,
                      "border"
                    )}>
                      {statusDisplay.icon}
                      <span className="flex-1">{statusDisplay.text}</span>
                    </div>
                  )}
                </div>
                
                {uploadStatus === 'idle' && (
                  <button
                    onClick={() => setFile(null)}
                    className="p-1.5 hover:bg-gray-100 rounded-full transition-colors flex-shrink-0"
                  >
                    <X className="w-4 h-4 text-gray-500" />
                  </button>
                )}
              </div>

              {/* Progress Bar */}
              {uploadStatus !== 'idle' && uploadStatus !== 'success' && (
                <div className="space-y-1">
                  <Progress 
                    value={progress} 
                    className={cn(
                      "h-2",
                      uploadStatus === 'error' ? 'bg-red-100' : 'bg-gray-100'
                    )}
                  />
                  <p className="text-xs text-right text-gray-500">
                    {progress}% complete
                  </p>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Footer Actions */}
        <div className="border-t border-gray-200 bg-white p-4 flex flex-col sm:flex-row justify-end gap-3">
          <Button
            variant="outline"
            onClick={onClose}
            disabled={uploadStatus === 'uploading' || uploadStatus === 'processing'}
            className="w-full sm:w-auto order-2 sm:order-1"
          >
            Cancel
          </Button>
          <Button
            onClick={handleUpload}
            disabled={!file || uploadStatus !== 'idle'}
            className={cn(
              "w-full sm:w-auto order-1 sm:order-2",
              "bg-gradient-to-r from-dopamine-dark to-purple-900",
              "hover:from-dopamine-dark hover:to-purple-800",
              "text-white font-medium",
              "disabled:opacity-50 disabled:cursor-not-allowed",
              "transition-all duration-200"
            )}
          >
            {uploadStatus === 'idle' ? (
              <>
                <Upload className="w-4 h-4 mr-2" />
                Start Upload
              </>
            ) : uploadStatus === 'uploading' ? (
              <>
                <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                Uploading...
              </>
            ) : uploadStatus === 'processing' ? (
              <>
                <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                Processing...
              </>
            ) : uploadStatus === 'success' ? (
              <>
                <CheckCircle className="w-4 h-4 mr-2" />
                Complete
              </>
            ) : (
              'Upload'
            )}
          </Button>
        </div>

        {/* Success Message Overlay */}
        {uploadStatus === 'success' && (
          <div className="absolute inset-0 bg-white/90 backdrop-blur-sm flex items-center justify-center">
            <div className="text-center">
              <div className="w-16 h-16 rounded-full bg-green-100 flex items-center justify-center mx-auto mb-4">
                <CheckCircle className="w-8 h-8 text-green-600" />
              </div>
              <h3 className="text-lg font-semibold text-gray-900 mb-1">
                Upload Successful!
              </h3>
              <p className="text-sm text-gray-600">
                Your video is ready to use
              </p>
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
};