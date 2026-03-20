import React, { useRef, useEffect, useState } from 'react';
import { Play, Pause, Volume2, VolumeX, Maximize, Minimize, Loader2 } from 'lucide-react';
import { cn } from '@/lib/utils';

interface VideoPlayerProps {
  src: string;
  title: string;
  onTimeUpdate?: (currentTime: number) => void;
  onSeek?: (time: number) => void;
  onError?: (error: string) => void;
  seekTo?: number | null;
  className?: string;
}

export const VideoPlayer: React.FC<VideoPlayerProps> = ({
  src,
  title,
  onTimeUpdate,
  onSeek,
  onError,
  seekTo,
  className,
}) => {
  const videoRef = useRef<HTMLVideoElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  
  const [isPlaying, setIsPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [volume, setVolume] = useState(1);
  const [isMuted, setIsMuted] = useState(false);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [showControls, setShowControls] = useState(true);
  const [isHovering, setIsHovering] = useState(false);
  const [videoError, setVideoError] = useState(false);
  const [loadAttempts, setLoadAttempts] = useState(0);
  const [lastSeekTo, setLastSeekTo] = useState<number | null>(null);

  let controlsTimeout: NodeJS.Timeout;

  // Handle seeking from parent component
  useEffect(() => {
    if (seekTo !== null && seekTo !== undefined && seekTo !== lastSeekTo && videoRef.current) {
      console.log('🎯 Seeking video to:', seekTo);
      videoRef.current.currentTime = seekTo;
      setCurrentTime(seekTo);
      setLastSeekTo(seekTo);
      onSeek?.(seekTo);
      
      // Auto-play after seeking
      if (videoRef.current.paused) {
        videoRef.current.play().catch(err => {
          console.error('Play after seek failed:', err);
        });
        setIsPlaying(true);
      }
    }
  }, [seekTo, lastSeekTo, onSeek]);


  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;

    const handleLoadedMetadata = () => {
      setDuration(video.duration);
      setIsLoading(false);
      setVideoError(false);
    };

    const handleTimeUpdate = () => {
      setCurrentTime(video.currentTime);
      onTimeUpdate?.(video.currentTime);
    };

    const handleWaiting = () => setIsLoading(true);
    const handlePlaying = () => {
      setIsLoading(false);
      setVideoError(false);
    };
    const handleEnded = () => setIsPlaying(false);
    
    const handleError = (e: Event) => {
      const videoElement = e.target as HTMLVideoElement;
      let errorMessage = 'Video playback error';
      
      if (videoElement.error) {
        switch (videoElement.error.code) {
          case MediaError.MEDIA_ERR_ABORTED:
            errorMessage = 'Video playback was aborted';
            break;
          case MediaError.MEDIA_ERR_NETWORK:
            errorMessage = 'Network error occurred while loading video';
            break;
          case MediaError.MEDIA_ERR_DECODE:
            errorMessage = 'Video decoding error';
            break;
          case MediaError.MEDIA_ERR_SRC_NOT_SUPPORTED:
            errorMessage = 'Video format not supported. Please ensure the video is in MP4 format with H.264 codec.';
            break;
          default:
            errorMessage = `Video error: ${videoElement.error.message}`;
        }
      }
      
      console.error('Video error:', errorMessage);
      
      // Try to reload once
      if (loadAttempts < 1) {
        console.log('Attempting to reload video...');
        setLoadAttempts(prev => prev + 1);
        setTimeout(() => {
          if (videoElement) {
            videoElement.load();
          }
        }, 1000);
      } else {
        setVideoError(true);
        setIsLoading(false);
        onError?.(errorMessage);
      }
    };

    const handleCanPlay = () => {
      setIsLoading(false);
      setVideoError(false);
    };

    const handleStalled = () => {
      console.log('Video stalled, retrying...');
      setIsLoading(true);
    };

    video.addEventListener('loadedmetadata', handleLoadedMetadata);
    video.addEventListener('timeupdate', handleTimeUpdate);
    video.addEventListener('waiting', handleWaiting);
    video.addEventListener('playing', handlePlaying);
    video.addEventListener('ended', handleEnded);
    video.addEventListener('error', handleError);
    video.addEventListener('canplay', handleCanPlay);
    video.addEventListener('stalled', handleStalled);

    return () => {
      video.removeEventListener('loadedmetadata', handleLoadedMetadata);
      video.removeEventListener('timeupdate', handleTimeUpdate);
      video.removeEventListener('waiting', handleWaiting);
      video.removeEventListener('playing', handlePlaying);
      video.removeEventListener('ended', handleEnded);
      video.removeEventListener('error', handleError);
      video.removeEventListener('canplay', handleCanPlay);
      video.removeEventListener('stalled', handleStalled);
    };
  }, [onTimeUpdate, onError, loadAttempts]);

  const togglePlay = () => {
    if (!videoRef.current || videoError) return;
    
    if (isPlaying) {
      videoRef.current.pause();
    } else {
      videoRef.current.play().catch(err => {
        console.error('Play failed:', err);
        onError?.('Failed to play video. Please check your connection.');
      });
    }
    setIsPlaying(!isPlaying);
  };

  const handleVolumeChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const newVolume = parseFloat(e.target.value);
    if (!videoRef.current) return;
    
    videoRef.current.volume = newVolume;
    setVolume(newVolume);
    setIsMuted(newVolume === 0);
  };

  const toggleMute = () => {
    if (!videoRef.current) return;
    
    if (isMuted) {
      videoRef.current.volume = volume || 1;
      setIsMuted(false);
    } else {
      videoRef.current.volume = 0;
      setIsMuted(true);
    }
  };

  const handleSeek = (e: React.ChangeEvent<HTMLInputElement>) => {
    const time = parseFloat(e.target.value);
    if (!videoRef.current) return;
    
    videoRef.current.currentTime = time;
    setCurrentTime(time);
    onSeek?.(time);
    setLastSeekTo(time);
  };

  const toggleFullscreen = () => {
    if (!containerRef.current) return;
    
    if (!document.fullscreenElement) {
      containerRef.current.requestFullscreen();
      setIsFullscreen(true);
    } else {
      document.exitFullscreen();
      setIsFullscreen(false);
    }
  };

  const formatTime = (seconds: number) => {
    if (isNaN(seconds)) return '0:00';
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const secs = Math.floor(seconds % 60);
    
    if (hours > 0) {
      return `${hours}:${minutes.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
    }
    return `${minutes}:${secs.toString().padStart(2, '0')}`;
  };

  const handleMouseMove = () => {
    setShowControls(true);
    clearTimeout(controlsTimeout);
    
    if (isPlaying) {
      controlsTimeout = setTimeout(() => {
        if (!isHovering) {
          setShowControls(false);
        }
      }, 3000);
    }
  };

  const retryLoad = () => {
    setVideoError(false);
    setIsLoading(true);
    setLoadAttempts(0);
    if (videoRef.current) {
      videoRef.current.load();
    }
  };

  if (videoError) {
    return (
      <div className={cn(
        "relative bg-black rounded-lg overflow-hidden flex items-center justify-center",
        className
      )}>
        <div className="text-center p-8">
          <p className="text-white mb-2">Failed to load video</p>
          <p className="text-sm text-white/60 mb-4">The video source may be unavailable or CORS not configured</p>
          <button
            onClick={retryLoad}
            className="bg-brand text-brand-foreground px-4 py-2 rounded-lg hover:bg-brand/90 transition-colors"
          >
            Retry
          </button>
        </div>
      </div>
    );
  }

  return (
    <div
      ref={containerRef}
      className={cn(
        "relative bg-black rounded-lg overflow-hidden group",
        className
      )}
      onMouseMove={handleMouseMove}
      onMouseEnter={() => setIsHovering(true)}
      onMouseLeave={() => {
        setIsHovering(false);
        if (isPlaying) {
          setShowControls(false);
        }
      }}
    >
      <video
        ref={videoRef}
        src={src}
        className="w-full h-full"
        onClick={togglePlay}
        crossOrigin="anonymous"
        preload="auto"
      />

      {isLoading && (
        <div className="absolute inset-0 flex items-center justify-center bg-black/50 z-10">
          <div className="text-center">
            <Loader2 className="w-12 h-12 text-white animate-spin mx-auto mb-2" />
            <p className="text-white text-sm">Loading video...</p>
          </div>
        </div>
      )}

      <div className={cn(
        "absolute top-0 left-0 right-0 p-4 bg-gradient-to-b from-black/70 to-transparent transition-opacity z-20",
        showControls ? "opacity-100" : "opacity-0"
      )}>
        <h3 className="text-white font-medium truncate">{title}</h3>
      </div>

      <div className={cn(
        "absolute bottom-0 left-0 right-0 bg-gradient-to-t from-black/70 via-black/40 to-transparent p-4 transition-opacity z-20",
        showControls ? "opacity-100" : "opacity-0 pointer-events-none"
      )}>
        <div className="mb-4">
          <input
            type="range"
            min={0}
            max={duration || 100}
            value={currentTime}
            onChange={handleSeek}
            className="w-full h-1 bg-gray-600 rounded-lg appearance-none cursor-pointer 
              [&::-webkit-slider-thumb]:appearance-none 
              [&::-webkit-slider-thumb]:w-3 
              [&::-webkit-slider-thumb]:h-3 
              [&::-webkit-slider-thumb]:bg-brand 
              [&::-webkit-slider-thumb]:rounded-full 
              [&::-webkit-slider-thumb]:cursor-pointer
              [&::-webkit-slider-thumb]:hover:scale-125
              [&::-webkit-slider-thumb]:transition-transform"
          />
          <div className="flex justify-between text-xs text-white mt-1">
            <span>{formatTime(currentTime)}</span>
            <span>{formatTime(duration)}</span>
          </div>
        </div>

        <div className="flex items-center gap-4">
          <button
            onClick={togglePlay}
            className="text-white hover:text-brand transition-colors p-1 rounded-full hover:bg-white/10"
          >
            {isPlaying ? <Pause className="w-5 h-5" /> : <Play className="w-5 h-5" />}
          </button>

          <div className="flex items-center gap-2 group/volume">
            <button
              onClick={toggleMute}
              className="text-white hover:text-brand transition-colors p-1 rounded-full hover:bg-white/10"
            >
              {isMuted ? <VolumeX className="w-5 h-5" /> : <Volume2 className="w-5 h-5" />}
            </button>
            <div className="w-0 group-hover/volume:w-20 transition-all overflow-hidden">
              <input
                type="range"
                min={0}
                max={1}
                step={0.1}
                value={isMuted ? 0 : volume}
                onChange={handleVolumeChange}
                className="w-20 h-1 bg-gray-600 rounded-lg appearance-none cursor-pointer
                  [&::-webkit-slider-thumb]:appearance-none 
                  [&::-webkit-slider-thumb]:w-3 
                  [&::-webkit-slider-thumb]:h-3 
                  [&::-webkit-slider-thumb]:bg-white 
                  [&::-webkit-slider-thumb]:rounded-full
                  [&::-webkit-slider-thumb]:cursor-pointer"
              />
            </div>
          </div>

          <div className="flex-1" />

          <button
            onClick={toggleFullscreen}
            className="text-white hover:text-brand transition-colors p-1 rounded-full hover:bg-white/10"
          >
            {isFullscreen ? <Minimize className="w-5 h-5" /> : <Maximize className="w-5 h-5" />}
          </button>
        </div>
      </div>

      {!isPlaying && !isLoading && !videoError && (
        <button
          onClick={togglePlay}
          className="absolute top-1/2 left-1/2 transform -translate-x-1/2 -translate-y-1/2 
            w-16 h-16 bg-brand rounded-full flex items-center justify-center
            hover:scale-110 transition-transform shadow-lg z-30"
        >
          <Play className="w-8 h-8 text-brand-foreground ml-1" />
        </button>
      )}
    </div>
  );
};