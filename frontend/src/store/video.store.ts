import { create } from 'zustand';
import { persist } from 'zustand/middleware';

export interface Video {
  id: string;
  video_id: string;
  originalVideoId?: string;
  title: string;
  fileName?: string;
  uploadedAt: Date;
  duration: string;
  thumbnail?: string | null;
  status: 'uploading' | 'processing' | 'ready' | 'error';
  s3Url?: string | null;
  transcriptUrl?: string | null;
  fileSize?: number;
}

interface VideoStore {
  videos: Video[];
  isLoading: boolean;
  error: string | null;
  loadVideos: () => Promise<void>;
  getVideoById: (id: string) => Video | undefined;
  addVideo: (video: Video) => void;
  removeVideo: (id: string) => Promise<void>;
  updateVideo: (id: string, updates: Partial<Video>) => void;
  clearError: () => void;
}

const API_BASE_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

export const useVideoStore = create<VideoStore>()(
  persist(
    (set, get) => ({
      videos: [],
      isLoading: false,
      error: null,

      loadVideos: async () => {
        set({ isLoading: true, error: null });
        try {
          const response = await fetch(`${API_BASE_URL}/api/videos`, {
            headers: {
              'ngrok-skip-browser-warning': 'true'
            }
          });
          
          if (!response.ok) {
            throw new Error('Failed to load videos');
          }
          
          const data = await response.json();
          console.log("video_data in store ", data);
          // Transform API response to match our Video interface
          const videos: Video[] = data.videos.map((v: any) => ({
            id: v.id,
            video_id: v.video_id,
            title: v.title,
            uploadedAt: new Date(v.uploaded_at),
            duration: v.duration || '0:00',
            thumbnail: v.thumbnail_url,
            status: 'ready',
            s3Url: v.video_url,
            transcriptUrl: v.transcript_url,
            fileSize: v.file_size
          }));
          
          set({ videos, isLoading: false });
        } catch (error) {
          set({ 
            error: error instanceof Error ? error.message : 'Failed to load videos', 
            isLoading: false 
          });
        }
      },

      getVideoById: (id: string) => {
        return get().videos.find(v => v.id === id);
      },

      addVideo: (video: Video) => {
        set((state) => ({
          videos: [video, ...state.videos]
        }));
      },

      removeVideo: async (id: string) => {
        try {
          const video = get().videos.find(v => v.id === id);
          if (!video) return;

          const response = await fetch(`${API_BASE_URL}/api/videos/${encodeURIComponent(video.video_id)}`, {
            method: 'DELETE',
            headers: {
              'ngrok-skip-browser-warning': 'true'
            }
          });

          if (!response.ok) {
            throw new Error('Failed to delete video');
          }

          set((state) => ({
            videos: state.videos.filter(v => v.id !== id)
          }));
        } catch (error) {
          set({ 
            error: error instanceof Error ? error.message : 'Failed to delete video' 
          });
        }
      },

      updateVideo: (id: string, updates: Partial<Video>) => {
        set((state) => ({
          videos: state.videos.map(v => 
            v.id === id ? { ...v, ...updates } : v
          )
        }));
      },

      clearError: () => {
        set({ error: null });
      }
    }),
    {
      name: 'video-storage',
      partialize: (state) => ({ 
        videos: state.videos.map(v => ({
          ...v,
          uploadedAt: v.uploadedAt.toISOString()
        }))
      }),
      onRehydrateStorage: () => (state) => {
        if (state) {
          // Convert uploadedAt strings back to Date objects
          state.videos = state.videos.map(v => ({
            ...v,
            uploadedAt: new Date(v.uploadedAt)
          }));
        }
      }
    }
  )
);