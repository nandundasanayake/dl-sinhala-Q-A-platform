import React, { useState, useEffect } from 'react';
import { Upload, X, Loader2, CheckCircle, AlertCircle, PlayCircle, FileVideo } from 'lucide-react';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Progress } from '@/components/ui/progress';
import { useVideoStore } from '@/store/video.store';
import { cn } from '@/lib/utils';

const API_BASE_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

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
      
      setTitle(selected.name.replace(/\.[^/.]+$/, ''));
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

      const response = await fetch(`${API_BASE_URL}/api/upload-video`, {
        method: 'POST',
        body: formData,
      });

      clearInterval(interval);
      setProgress(100);
      setUploadStatus('processing');

      const data = await response.json();

      if (response.ok) {
        setUploadStatus('success');

        const uniqueId = `${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
        
        addVideo({
          id: uniqueId,
          video_id: data.video_id,
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

  const truncateFileName = (name: string, maxLength: number = 30) => {
    if (name.length <= maxLength) return name;
    const extension = name.split('.').pop() || '';
    const nameWithoutExt = name.substring(0, name.lastIndexOf('.'));
    const truncatedName = nameWithoutExt.substring(0, maxLength - 3 - extension.length);
    return `${truncatedName}...${extension}`;
  };

  const getStatusDisplay = () => {
    switch (uploadStatus) {
      case 'uploading':
        return {
          icon: <Loader2 className="w-4 h-4 sm:w-5 sm:h-5 animate-spin text-brand" />,
          text: `Uploading... ${progress}%`,
          bgColor: 'bg-blue-50',
          textColor: 'text-blue-700',
          borderColor: 'border-blue-200'
        };
      case 'processing':
        return {
          icon: <Loader2 className="w-4 h-4 sm:w-5 sm:h-5 animate-spin text-brand" />,
          text: 'Generating transcript & embeddings...',
          bgColor: 'bg-accent',
          textColor: 'text-foreground',
          borderColor: 'border-border'
        };
      case 'success':
        return {
          icon: <CheckCircle className="w-4 h-4 sm:w-5 sm:h-5 text-green-500" />,
          text: 'Upload complete!',
          bgColor: 'bg-green-50',
          textColor: 'text-green-700',
          borderColor: 'border-green-200'
        };
      case 'error':
        return {
          icon: <AlertCircle className="w-4 h-4 sm:w-5 sm:h-5 text-red-500" />,
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
      <DialogContent className={cn(
        // Base styles
        "p-0 gap-0 overflow-hidden",
        // Responsive width
        "w-[calc(100%-2rem)] max-w-[calc(100%-2rem)]",
        "sm:max-w-md sm:w-full",
        "md:max-w-lg",
        // Height management
        "max-h-[90vh] sm:max-h-[85vh]",
        "flex flex-col", // Use flex column for proper height distribution
        // Center positioning
        "fixed left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2",
        "mx-0"
      )}>
        {/* Header - Fixed at top */}
        <DialogHeader className="bg-sidebar p-4 sm:p-5 md:p-6 flex-shrink-0">
          <DialogTitle className="flex items-center gap-2 text-sidebar-foreground text-lg sm:text-xl">
            <div className="p-1.5 sm:p-2 bg-white/10 rounded-lg">
              <Upload className="w-4 h-4 sm:w-5 sm:h-5 text-brand" />
            </div>
            Upload New Video
          </DialogTitle>
          <DialogDescription className="text-sidebar-foreground/70 text-xs sm:text-sm mt-0.5 sm:mt-1">
            Share your video and let AI create smart notes and transcripts 
          </DialogDescription>
        </DialogHeader>

        {/* Scrollable Content Area */}
        <div className="flex-1 overflow-y-auto bg-background p-4 sm:p-5 md:p-6">
          {!file ? (
            // Upload Area
            <div
              onClick={() => document.getElementById('video-upload')?.click()}
              onDragOver={handleDragOver}
              onDragLeave={handleDragLeave}
              onDrop={handleDrop}
              className={cn(
                "border-2 border-dashed rounded-xl transition-all cursor-pointer",
                "p-4 sm:p-6 md:p-8",
                "text-center",
                "min-h-[200px] sm:min-h-[250px] flex flex-col items-center justify-center",
                isDragging 
                  ? "border-brand bg-accent/50" 
                  : "border-border hover:border-brand hover:bg-accent/20"
              )}
            >
              <div className={cn(
                "w-12 h-12 sm:w-16 sm:h-16 md:w-20 md:h-20",
                "rounded-full mb-2 sm:mb-3 md:mb-4",
                "flex items-center justify-center transition-all",
                isDragging ? "bg-brand scale-110" : "bg-accent"
              )}>
                <Upload className={cn(
                  "w-5 h-5 sm:w-6 sm:h-6 md:w-8 md:h-8",
                  "transition-all",
                  isDragging ? "text-white" : "text-brand"
                )} />
              </div>
              
              <p className="text-sm sm:text-base text-foreground font-medium mb-1">
                {isDragging ? "Drop your video here" : "Click to select or drag and drop"}
              </p>
              <p className="text-xs sm:text-sm text-muted-foreground mb-2 sm:mb-3">
                MP4, WebM, or MOV (max 500MB)
              </p>
              
              <div className="flex flex-wrap items-center justify-center gap-2 text-xs text-muted-foreground">
                <span className="flex items-center gap-1 whitespace-nowrap">
                  <FileVideo className="w-3 h-3" /> Any format
                </span>
                <span className="w-1 h-1 rounded-full bg-border hidden xs:inline-block" />
                <span className="whitespace-nowrap">Up to 4K</span>
                <span className="w-1 h-1 rounded-full bg-border hidden xs:inline-block" />
                <span className="whitespace-nowrap">Drag & drop</span>
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
              <div className="space-y-1 sm:space-y-2">
                <Label htmlFor="title" className="text-xs sm:text-sm font-medium text-foreground">
                  Video Title
                </Label>
                <Input
                  id="title"
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  placeholder="Enter a descriptive title"
                  disabled={uploadStatus !== 'idle'}
                  className="h-9 sm:h-10 text-sm border-input focus:border-ring focus:ring-ring/20 w-full"
                />
              </div>

              {/* File Info Card - Improved for long filenames */}
              <div className={cn(
                "rounded-lg p-3 sm:p-4 border",
                "flex flex-col sm:flex-row items-start gap-3",
                uploadStatus === 'error' ? 'bg-red-50 border-red-200' : 'bg-card border-border'
              )}>
                <div className="w-10 h-10 sm:w-12 sm:h-12 rounded-lg bg-accent flex items-center justify-center flex-shrink-0">
                  <PlayCircle className="w-5 h-5 sm:w-6 sm:h-6 text-brand" />
                </div>
                
                {/* Filename container with proper overflow handling */}
                <div className="flex-1 min-w-0 w-full">
                  {/* Filename with tooltip on hover */}
                  <div className="group relative">
                    <p className="text-sm font-medium text-foreground truncate" title={file.name}>
                      {truncateFileName(file.name, 25)}
                    </p>
                    {/* Tooltip for full filename on hover (desktop only) */}
                    <div className="hidden sm:block absolute bottom-full left-0 mb-1 px-2 py-1 bg-gray-900 text-white text-xs rounded opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none whitespace-nowrap z-50">
                      {file.name}
                    </div>
                  </div>
                  <p className="text-xs text-muted-foreground mt-0.5">
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
                      <span className="flex-shrink-0">{statusDisplay.icon}</span>
                      <span className="flex-1 break-words">{statusDisplay.text}</span>
                    </div>
                  )}
                </div>
                
                {/* Remove button - Always visible */}
                {uploadStatus === 'idle' && (
                  <button
                    onClick={() => setFile(null)}
                    className="p-1.5 hover:bg-accent rounded-full transition-colors flex-shrink-0 self-end sm:self-start"
                    aria-label="Remove file"
                  >
                    <X className="w-4 h-4 text-muted-foreground" />
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
                      uploadStatus === 'error' ? 'bg-red-100' : 'bg-muted'
                    )}
                  />
                  <p className="text-xs text-right text-muted-foreground">
                    {progress}% complete
                  </p>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Footer - Fixed at bottom */}
        <div className="border-t border-border bg-card p-3 sm:p-4 flex-shrink-0">
          <div className="flex flex-col-reverse sm:flex-row justify-end gap-2 sm:gap-3">
            <Button
              variant="outline"
              onClick={onClose}
              disabled={uploadStatus === 'uploading' || uploadStatus === 'processing'}
              className="w-full sm:w-auto"
            >
              Cancel
            </Button>
            <Button
              onClick={handleUpload}
              disabled={!file || uploadStatus !== 'idle'}
              className={cn(
                "w-full sm:w-auto",
                "bg-secondary text-secondary-foreground",
                "hover:bg-secondary/90",
                "font-medium",
                "disabled:opacity-50 disabled:cursor-not-allowed"
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
        </div>

        {/* Success Overlay */}
        {uploadStatus === 'success' && (
          <div className="absolute inset-0 bg-background/90 backdrop-blur-sm flex items-center justify-center p-4 z-20">
            <div className="text-center w-full max-w-xs sm:max-w-sm">
              <div className="w-14 h-14 sm:w-16 sm:h-16 md:w-20 md:h-20 rounded-full bg-green-100 flex items-center justify-center mx-auto mb-3 sm:mb-4">
                <CheckCircle className="w-7 h-7 sm:w-8 sm:h-8 md:w-10 md:h-10 text-green-600" />
              </div>
              <h3 className="text-base sm:text-lg md:text-xl font-semibold text-foreground mb-1">
                Upload Successful!
              </h3>
              <p className="text-xs sm:text-sm text-muted-foreground">
                Your video is ready to use
              </p>
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
};