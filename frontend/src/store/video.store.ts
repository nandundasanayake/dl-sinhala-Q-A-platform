// src/store/video.store.ts
import { create } from 'zustand';
import { persist } from 'zustand/middleware';

export interface Video {
  id: string;
  originalVideoId?: string;
  title: string;
  fileName: string;
  uploadedAt: Date;
  duration: string;
  thumbnail?: string;
  status: 'processing' | 'ready' | 'error';
  s3Url?: string;
  transcriptUrl?: string;
}

interface VideoStore {
  videos: Video[];
  addVideo: (video: Omit<Video, 'uploadedAt'> & { uploadedAt?: Date }) => void;
  updateVideo: (id: string, updates: Partial<Video>) => void;
  removeVideo: (id: string) => void;
  getVideoById: (id: string) => Video | undefined;
  loadVideos: () => void;
}

export const useVideoStore = create<VideoStore>()(
  persist(
    (set, get) => ({
      videos: [],
      
      addVideo: (video) => {
        const newVideo: Video = {
          ...video,
          id: video.id || `${Date.now()}-${Math.random().toString(36).substr(2, 9)}`,
          uploadedAt: video.uploadedAt || new Date(),
        };
        set((state) => ({
          videos: [newVideo, ...state.videos],
        }));

        return newVideo.id;
      },
      
      updateVideo: (id, updates) => {
        set((state) => ({
          videos: state.videos.map((v) =>
            v.id === id ? { ...v, ...updates } : v
          ),
        }));
      },
      
      removeVideo: (id) => {
        set((state) => ({
          videos: state.videos.filter((v) => v.id !== id),
        }));
      },
      
      getVideoById: (id) => {
        return get().videos.find((v) => v.id === id);
      },
      
      loadVideos: () => {
        // Load from localStorage or API
        const stored = localStorage.getItem('videos');
        if (stored) {
          try {
            const parsed = JSON.parse(stored);
            // Convert date strings back to Date objects
            const withDates = parsed.map((v: any) => ({
              ...v,
              uploadedAt: new Date(v.uploadedAt),
            }));
            set({ videos: withDates });
          } catch (error) {
            console.error('Failed to load videos:', error);
          }
        }
      },
    }),
    {
      name: 'video-storage',
    }
  )
);