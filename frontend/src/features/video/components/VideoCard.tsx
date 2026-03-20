import React, { useState } from 'react';
import { PlayCircle, Clock, ImageOff, Plus, MoreVertical, Trash2, X } from 'lucide-react';
import { formatDistanceToNow } from 'date-fns';
import { cn } from '@/lib/utils';
import { useVideoStore } from '@/store/video.store';

const API_BASE_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

interface VideoCardProps {
  id: string;
  title: string;
  duration?: string;
  thumbnail?: string;
  uploadedAt: Date;
  onClick?: (id: string) => void;
  onDelete?: (id: string) => void;
  isFirst?: boolean;
}

export const VideoCard: React.FC<VideoCardProps> = ({
  id,
  title,
  duration = '00:00',
  thumbnail,
  uploadedAt,
  onClick,
  onDelete,
  isFirst = false,
}) => {
  const [imageError, setImageError] = useState(false);
  const [showMenu, setShowMenu] = useState(false);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);
  const { removeVideo } = useVideoStore();

  const thumbnailUrl = thumbnail?.startsWith('/static') 
    ? `${API_BASE_URL}${thumbnail}`
    : thumbnail;

  const handleMenuClick = (e: React.MouseEvent) => {
    e.stopPropagation(); // Prevent card click
    setShowMenu(!showMenu);
  };

  const handleDeleteClick = (e: React.MouseEvent) => {
    e.stopPropagation(); // Prevent card click
    setShowMenu(false);
    setShowDeleteConfirm(true);
  };

  const handleCancelDelete = (e: React.MouseEvent) => {
    e.stopPropagation();
    setShowDeleteConfirm(false);
  };

  const handleConfirmDelete = async (e: React.MouseEvent) => {
    e.stopPropagation();
    setIsDeleting(true);
    
    try {
      // Call the delete API through the store
      await removeVideo(id);
      onDelete?.(id);
    } catch (error) {
      console.error('Failed to delete video:', error);
    } finally {
      setIsDeleting(false);
      setShowDeleteConfirm(false);
    }
  };

  // Close menu when clicking outside
  React.useEffect(() => {
    const handleClickOutside = () => {
      setShowMenu(false);
    };
    
    if (showMenu) {
      document.addEventListener('click', handleClickOutside);
      return () => document.removeEventListener('click', handleClickOutside);
    }
  }, [showMenu]);

  if (isFirst) {
    return (
      <div
        onClick={() => onClick?.(id)}
        className="group relative bg-card rounded-xl border-2 border-dashed border-border hover:border-brand transition-all cursor-pointer aspect-video flex flex-col items-center justify-center gap-3 hover:bg-accent/20"
      >
        <div className="w-16 h-16 rounded-full bg-accent flex items-center justify-center group-hover:bg-brand/10 transition-colors">
          <Plus className="w-8 h-8 text-brand" />
        </div>
        <span className="text-sm font-medium text-muted-foreground">Upload New Video</span>
      </div>
    );
  }

  return (
    <div className="relative group">
      {/* Delete Confirmation Modal */}
      {showDeleteConfirm && (
        <div 
          className="absolute inset-0 z-50 flex items-center justify-center p-4"
          onClick={(e) => e.stopPropagation()}
        >
          <div className="absolute inset-0 bg-black/60 rounded-xl" />
          <div className="relative bg-card rounded-xl p-6 max-w-sm w-full shadow-2xl border border-border">
            <button
              onClick={handleCancelDelete}
              className="absolute top-3 right-3 text-muted-foreground hover:text-foreground"
            >
              <X className="w-5 h-5" />
            </button>
            
            <div className="text-center">
              <div className="w-16 h-16 rounded-full bg-destructive/10 flex items-center justify-center mx-auto mb-4">
                <Trash2 className="w-8 h-8 text-destructive" />
              </div>
              <h3 className="text-lg font-semibold text-foreground mb-2">Delete Video</h3>
              <p className="text-sm text-muted-foreground mb-6">
                Are you sure you want to remove "<span className="font-medium text-foreground">{title}</span>"? 
                Once deleted, you won't be able to recover it.
              </p>
              <div className="flex gap-3">
                <button
                  onClick={handleCancelDelete}
                  className="flex-1 px-4 py-2 bg-accent text-foreground rounded-lg hover:bg-accent/80 transition-colors text-sm font-medium"
                >
                  Cancel
                </button>
                <button
                  onClick={handleConfirmDelete}
                  disabled={isDeleting}
                  className="flex-1 px-4 py-2 bg-distr text-destructive-soft-foreground rounded-lg hover:bg-destructive/80 hover:text-destructive-foreground transition-colors text-sm font-medium disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
                >
                  {isDeleting ? (
                    <>
                      <div className="w-4 h-4 border-2 border-destructive-foreground/30 border-t-destructive-foreground rounded-full animate-spin" />
                      Deleting...
                    </>
                  ) : (
                    <>
                      <Trash2 className="w-4 h-4" />
                      Delete
                    </>
                  )}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Three dots menu */}
      <button
        onClick={handleMenuClick}
        className="absolute top-2 right-2 z-10 p-2 bg-sidebar/40 backdrop-blur-sm rounded-lg opacity-0 group-hover:opacity-100 transition-opacity hover:bg-sidebar/80 text-sidebar-foreground"
      >
        <MoreVertical className="w-4 h-4" />
      </button>

      {/* Dropdown menu */}
      {showMenu && (
        <div className="absolute top-12 right-2 z-20 bg-card border border-border rounded-lg shadow-lg py-1 min-w-[140px]">
          <button
            onClick={handleDeleteClick}
            className="w-full px-4 py-2 text-sm text-left text-destructive hover:bg-destructive/10 flex items-center gap-2 transition-colors"
          >
            <Trash2 className="w-4 h-4" />
            Delete Video
          </button>
        </div>
      )}

      {/* Video Card */}
      <div
        onClick={() => onClick?.(id)}
        className="bg-card rounded-xl border border-border overflow-hidden hover:shadow-lg transition-all cursor-pointer hover:border-brand/50"
      >
        <div className="relative aspect-video bg-muted">
          {thumbnailUrl && !imageError ? (
            <img
              src={thumbnailUrl}
              alt={title}
              className="w-full h-full object-cover"
              onError={() => setImageError(true)}
              loading="lazy"
            />
          ) : (
            <div className="w-full h-full flex items-center justify-center bg-gradient-to-br from-accent to-accent/50">
              {imageError ? (
                <ImageOff className="w-12 h-12 text-muted-foreground/30" />
              ) : (
                <PlayCircle className="w-12 h-12 text-brand/50" />
              )}
            </div>
          )}
          
          {duration !== '0:00' && (
            <div className="absolute bottom-2 right-2 bg-sidebar/70 text-sidebar-foreground text-xs px-2 py-1 rounded-md backdrop-blur-sm">
              <Clock className="w-3 h-3 inline mr-1" />
              {duration}
            </div>
          )}

          <div className="absolute inset-0 bg-black/0 group-hover:bg-black/30 transition-all flex items-center justify-center">
            <PlayCircle className="w-12 h-12 text-white opacity-0 group-hover:opacity-100 transition-all transform group-hover:scale-110" />
          </div>
        </div>

        <div className="p-4">
          <h3 className="font-medium text-foreground line-clamp-1 group-hover:text-brand transition-colors">
            {title}
          </h3>
          <p className="text-xs text-muted-foreground mt-2">
            Uploaded {formatDistanceToNow(uploadedAt)} ago
          </p>
        </div>
      </div>
    </div>
  );
};