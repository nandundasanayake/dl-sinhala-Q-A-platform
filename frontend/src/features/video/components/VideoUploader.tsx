import React, { useState, useEffect, useRef } from 'react';
import { Upload, X, Loader2, CheckCircle, AlertCircle, PlayCircle, Video, Mic } from 'lucide-react';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Button } from '@/components/ui/button';
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
  const [statusMessage, setStatusMessage] = useState('');
  const [transcriptionMode, setTranscriptionMode] = useState<'video' | 'voice'>('video');
  
  const { addVideo } = useVideoStore();
  const pollIntervalRef = useRef<NodeJS.Timeout | null>(null);
  const videoIdRef = useRef<string | null>(null);

  useEffect(() => {
    if (!isOpen) {
      setTimeout(() => {
        setFile(null);
        setTitle('');
        setUploadStatus('idle');
        setProgress(0);
        setErrorMessage('');
        setStatusMessage('');
        setTranscriptionMode('video');
        if (pollIntervalRef.current) {
          clearInterval(pollIntervalRef.current);
          pollIntervalRef.current = null;
        }
        videoIdRef.current = null;
      }, 200);
    }
  }, [isOpen]);

  // Poll for status updates
  useEffect(() => {
    if (videoIdRef.current && (uploadStatus === 'uploading' || uploadStatus === 'processing')) {
      pollIntervalRef.current = setInterval(async () => {
        try {
          const response = await fetch(`${API_BASE_URL}/api/upload-status/${videoIdRef.current}`);
          if (response.ok) {
            const statusData = await response.json();
            
            console.log('Status:', statusData);
            
            // Update progress and message
            setProgress(statusData.progress || 0);
            setStatusMessage(statusData.message);
            
            // Update UI based on status
            if (statusData.status === 'uploading') {
              setUploadStatus('uploading');
            } else if (statusData.status === 'uploaded') {
              setUploadStatus('processing');
              setStatusMessage('Video uploaded, starting transcription...');
            } else if (statusData.status === 'transcript_generated') {
              setUploadStatus('processing');
              setStatusMessage('Transcript generated, finalizing...');
            } else if (statusData.status === 'completed') {
              if (pollIntervalRef.current) {
                clearInterval(pollIntervalRef.current);
                pollIntervalRef.current = null;
              }
              setUploadStatus('success');
              setProgress(100);

              const videoTitle = statusData.data?.original_title || statusData.original_title || title || file?.name || '';
              
              // Add to store
              addVideo({
                id: videoIdRef.current!,
                video_id: videoIdRef.current!,
                originalVideoId: videoIdRef.current!,
                title: videoTitle,
                fileName: file?.name || '',
                uploadedAt: new Date(),
                duration: statusData.data?.duration || '00:00',
                thumbnail: statusData.data?.thumbnail_url,
                status: 'ready',
                s3Url: statusData.data?.video_s3_url,
                transcriptUrl: statusData.data?.transcript_s3_url,
              });
              
              setTimeout(() => {
                onClose();
                if (onUploadComplete) {
                  onUploadComplete(videoIdRef.current!);
                }
              }, 1500);
            } else if (statusData.status === 'error') {
              if (pollIntervalRef.current) {
                clearInterval(pollIntervalRef.current);
                pollIntervalRef.current = null;
              }
              setUploadStatus('error');
              setErrorMessage(statusData.message || 'Processing failed');
            }
          }
        } catch (err) {
          console.error('Polling error:', err);
        }
      }, 2000);
      
      return () => {
        if (pollIntervalRef.current) {
          clearInterval(pollIntervalRef.current);
          pollIntervalRef.current = null;
        }
      };
    }
  }, [uploadStatus, title, file, addVideo, onClose, onUploadComplete]);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const selected = e.target.files?.[0];
    if (selected) {
      const maxSize = 5 * 1024 * 1024 * 1024; // 5GB
      if (selected.size > maxSize) {
        setErrorMessage(`File too large. Maximum size is 5GB.`);
        setUploadStatus('error');
        return;
      }
      
      setFile(selected);
      setTitle(selected.name.replace(/\.[^/.]+$/, ''));
      setErrorMessage('');
      setUploadStatus('idle');
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
      const maxSize = 5 * 1024 * 1024 * 1024; // 5GB
      if (droppedFile.size > maxSize) {
        setErrorMessage(`File too large. Maximum size is 5GB.`);
        setUploadStatus('error');
        return;
      }
      
      setFile(droppedFile);
      if (!title) {
        setTitle(droppedFile.name.replace(/\.[^/.]+$/, ''));
      }
      setErrorMessage('');
      setUploadStatus('idle');
    }
  };

  const handleUpload = async () => {
    if (!file) return;

    setUploadStatus('uploading');
    setProgress(0);
    setErrorMessage('');
    setStatusMessage('Getting upload URL...');

    try {
      // Step 1: Get pre-signed URL from backend
      const encodedFileName = encodeURIComponent(file.name);
      const urlResponse = await fetch(`${API_BASE_URL}/api/generate-upload-url?filename=${encodedFileName}`);
      
      if (!urlResponse.ok) {
        const errorData = await urlResponse.json();
        setUploadStatus('error');
        setErrorMessage(errorData.detail || 'Failed to generate upload URL');
        return;
      }

      const { upload_url, video_id, original_filename } = await urlResponse.json();
      videoIdRef.current = video_id;

      // Step 2: Direct upload to S3 using PUT request
      setStatusMessage('Uploading to cloud storage...');
      
      const xhr = new XMLHttpRequest();
      
      await new Promise<void>((resolve, reject) => {
        xhr.upload.addEventListener('progress', (event) => {
          if (event.lengthComputable) {
            // S3 upload progress (0-100% of the upload phase)
            const percentComplete = Math.round((event.loaded / event.total) * 100);
            setProgress(percentComplete);
            setStatusMessage(`Uploading to cloud... ${percentComplete}%`);
          }
        });

        xhr.addEventListener('load', () => {
          if (xhr.status === 200) {
            resolve();
          } else {
            reject(new Error(`S3 upload failed with status ${xhr.status}`));
          }
        });

        xhr.addEventListener('error', () => {
          reject(new Error('Network error during S3 upload'));
        });

        xhr.addEventListener('abort', () => {
          reject(new Error('Upload was aborted'));
        });

        xhr.open('PUT', upload_url);
        xhr.setRequestHeader('Content-Type', file.type || 'video/mp4');
        xhr.send(file);
      });

      // Step 3: Trigger backend processing
      setStatusMessage('Starting video processing...');
      setProgress(0); // Reset progress for processing phase
      
      const processResponse = await fetch(`${API_BASE_URL}/api/process-video`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ 
          video_id: video_id,
          original_title: title || original_filename,
          transcription_mode: transcriptionMode
        }),
      });

      if (!processResponse.ok) {
        const errorData = await processResponse.json();
        setUploadStatus('error');
        setErrorMessage(errorData.detail || 'Failed to start processing');
        return;
      }

      // Step 4: Switch to processing status - polling will take over from here
      setUploadStatus('processing');
      setProgress(10);
      setStatusMessage('Processing started...');
      
    } catch (error) {
      setUploadStatus('error');
      if (error instanceof Error) {
        setErrorMessage(error.message);
      } else {
        setErrorMessage('Network error. Please check your connection.');
      }
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
          text: 'Uploading video...',
          subText: `${Math.round(progress)}% complete`,
          bgColor: 'bg-blue-50',
          textColor: 'text-blue-700'
        };
      case 'processing':
        return {
          icon: <Loader2 className="w-4 h-4 sm:w-5 sm:h-5 animate-spin text-brand" />,
          text: statusMessage || 'Processing video...',
          subText: `${Math.round(progress)}% complete`,
          bgColor: 'bg-purple-50',
          textColor: 'text-purple-700'
        };
      case 'success':
        return {
          icon: <CheckCircle className="w-4 h-4 sm:w-5 sm:h-5 text-green-500" />,
          text: 'Upload complete!',
          subText: 'Your video is ready to use',
          bgColor: 'bg-green-50',
          textColor: 'text-green-700'
        };
      case 'error':
        return {
          icon: <AlertCircle className="w-4 h-4 sm:w-5 sm:h-5 text-red-500" />,
          text: 'Upload failed',
          subText: errorMessage,
          bgColor: 'bg-red-50',
          textColor: 'text-red-700'
        };
      default:
        return null;
    }
  };

  const statusDisplay = getStatusDisplay();

  return (
    <Dialog open={isOpen} onOpenChange={onClose}>
      <DialogContent className={cn(
        "p-0 gap-0 overflow-hidden",
        "w-[calc(100%-2rem)] max-w-[calc(100%-2rem)]",
        "sm:max-w-md sm:w-full",
        "md:max-w-lg",
        "max-h-[90vh] sm:max-h-[85vh]",
        "flex flex-col",
        "fixed left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2",
        "mx-0"
      )}>
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

        <div className="flex-1 overflow-y-auto bg-background p-4 sm:p-5 md:p-6">
          {!file ? (
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
                isDragging ? "border-brand bg-accent/50" : "border-border hover:border-brand hover:bg-accent/20"
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
                MP4, WebM, MOV, or AVI (max 5GB)
              </p>
              <input
                id="video-upload"
                type="file"
                accept="video/*"
                className="hidden"
                onChange={handleFileChange}
              />
            </div>
          ) : (
            <div className="space-y-4">
              <div className="space-y-1 sm:space-y-2">
                <Label htmlFor="title" className="text-xs sm:text-sm font-medium text-foreground">
                  Video Title
                </Label>
                <Input
                  id="title"
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  placeholder="Enter a descriptive title"
                  disabled
                  className="h-9 sm:h-10 text-sm border-input focus:border-ring focus:ring-ring/20 w-full"
                />
              </div>

              {/* Transcription Mode Toggle */}
              <div className="space-y-1 sm:space-y-2">
                <Label className="text-xs sm:text-sm font-medium text-foreground">
                  Transcription Mode
                </Label>
                <div className="grid grid-cols-2 gap-2">
                  <button
                    type="button"
                    onClick={() => setTranscriptionMode('video')}
                    disabled={uploadStatus !== 'idle'}
                    className={cn(
                      "flex items-center gap-2 p-3 rounded-lg border-2 transition-all text-left",
                      "disabled:opacity-50 disabled:cursor-not-allowed",
                      transcriptionMode === 'video'
                        ? "border-brand bg-brand/5 ring-1 ring-brand/20"
                        : "border-border hover:border-muted-foreground/30 bg-card"
                    )}
                  >
                    <div className={cn(
                      "w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0",
                      transcriptionMode === 'video' ? "bg-brand/10" : "bg-muted"
                    )}>
                      <Video className={cn(
                        "w-4 h-4",
                        transcriptionMode === 'video' ? "text-brand" : "text-muted-foreground"
                      )} />
                    </div>
                    <div>
                      <p className={cn(
                        "text-xs font-semibold",
                        transcriptionMode === 'video' ? "text-brand" : "text-foreground"
                      )}>Video + Audio</p>
                      <p className="text-[10px] text-muted-foreground leading-tight mt-0.5">Screen content + voice</p>
                    </div>
                  </button>

                  <button
                    type="button"
                    onClick={() => setTranscriptionMode('voice')}
                    disabled={uploadStatus !== 'idle'}
                    className={cn(
                      "flex items-center gap-2 p-3 rounded-lg border-2 transition-all text-left",
                      "disabled:opacity-50 disabled:cursor-not-allowed",
                      transcriptionMode === 'voice'
                        ? "border-purple-500 bg-purple-500/5 ring-1 ring-purple-500/20"
                        : "border-border hover:border-muted-foreground/30 bg-card"
                    )}
                  >
                    <div className={cn(
                      "w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0",
                      transcriptionMode === 'voice' ? "bg-purple-500/10" : "bg-muted"
                    )}>
                      <Mic className={cn(
                        "w-4 h-4",
                        transcriptionMode === 'voice' ? "text-purple-500" : "text-muted-foreground"
                      )} />
                    </div>
                    <div>
                      <p className={cn(
                        "text-xs font-semibold",
                        transcriptionMode === 'voice' ? "text-purple-500" : "text-foreground"
                      )}>Voice Only</p>
                      <p className="text-[10px] text-muted-foreground leading-tight mt-0.5">Audio/voice only</p>
                    </div>
                  </button>
                </div>
              </div>

              <div className={cn(
                "rounded-lg p-3 sm:p-4 border",
                "flex flex-col sm:flex-row items-start gap-3",
                uploadStatus === 'error' ? 'bg-red-50 border-red-200' : 'bg-card border-border'
              )}>
                <div className="w-10 h-10 sm:w-12 sm:h-12 rounded-lg bg-accent flex items-center justify-center flex-shrink-0">
                  <PlayCircle className="w-5 h-5 sm:w-6 sm:h-6 text-brand" />
                </div>
                
                <div className="flex-1 min-w-0 w-full">
                  <div className="group relative">
                    <p className="text-sm font-medium text-foreground truncate" title={file.name}>
                      {truncateFileName(file.name, 25)}
                    </p>
                    <div className="hidden sm:block absolute bottom-full left-0 mb-1 px-2 py-1 bg-gray-900 text-white text-xs rounded opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none whitespace-nowrap z-50">
                      {file.name}
                    </div>
                  </div>
                  <p className="text-xs text-muted-foreground mt-0.5">
                    {(file.size / (1024 * 1024)).toFixed(2)} MB
                  </p>
                  
                  {statusDisplay && uploadStatus !== 'idle' && (
                    <div className={cn(
                      "mt-2 p-2 rounded-md text-xs",
                      statusDisplay.bgColor,
                      statusDisplay.textColor,
                      "border"
                    )}>
                      <div className="flex items-start gap-2">
                        <span className="flex-shrink-0 mt-0.5">{statusDisplay.icon}</span>
                        <div className="flex-1">
                          <p className="font-medium">{statusDisplay.text}</p>
                          {statusDisplay.subText && (
                            <p className="text-xs opacity-75 mt-0.5">{statusDisplay.subText}</p>
                          )}
                        </div>
                      </div>
                    </div>
                  )}
                </div>
                
                {uploadStatus === 'idle' && (
                  <button
                    onClick={() => {
                      setFile(null);
                      setErrorMessage('');
                    }}
                    className="p-1.5 hover:bg-accent rounded-full transition-colors flex-shrink-0 self-end sm:self-start"
                    aria-label="Remove file"
                  >
                    <X className="w-4 h-4 text-muted-foreground" />
                  </button>
                )}
              </div>

              {uploadStatus !== 'idle' && uploadStatus !== 'success' && (
                <div className="space-y-2">
                  <Progress value={progress} className="h-2 bg-muted" />
                  <div className="flex justify-between items-center text-xs">
                    <span className="text-muted-foreground">
                      {uploadStatus === 'uploading' && 'Uploading...'}
                      {uploadStatus === 'processing' && 'Processing...'}
                    </span>
                    <span className="text-muted-foreground font-medium">
                      {Math.round(progress)}% complete
                    </span>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>

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