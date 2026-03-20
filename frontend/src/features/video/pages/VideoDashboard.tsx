// import React, { useState, useEffect } from 'react';
// import { useNavigate } from 'react-router-dom';
// import { VideoCard } from '../components/VideoCard';
// import { VideoUploader } from '../components/VideoUploader';
// import { useVideoStore } from '@/store/video.store';
// import { Input } from '@/components/ui/input';
// import { Search, PlayCircle } from 'lucide-react';
// import { Button } from '@/components/ui/button';

// export const VideoDashboard: React.FC = () => {
//   const navigate = useNavigate();
//   const [isUploaderOpen, setIsUploaderOpen] = useState(false);
//   const [searchQuery, setSearchQuery] = useState('');
//   const { videos, loadVideos } = useVideoStore();

//   useEffect(() => {
//     loadVideos();
//   }, []);

//   const filteredVideos = videos
//     .filter(video => 
//       video.title.toLowerCase().includes(searchQuery.toLowerCase())
//     )
//     .sort((a, b) => {
//       const dateA = a.uploadedAt instanceof Date ? a.uploadedAt : new Date(a.uploadedAt);
//       const dateB = b.uploadedAt instanceof Date ? b.uploadedAt : new Date(b.uploadedAt);
//       return dateB.getTime() - dateA.getTime();
//     });

//   const handleVideoClick = (videoId: string) => {
//     navigate(`/watch/${videoId}`);
//   };

//   return (
//     <div className="min-h-screen bg-background">
//       {/* Header */}
//       <div className="bg-sidebar border-b border-border sticky top-0 z-10">
//         <div className="max-w-7xl mx-auto px-4 py-4">
//           <div className="flex items-center justify-between">
//             <div className="flex items-center gap-3">
//               <div className="w-10 h-10 rounded-lg bg-brand flex items-center justify-center">
//                 <PlayCircle className="w-6 h-6 text-brand-foreground" />
//               </div>
//               <h1 className="text-xl font-bold text-sidebar-foreground">Video Library</h1>
//             </div>
//           </div>
//         </div>
//       </div>

//       <main className="max-w-7xl mx-auto px-4 py-8">
//         <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4 mb-8">
//           <div>
//             <p className="text-sm text-muted-foreground">
//               {filteredVideos.length} {filteredVideos.length === 1 ? 'video' : 'videos'} uploaded
//             </p>
//           </div>

//           <div className="relative w-full md:w-64">
//             <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
//             <Input
//               placeholder="Search videos..."
//               value={searchQuery}
//               onChange={(e) => setSearchQuery(e.target.value)}
//               className="pl-9 bg-card border-border"
//             />
//           </div>
//         </div>

//         <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">
//           <VideoCard
//             id="upload"
//             title=""
//             uploadedAt={new Date()}
//             isFirst
//             onClick={() => setIsUploaderOpen(true)}
//           />

//           {filteredVideos.map((video) => (
//             <VideoCard
//               key={video.id}
//               id={video.id}
//               title={video.title}
//               duration={video.duration}
//               thumbnail={video.thumbnail}
//               uploadedAt={video.uploadedAt}
//               onClick={handleVideoClick}
//             />
//           ))}
//         </div>

//         {filteredVideos.length === 0 && !searchQuery && (
//           <div className="text-center py-16">
//             <div className="w-20 h-20 rounded-full bg-accent mx-auto mb-4 flex items-center justify-center">
//               <PlayCircle className="w-10 h-10 text-brand" />
//             </div>
//             <h3 className="text-lg font-medium text-foreground mb-2">
//               No videos yet
//             </h3>
//             <p className="text-sm text-muted-foreground mb-6">
//               Upload your first video to start learning
//             </p>
//             <Button
//               onClick={() => setIsUploaderOpen(true)}
//               className="bg-brand text-brand-foreground hover:bg-brand/90"
//             >
//               Upload Video
//             </Button>
//           </div>
//         )}
//       </main>

//       <VideoUploader
//         isOpen={isUploaderOpen}
//         onClose={() => setIsUploaderOpen(false)}
//         onUploadComplete={(videoId) => {
//           // Optionally navigate to the new video
//           // navigate(`/watch/${videoId}`);
//         }}
//       />
//     </div>
//   );
// };




import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useLocation } from 'react-router-dom';
import { VideoCard } from '../components/VideoCard';
import { VideoUploader } from '../components/VideoUploader';
import { useVideoStore } from '@/store/video.store';
import { Input } from '@/components/ui/input';
import { Search, PlayCircle, RefreshCw, AlertCircle } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Alert, AlertDescription } from '@/components/ui/alert';

