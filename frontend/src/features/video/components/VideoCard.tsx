// src/features/video/components/VideoCard.tsx
import React, {useState} from 'react';
import { PlayCircle, Clock, ImageOff } from 'lucide-react';
import { formatDistanceToNow } from 'date-fns';

interface VideoCardProps {
  id: string;
  title: string;
  duration?: string;
  thumbnail?: string;
  uploadedAt: Date;
  onClick?: (id: string) => void;
  isFirst?: boolean;
}

export const VideoCard: React.FC<VideoCardProps> = ({
  id,
  title,
  duration = '00:00',
  thumbnail,
  uploadedAt,
  onClick,
  isFirst = false,
}) => {
  const [imageError, setImageError] = useState(false);

  // Construct full URL for local thumbnails
  const thumbnailUrl = thumbnail?.startsWith('/static') 
    ? `http://localhost:8000${thumbnail}`
    : thumbnail;

  if (isFirst) {
    return (
      <div
        onClick={() => onClick?.(id)}
        className="group relative bg-white rounded-xl border-2 border-dashed border-gray-200 hover:border-dopamine-accent transition-all cursor-pointer aspect-video flex flex-col items-center justify-center gap-3 hover:bg-dopamine-light/20"
      >
        <div className="w-16 h-16 rounded-full bg-dopamine-light flex items-center justify-center group-hover:bg-dopamine-accent/10 transition-colors">
          <svg
            className="w-8 h-8 text-dopamine-accent"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M12 4v16m8-8H4"
            />
          </svg>
        </div>
        <span className="text-sm font-medium text-gray-600">Upload New Video</span>
      </div>
    );
  }

  return (
    <div
      onClick={() => onClick?.(id)}
      className="group bg-white rounded-xl border border-gray-200 overflow-hidden hover:shadow-lg transition-all cursor-pointer hover:border-dopamine-accent/50"
    >
      {/* Thumbnail */}
      <div className="relative aspect-video bg-gray-100">
        {thumbnailUrl && !imageError ? (
          <img
            src={thumbnailUrl}
            alt={title}
            className="w-full h-full object-cover"
            onError={() => setImageError(true)}
            loading="lazy"
          />
        ) : (
          <div className="w-full h-full flex items-center justify-center bg-gradient-to-br from-dopamine-light to-purple-100">
            {imageError ? (
              <ImageOff className="w-12 h-12 text-gray-400" />
            ) : (
              <PlayCircle className="w-12 h-12 text-dopamine-accent/50" />
            )}
          </div>
        )}
        
        {/* Duration Badge */}
        {duration !== '0:00' && (
          <div className="absolute bottom-2 right-2 bg-black/70 text-white text-xs px-2 py-1 rounded-md backdrop-blur-sm">
            <Clock className="w-3 h-3 inline mr-1" />
            {duration}
          </div>
        )}

        {/* Play Overlay */}
        <div className="absolute inset-0 bg-black/0 group-hover:bg-black/30 transition-all flex items-center justify-center">
          <PlayCircle className="w-12 h-12 text-white opacity-0 group-hover:opacity-100 transition-all transform group-hover:scale-110" />
        </div>
      </div>

      {/* Info */}
      <div className="p-4">
        <h3 className="font-medium text-gray-900 line-clamp-1 group-hover:text-dopamine-accent transition-colors">
          {title}
        </h3>
        <p className="text-xs text-gray-500 mt-2">
          Uploaded {formatDistanceToNow(uploadedAt)} ago
        </p>
      </div>
    </div>
  );
};