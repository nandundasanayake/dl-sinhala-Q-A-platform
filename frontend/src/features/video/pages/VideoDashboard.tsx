// src/features/video/pages/VideoDashboard.tsx
import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { PageHeader } from '@/components/layout/PageHeader';
import { VideoCard } from '../components/VideoCard';
import { VideoUploader } from '../components/VideoUploader';
import { useVideoStore } from '@/store/video.store';
import { Input } from '@/components/ui/input';
import { Search, PlayCircle } from 'lucide-react';

export const VideoDashboard: React.FC = () => {
  const navigate = useNavigate();
  const [isUploaderOpen, setIsUploaderOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const { videos, loadVideos } = useVideoStore();

  useEffect(() => {
    loadVideos();
  }, []);

  const filteredVideos = videos
    .filter(video => 
      video.title.toLowerCase().includes(searchQuery.toLowerCase())
    )
    .sort((a, b) => {
        // Safely handle dates
        const dateA = a.uploadedAt instanceof Date ? a.uploadedAt : new Date(a.uploadedAt);
        const dateB = b.uploadedAt instanceof Date ? b.uploadedAt : new Date(b.uploadedAt);
        return dateB.getTime() - dateA.getTime();
  });
    

  const handleVideoClick = (videoId: string) => {
    navigate(`/watch/${videoId}`);
  };

  return (
    <div className="min-h-screen bg-gray-50">
      {/* <PageHeader
        title="My Videos"
        viewMode="student"
        setViewMode={() => {}}
      /> */}

      <main className="max-w-7xl mx-auto px-4 py-8">
        {/* Header */}
        <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4 mb-8">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">Video Library</h1>
            <p className="text-sm text-gray-500 mt-1">
              {filteredVideos.length} videos uploaded
            </p>
          </div>

          <div className="relative w-full md:w-64">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
            <Input
              placeholder="Search videos..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="pl-9"
            />
          </div>
        </div>

        {/* Video Grid */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">
          {/* Upload Card */}
          <VideoCard
            id="upload"
            title=""
            uploadedAt={new Date()}
            isFirst
            onClick={() => setIsUploaderOpen(true)}
          />

          {/* Video Cards */}
          {filteredVideos.map((video) => (
            <VideoCard
              key={video.id}
              id={video.id}
              title={video.title}
              duration={video.duration}
              thumbnail={video.thumbnail}
              uploadedAt={video.uploadedAt}
              onClick={handleVideoClick}
            />
          ))}
        </div>

        {/* Empty State */}
        {filteredVideos.length === 0 && !searchQuery && (
          <div className="text-center py-16">
            <div className="w-20 h-20 rounded-full bg-dopamine-light mx-auto mb-4 flex items-center justify-center">
              <PlayCircle className="w-10 h-10 text-dopamine-accent" />
            </div>
            <h3 className="text-lg font-medium text-gray-900 mb-2">
              No videos yet
            </h3>
            <p className="text-sm text-gray-500 mb-6">
              Upload your first video to start learning
            </p>
            <button
              onClick={() => setIsUploaderOpen(true)}
              className="bg-dopamine-dark text-white px-6 py-3 rounded-lg font-medium hover:bg-opacity-90 transition-colors"
            >
              Upload Video
            </button>
          </div>
        )}
      </main>

      <VideoUploader
        isOpen={isUploaderOpen}
        onClose={() => setIsUploaderOpen(false)}
      />
    </div>
  );
};