export const VideoDashboard: React.FC = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const [isUploaderOpen, setIsUploaderOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const { videos, isLoading, error, loadVideos, clearError } = useVideoStore();

  useEffect(() => {
    if (!location.state?.fromWatch || videos.length === 0) {
      loadVideos();
    }
  }, [location.state]);

  const handleRefresh = () => {
    loadVideos();
  };

  const filteredVideos = videos
    .filter(video => 
      video.title.toLowerCase().includes(searchQuery.toLowerCase())
    )
    .sort((a, b) => {
      const dateA = a.uploadedAt instanceof Date ? a.uploadedAt : new Date(a.uploadedAt);
      const dateB = b.uploadedAt instanceof Date ? b.uploadedAt : new Date(b.uploadedAt);
      return dateB.getTime() - dateA.getTime();
    });

  const handleVideoClick = (videoId: string) => {
    navigate(`/watch/${videoId}`);
  };

  return (
    <div className="min-h-screen bg-background">
      {/* Header */}
      <div className="bg-sidebar border-b border-border sticky top-0 z-10">
        <div className="max-w-7xl mx-auto px-4 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-lg bg-white p-1 flex items-center justify-center">
                <img 
                  src="/logo_new.png" 
                  alt="Dopamine Lite Logo" 
                  className="w-full h-full object-cover"
                />
              </div>
              <h1 className="text-xl font-bold text-sidebar-foreground">Dopamine Lite</h1>
            </div>
            
            <Button
              variant="ghost"
              size="icon"
              onClick={handleRefresh}
              disabled={isLoading}
              className="text-sidebar-foreground hover:text-sidebar-foreground/80 hover:bg-white/10"
            >
              <RefreshCw className={`w-5 h-5 ${isLoading ? 'animate-spin' : ''}`} />
            </Button>
          </div>
        </div>
      </div>

      <main className="max-w-7xl mx-auto px-4 py-8">
        {error && (
          <Alert variant="destructive" className="mb-6">
            <AlertCircle className="h-4 w-4" />
            <AlertDescription className="flex items-center justify-between">
              <span>{error}</span>
              <Button 
                variant="outline" 
                size="sm" 
                onClick={clearError}
                className="ml-4"
              >
                Dismiss
              </Button>
            </AlertDescription>
          </Alert>
        )}

        <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4 mb-8">
          <div>
            {isLoading ? (
              <p className="text-sm text-muted-foreground">Loading videos...</p>
            ) : (
              <p className="text-sm text-muted-foreground">
                {filteredVideos.length} {filteredVideos.length === 1 ? 'video' : 'videos'} uploaded
              </p>
            )}
          </div>

          <div className="relative w-full md:w-64">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
            <Input
              placeholder="Search videos..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="pl-9 bg-card border-border"
              disabled={isLoading}
            />
          </div>
        </div>

        {isLoading ? (
          <div className="flex justify-center items-center py-16">
            <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-brand"></div>
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">
            <VideoCard
              id="upload"
              title=""
              uploadedAt={new Date()}
              isFirst
              onClick={() => setIsUploaderOpen(true)}
            />

            {filteredVideos.map((video) => (
              <VideoCard
                key={video.id}
                id={video.id}
                title={video.title}
                duration={video.duration}
                thumbnail={video.thumbnail || undefined}
                uploadedAt={video.uploadedAt}
                onClick={handleVideoClick}
              />
            ))}
          </div>
        )}

        {!isLoading && filteredVideos.length === 0 && !searchQuery && (
          <div className="text-center py-16">
            <div className="w-20 h-20 rounded-full bg-accent mx-auto mb-4 flex items-center justify-center">
              <PlayCircle className="w-10 h-10 text-brand" />
            </div>
            <h3 className="text-lg font-medium text-foreground mb-2">
              No videos yet
            </h3>
            <p className="text-sm text-muted-foreground mb-6">
              Upload your first video to start learning
            </p>
            <Button
              onClick={() => setIsUploaderOpen(true)}
              className="bg-brand text-brand-foreground hover:bg-brand/90"
            >
              Upload Video
            </Button>
          </div>
        )}

        {!isLoading && filteredVideos.length === 0 && searchQuery && (
          <div className="text-center py-16">
            <Search className="w-12 h-12 text-muted-foreground/30 mx-auto mb-4" />
            <h3 className="text-lg font-medium text-foreground mb-2">
              No videos found
            </h3>
            <p className="text-sm text-muted-foreground">
              No videos match your search "{searchQuery}"
            </p>
          </div>
        )}
      </main>

      <VideoUploader
        isOpen={isUploaderOpen}
        onClose={() => setIsUploaderOpen(false)}
        onUploadComplete={(videoId) => {
          loadVideos(); // Refresh the video list
        }}
      />
    </div>
  );
};