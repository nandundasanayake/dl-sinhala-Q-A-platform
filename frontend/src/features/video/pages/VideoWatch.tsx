// import React, { useState, useRef, useEffect } from 'react';
// import { useParams, useNavigate } from 'react-router-dom';
// import { ArrowLeft, Bot, User, Send, PlayCircle } from 'lucide-react';
// import { Button } from '@/components/ui/button';
// import { VideoPlayer } from '../components/VideoPlayer';
// import { useVideoStore } from '@/store/video.store';

// interface ChatMessage {
//   role: 'user' | 'assistant';
//   content: string;
// }

// export const VideoWatch: React.FC = () => {
//   const { videoId } = useParams<{ videoId: string }>();
//   const navigate = useNavigate();
//   const { getVideoById } = useVideoStore();
  
//   const [chatHistory, setChatHistory] = useState<ChatMessage[]>([]);
//   const [question, setQuestion] = useState('');
//   const [isTyping, setIsTyping] = useState(false);
//   const [currentVideoTime, setCurrentVideoTime] = useState(0);
//   const [videoError, setVideoError] = useState<string | null>(null);
  
//   const chatEndRef = useRef<HTMLDivElement>(null);
//   const video = getVideoById(videoId || '');

//   useEffect(() => {
//     if (video) {
//       if (!video.s3Url) {
//         setVideoError('No video URL available');
//       }
//     }
//   }, [video]);

//   useEffect(() => {
//     const saved = localStorage.getItem(`chat_${videoId}`);
//     if (saved) {
//       try {
//         const parsed = JSON.parse(saved);
//         const validHistory: ChatMessage[] = parsed.filter(
//           (msg: any) => msg.role === 'user' || msg.role === 'assistant'
//         );
//         setChatHistory(validHistory);
//       } catch (error) {
//         console.error('Failed to parse chat history:', error);
//       }
//     }
//   }, [videoId]);

//   useEffect(() => {
//     chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
//   }, [chatHistory]);

//   const handleSeek = (timeString: string) => {
//     const [minutes, seconds] = timeString.split(':').map(Number);
//     const totalSeconds = (minutes * 60) + seconds;
//     setCurrentVideoTime(totalSeconds);
//   };

//   const renderMessageContent = (content: string) => {
//     const regex = /(⏱️\s*\[▶ Play Video \(\d{2}:\d{2}\s*-\s*\d{2}:\d{2}\)\])/g;
//     const parts = content.split(regex);
    
//     return parts.map((part, index) => {
//       if (part && part.startsWith('⏱️')) {
//         const timeMatch = part.match(/(\d{2}:\d{2})/);
//         const startTime = timeMatch ? timeMatch[0] : "00:00";
        
//         return (
//           <button 
//             key={index}
//             onClick={() => handleSeek(startTime)}
//             className="inline-flex items-center gap-1.5 bg-accent text-brand px-3 py-1.5 rounded-lg text-sm font-bold hover:bg-accent/80 transition-colors mt-2 border border-border shadow-sm"
//             title={`Click to play video from ${startTime}`}
//           >
//             <PlayCircle className="w-4 h-4" />
//             Play ({startTime})
//           </button>
//         );
//       }
      
//       return (
//         <span key={index}>
//           {part?.split('\n').map((line, i) => (
//             <React.Fragment key={i}>
//               <span dangerouslySetInnerHTML={{ 
//                 __html: line.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>') 
//               }} />
//               {i !== part.split('\n').length - 1 && <br />}
//             </React.Fragment>
//           ))}
//         </span>
//       );
//     });
//   };

//   const handleSendMessage = async (e: React.FormEvent) => {
//     e.preventDefault();
//     if (!question.trim() || !videoId) return;

//     const currentQuestion = question;
//     setQuestion('');
    
//     const userMessage: ChatMessage = { 
//       role: 'user', 
//       content: currentQuestion 
//     };
    
//     const newHistory = [...chatHistory, userMessage];
//     setChatHistory(newHistory);
//     setIsTyping(true);

//     try {
//       const response = await fetch('http://localhost:8000/api/chat', {
//         method: 'POST',
//         headers: { 'Content-Type': 'application/json' },
//         body: JSON.stringify({
//           video_id: videoId,
//           question: currentQuestion,
//           chat_history: chatHistory,
//         }),
//       });

//       const data = await response.json();

//       if (response.ok) {
//         const assistantMessage: ChatMessage = { 
//           role: 'assistant', 
//           content: data.answer 
//         };
//         const updatedHistory = [...newHistory, assistantMessage];
//         setChatHistory(updatedHistory);
//         localStorage.setItem(`chat_${videoId}`, JSON.stringify(updatedHistory));
//       } else {
//         const errorMessage: ChatMessage = { 
//           role: 'assistant', 
//           content: `❌ Error: ${data.detail}` 
//         };
//         setChatHistory([...newHistory, errorMessage]);
//       }
//     } catch (error) {
//       const errorMessage: ChatMessage = { 
//         role: 'assistant', 
//         content: `❌ Network Error: Could not connect.` 
//       };
//       setChatHistory([...newHistory, errorMessage]);
//     } finally {
//       setIsTyping(false);
//     }
//   };

//   if (!video) {
//     return (
//       <div className="min-h-screen bg-background flex items-center justify-center">
//         <div className="text-center">
//           <h2 className="text-xl font-semibold text-foreground mb-2">Video not found</h2>
//           <Button onClick={() => navigate('/dashboard')} variant="outline">
//             Back to Dashboard
//           </Button>
//         </div>
//       </div>
//     );
//   }

//   return (
//     <div className="min-h-screen bg-background">
//       <div className="bg-sidebar border-b border-border sticky top-0 z-10">
//         <div className="max-w-7xl mx-auto px-4 py-3 flex items-center gap-4">
//           <Button
//             variant="ghost"
//             size="icon"
//             onClick={() => navigate('/dashboard')}
//             className="text-sidebar-foreground hover:text-sidebar-foreground/80 hover:bg-white/10"
//           >
//             <ArrowLeft className="w-5 h-5" />
//           </Button>
//           <h1 className="text-lg font-semibold text-sidebar-foreground truncate">{video.title}</h1>
//         </div>
//       </div>

//       <main className="max-w-7xl mx-auto p-4 md:p-6 grid grid-cols-1 lg:grid-cols-3 gap-6">
//         <div className="lg:col-span-2 space-y-4">
//           {videoError ? (
//             <div className="bg-destructive/10 border border-destructive rounded-lg p-8 text-center">
//               <p className="text-destructive font-medium">⚠️ Video Error</p>
//               <p className="text-sm text-destructive/80 mt-1">{videoError}</p>
//             </div>
//           ) : (
//             <VideoPlayer
//               src={video.s3Url || ''}
//               title={video.title}
//               onSeek={(time) => setCurrentVideoTime(time)}
//               className="aspect-video"
//             />
//           )}
//         </div>

//         <div className="bg-card rounded-2xl shadow-sm border border-border flex flex-col h-[600px]">
//           <div className="bg-sidebar p-4 rounded-t-2xl flex items-center gap-2">
//             <Bot className="w-5 h-5 text-brand" />
//             <h2 className="text-sidebar-foreground font-semibold">AI Teaching Assistant</h2>
//           </div>

//           <div className="flex-1 overflow-y-auto p-4 space-y-4 bg-muted/30">
//             {chatHistory.length === 0 ? (
//               <div className="h-full flex flex-col items-center justify-center text-muted-foreground gap-3">
//                 <Bot className="w-12 h-12 text-muted-foreground/30" />
//                 <p className="text-sm text-center px-4">
//                   Ask questions about this video and get answers with timestamps!
//                 </p>
//               </div>
//             ) : (
//               chatHistory.map((msg, idx) => (
//                 <div key={idx} className={`flex gap-3 ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
//                   {msg.role === 'assistant' && (
//                     <div className="w-8 h-8 rounded-full bg-sidebar flex-shrink-0 flex items-center justify-center mt-1">
//                       <Bot className="w-4 h-4 text-sidebar-foreground" />
//                     </div>
//                   )}
                  
//                   <div className={`max-w-[85%] rounded-2xl p-3.5 text-sm shadow-sm ${
//                     msg.role === 'user' 
//                       ? 'bg-brand text-brand-foreground rounded-tr-none' 
//                       : 'bg-card border border-border text-foreground rounded-tl-none'
//                   }`}>
//                     {renderMessageContent(msg.content)}
//                   </div>

//                   {msg.role === 'user' && (
//                     <div className="w-8 h-8 rounded-full bg-muted flex-shrink-0 flex items-center justify-center mt-1">
//                       <User className="w-4 h-4 text-muted-foreground" />
//                     </div>
//                   )}
//                 </div>
//               ))
//             )}
            
//             {isTyping && (
//               <div className="flex gap-3 justify-start">
//                 <div className="w-8 h-8 rounded-full bg-sidebar flex items-center justify-center mt-1">
//                   <Bot className="w-4 h-4 text-sidebar-foreground" />
//                 </div>
//                 <div className="bg-card border border-border rounded-2xl rounded-tl-none p-4 flex gap-1">
//                   <div className="w-2 h-2 bg-muted-foreground/30 rounded-full animate-bounce"></div>
//                   <div className="w-2 h-2 bg-muted-foreground/30 rounded-full animate-bounce" style={{ animationDelay: '0.2s' }}></div>
//                   <div className="w-2 h-2 bg-muted-foreground/30 rounded-full animate-bounce" style={{ animationDelay: '0.4s' }}></div>
//                 </div>
//               </div>
//             )}
//             <div ref={chatEndRef} />
//           </div>

//           <div className="p-4 bg-card border-t border-border rounded-b-2xl">
//             <form onSubmit={handleSendMessage} className="flex gap-2">
//               <input
//                 type="text"
//                 value={question}
//                 onChange={(e) => setQuestion(e.target.value)}
//                 placeholder="Ask a question about the video..."
//                 className="flex-1 bg-background border border-input rounded-xl px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-ring focus:border-transparent"
//               />
//               <button
//                 type="submit"
//                 disabled={!question.trim() || isTyping}
//                 className="bg-brand hover:bg-brand/90 text-brand-foreground rounded-xl px-5 py-3 transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center"
//               >
//                 <Send className="w-5 h-5" />
//               </button>
//             </form>
//           </div>
//         </div>
//       </main>
//     </div>
//   );
// };




// import React, { useState, useRef, useEffect } from 'react';
// import { useParams, useNavigate } from 'react-router-dom';
// import { ArrowLeft, Bot, User, Send, PlayCircle, Loader2 } from 'lucide-react';
// import { Button } from '@/components/ui/button';
// import { VideoPlayer } from '../components/VideoPlayer';
// import { useVideoStore } from '@/store/video.store';

// interface ChatMessage {
//   role: 'user' | 'assistant';
//   content: string;
// }

// export const VideoWatch: React.FC = () => {
//   const { videoId } = useParams<{ videoId: string }>();
//   const navigate = useNavigate();
//   const { getVideoById, loadVideos } = useVideoStore();
  
//   const [chatHistory, setChatHistory] = useState<ChatMessage[]>([]);
//   const [question, setQuestion] = useState('');
//   const [isTyping, setIsTyping] = useState(false);
//   const [currentVideoTime, setCurrentVideoTime] = useState(0);
//   const [videoError, setVideoError] = useState<string | null>(null);
//   const [isLoading, setIsLoading] = useState(true);
  
//   const chatEndRef = useRef<HTMLDivElement>(null);
//   const video = getVideoById(videoId || '');

//   useEffect(() => {
//     // Load videos if not in store
//     if (!video && videoId) {
//       loadVideos().then(() => {
//         setIsLoading(false);
//       });
//     } else {
//       setIsLoading(false);
//     }
//   }, [videoId, video]);

//   useEffect(() => {
//     if (video) {
//       if (!video.s3Url) {
//         setVideoError('No video URL available');
//       } else {
//         setVideoError(null);
//       }
//     }
//   }, [video]);

//   useEffect(() => {
//     const saved = localStorage.getItem(`chat_${videoId}`);
//     if (saved) {
//       try {
//         const parsed = JSON.parse(saved);
//         const validHistory: ChatMessage[] = parsed.filter(
//           (msg: any) => msg.role === 'user' || msg.role === 'assistant'
//         );
//         setChatHistory(validHistory);
//       } catch (error) {
//         console.error('Failed to parse chat history:', error);
//       }
//     }
//   }, [videoId]);

//   useEffect(() => {
//     chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
//   }, [chatHistory]);

//   const handleSeek = (timeString: string) => {
//     const [minutes, seconds] = timeString.split(':').map(Number);
//     const totalSeconds = (minutes * 60) + seconds;
//     setCurrentVideoTime(totalSeconds);
//   };

//   // In VideoWatch.tsx, add this useEffect
// useEffect(() => {
//   if (video) {
//     console.log('Video object:', video);
//     console.log('S3 URL:', video.s3Url);
    
//     // Test if the URL is accessible
//     if (video.s3Url) {
//       fetch(video.s3Url, { method: 'HEAD' })
//         .then(response => {
//           console.log('Video URL status:', response.status);
//           if (!response.ok) {
//             setVideoError(`Video URL returned status ${response.status}`);
//           }
//         })
//         .catch(err => {
//           console.error('Error fetching video:', err);
//           setVideoError('Failed to access video URL');
//         });
//     }
//   }
// }, [video]);

//   const renderMessageContent = (content: string) => {
//     const regex = /(⏱️\s*\[▶ Play Video \(\d{2}:\d{2}\s*-\s*\d{2}:\d{2}\)\])/g;
//     const parts = content.split(regex);
    
//     return parts.map((part, index) => {
//       if (part && part.startsWith('⏱️')) {
//         const timeMatch = part.match(/(\d{2}:\d{2})/);
//         const startTime = timeMatch ? timeMatch[0] : "00:00";
        
//         return (
//           <button 
//             key={index}
//             onClick={() => handleSeek(startTime)}
//             className="inline-flex items-center gap-1.5 bg-accent text-brand px-3 py-1.5 rounded-lg text-sm font-bold hover:bg-accent/80 transition-colors mt-2 border border-border shadow-sm"
//             title={`Click to play video from ${startTime}`}
//           >
//             <PlayCircle className="w-4 h-4" />
//             Play ({startTime})
//           </button>
//         );
//       }
      
//       return (
//         <span key={index}>
//           {part?.split('\n').map((line, i) => (
//             <React.Fragment key={i}>
//               <span dangerouslySetInnerHTML={{ 
//                 __html: line.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>') 
//               }} />
//               {i !== part.split('\n').length - 1 && <br />}
//             </React.Fragment>
//           ))}
//         </span>
//       );
//     });
//   };

//   const handleSendMessage = async (e: React.FormEvent) => {
//     e.preventDefault();
//     if (!question.trim() || !videoId) return;

//     const currentQuestion = question;
//     setQuestion('');
    
//     const userMessage: ChatMessage = { 
//       role: 'user', 
//       content: currentQuestion 
//     };
    
//     const newHistory = [...chatHistory, userMessage];
//     setChatHistory(newHistory);
//     setIsTyping(true);

//     try {
//       const response = await fetch('http://localhost:8000/api/chat', {
//         method: 'POST',
//         headers: { 'Content-Type': 'application/json' },
//         body: JSON.stringify({
//           video_id: videoId,
//           question: currentQuestion,
//           chat_history: chatHistory,
//         }),
//       });

//       const data = await response.json();

//       if (response.ok) {
//         const assistantMessage: ChatMessage = { 
//           role: 'assistant', 
//           content: data.answer 
//         };
//         const updatedHistory = [...newHistory, assistantMessage];
//         setChatHistory(updatedHistory);
//         localStorage.setItem(`chat_${videoId}`, JSON.stringify(updatedHistory));
//       } else {
//         const errorMessage: ChatMessage = { 
//           role: 'assistant', 
//           content: `❌ Error: ${data.detail}` 
//         };
//         setChatHistory([...newHistory, errorMessage]);
//       }
//     } catch (error) {
//       const errorMessage: ChatMessage = { 
//         role: 'assistant', 
//         content: `❌ Network Error: Could not connect.` 
//       };
//       setChatHistory([...newHistory, errorMessage]);
//     } finally {
//       setIsTyping(false);
//     }
//   };

//   if (isLoading) {
//     return (
//       <div className="min-h-screen bg-background flex items-center justify-center">
//         <div className="text-center">
//           <Loader2 className="w-12 h-12 animate-spin text-brand mx-auto mb-4" />
//           <p className="text-muted-foreground">Loading video...</p>
//         </div>
//       </div>
//     );
//   }

//   if (!video) {
//     return (
//       <div className="min-h-screen bg-background flex items-center justify-center">
//         <div className="text-center">
//           <h2 className="text-xl font-semibold text-foreground mb-2">Video not found</h2>
//           <p className="text-muted-foreground mb-4">The video you're looking for doesn't exist.</p>
//           <Button onClick={() => navigate('/dashboard')} variant="outline">
//             Back to Dashboard
//           </Button>
//         </div>
//       </div>
//     );
//   }

//   return (
//     <div className="min-h-screen bg-background">
//       <div className="bg-sidebar border-b border-border sticky top-0 z-10">
//         <div className="max-w-7xl mx-auto px-4 py-3 flex items-center gap-4">
//           <Button
//             variant="ghost"
//             size="icon"
//             onClick={() => navigate('/dashboard')}
//             className="text-sidebar-foreground hover:text-sidebar-foreground/80 hover:bg-white/10"
//           >
//             <ArrowLeft className="w-5 h-5" />
//           </Button>
//           <h1 className="text-lg font-semibold text-sidebar-foreground truncate">{video.title}</h1>
//         </div>
//       </div>

//       <main className="max-w-7xl mx-auto p-4 md:p-6 grid grid-cols-1 lg:grid-cols-3 gap-6">
//         <div className="lg:col-span-2 space-y-4">
//           {videoError ? (
//             <div className="bg-destructive/10 border border-destructive rounded-lg p-8 text-center">
//               <p className="text-destructive font-medium">⚠️ Video Error</p>
//               <p className="text-sm text-destructive/80 mt-1">{videoError}</p>
//               <Button 
//                 onClick={() => navigate('/dashboard')} 
//                 variant="outline" 
//                 className="mt-4"
//               >
//                 Back to Dashboard
//               </Button>
//             </div>
//           ) : (
//             <VideoPlayer
//               src={video.s3Url || ''}
//               title={video.title}
//               onSeek={(time) => setCurrentVideoTime(time)}
//               className="aspect-video"
//             />
//           )}
//         </div>

//         <div className="bg-card rounded-2xl shadow-sm border border-border flex flex-col h-[600px]">
//           <div className="bg-sidebar p-4 rounded-t-2xl flex items-center gap-2">
//             <Bot className="w-5 h-5 text-brand" />
//             <h2 className="text-sidebar-foreground font-semibold">AI Teaching Assistant</h2>
//           </div>

//           <div className="flex-1 overflow-y-auto p-4 space-y-4 bg-muted/30">
//             {chatHistory.length === 0 ? (
//               <div className="h-full flex flex-col items-center justify-center text-muted-foreground gap-3">
//                 <Bot className="w-12 h-12 text-muted-foreground/30" />
//                 <p className="text-sm text-center px-4">
//                   Ask questions about this video and get answers with timestamps!
//                 </p>
//               </div>
//             ) : (
//               chatHistory.map((msg, idx) => (
//                 <div key={idx} className={`flex gap-3 ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
//                   {msg.role === 'assistant' && (
//                     <div className="w-8 h-8 rounded-full bg-sidebar flex-shrink-0 flex items-center justify-center mt-1">
//                       <Bot className="w-4 h-4 text-sidebar-foreground" />
//                     </div>
//                   )}
                  
//                   <div className={`max-w-[85%] rounded-2xl p-3.5 text-sm shadow-sm ${
//                     msg.role === 'user' 
//                       ? 'bg-brand text-brand-foreground rounded-tr-none' 
//                       : 'bg-card border border-border text-foreground rounded-tl-none'
//                   }`}>
//                     {renderMessageContent(msg.content)}
//                   </div>

//                   {msg.role === 'user' && (
//                     <div className="w-8 h-8 rounded-full bg-muted flex-shrink-0 flex items-center justify-center mt-1">
//                       <User className="w-4 h-4 text-muted-foreground" />
//                     </div>
//                   )}
//                 </div>
//               ))
//             )}
            
//             {isTyping && (
//               <div className="flex gap-3 justify-start">
//                 <div className="w-8 h-8 rounded-full bg-sidebar flex items-center justify-center mt-1">
//                   <Bot className="w-4 h-4 text-sidebar-foreground" />
//                 </div>
//                 <div className="bg-card border border-border rounded-2xl rounded-tl-none p-4 flex gap-1">
//                   <div className="w-2 h-2 bg-muted-foreground/30 rounded-full animate-bounce"></div>
//                   <div className="w-2 h-2 bg-muted-foreground/30 rounded-full animate-bounce" style={{ animationDelay: '0.2s' }}></div>
//                   <div className="w-2 h-2 bg-muted-foreground/30 rounded-full animate-bounce" style={{ animationDelay: '0.4s' }}></div>
//                 </div>
//               </div>
//             )}
//             <div ref={chatEndRef} />
//           </div>

//           <div className="p-4 bg-card border-t border-border rounded-b-2xl">
//             <form onSubmit={handleSendMessage} className="flex gap-2">
//               <input
//                 type="text"
//                 value={question}
//                 onChange={(e) => setQuestion(e.target.value)}
//                 placeholder="Ask a question about the video..."
//                 className="flex-1 bg-background border border-input rounded-xl px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-ring focus:border-transparent"
//               />
//               <button
//                 type="submit"
//                 disabled={!question.trim() || isTyping}
//                 className="bg-brand hover:bg-brand/90 text-brand-foreground rounded-xl px-5 py-3 transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center"
//               >
//                 <Send className="w-5 h-5" />
//               </button>
//             </form>
//           </div>
//         </div>
//       </main>
//     </div>
//   );
// };




import React, { useState, useRef, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { ArrowLeft, Bot, User, Send, PlayCircle, Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { VideoPlayer } from '../components/VideoPlayer';
import { useVideoStore } from '@/store/video.store';

const API_BASE_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
}

export const VideoWatch: React.FC = () => {
  const { videoId } = useParams<{ videoId: string }>();
  const navigate = useNavigate();
  const { getVideoById, updateVideo, loadVideos } = useVideoStore();
  
  const [chatHistory, setChatHistory] = useState<ChatMessage[]>([]);
  const [question, setQuestion] = useState('');
  const [isTyping, setIsTyping] = useState(false);
  const [currentVideoTime, setCurrentVideoTime] = useState(0);
  const [videoError, setVideoError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isFetchingUrl, setIsFetchingUrl] = useState(false);
  
  const chatEndRef = useRef<HTMLDivElement>(null);
  const video = getVideoById(videoId || '');

  // Fetch signed URL when component mounts
  useEffect(() => {
    const fetchSignedUrl = async () => {
      if (!video || !video.video_id) {
        setIsLoading(false);
        return;
      }

      // If we already have a signed URL that starts with https, use it
      if (video.s3Url && video.s3Url.startsWith('https://')) {
        console.log('Using existing signed URL');
        setIsLoading(false);
        return;
      }

      setIsFetchingUrl(true);
      try {
        console.log('Fetching signed URL for:', video.video_id);
        const response = await fetch(
          `${API_BASE_URL}/api/videos/${encodeURIComponent(video.video_id)}/signed-url`
        );
        
        if (response.ok) {
          const data = await response.json();
          console.log('Received signed URL');
          
          // Update the video in store with signed URL
          updateVideo(video.id, { 
            s3Url: data.url 
          });
          setVideoError(null);
        } else {
          const errorText = await response.text();
          console.error('Failed to get signed URL:', errorText);
          setVideoError('Failed to get video URL');
        }
      } catch (error) {
        console.error('Error fetching signed URL:', error);
        setVideoError('Failed to load video');
      } finally {
        setIsFetchingUrl(false);
        setIsLoading(false);
      }
    };

    fetchSignedUrl();
  }, [video?.id, video?.video_id]);

  // Load videos if not in store
  useEffect(() => {
    if (!video && videoId) {
      loadVideos().then(() => {
        setIsLoading(false);
      });
    }
  }, [videoId, video]);

  // Load chat history
  useEffect(() => {
    const saved = localStorage.getItem(`chat_${videoId}`);
    if (saved) {
      try {
        const parsed = JSON.parse(saved);
        const validHistory: ChatMessage[] = parsed.filter(
          (msg: any) => msg.role === 'user' || msg.role === 'assistant'
        );
        setChatHistory(validHistory);
      } catch (error) {
        console.error('Failed to parse chat history:', error);
      }
    }
  }, [videoId]);

  // Scroll to bottom of chat
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [chatHistory]);

  const handleSeek = (timeString: string) => {
    const [minutes, seconds] = timeString.split(':').map(Number);
    const totalSeconds = (minutes * 60) + seconds;
    console.log("Seeked: ", totalSeconds);
    setCurrentVideoTime(totalSeconds);
  };

  const renderMessageContent = (content: string) => {
    const regex = /(⏱️\s*\[▶ Play Video \(\d{2}:\d{2}\s*-\s*\d{2}:\d{2}\)\])/g;
    const parts = content.split(regex);
    
    return parts.map((part, index) => {
      if (part && part.startsWith('⏱️')) {
        const timeMatch = part.match(/(\d{2}:\d{2})/);
        const startTime = timeMatch ? timeMatch[0] : "00:00";
        
        return (
          <button 
            key={index}
            onClick={() => handleSeek(startTime)}
            className="inline-flex items-center gap-1.5 bg-accent text-brand px-3 py-1.5 rounded-lg text-sm font-bold hover:bg-accent/80 transition-colors mt-2 border border-border shadow-sm"
            title={`Click to play video from ${startTime}`}
          >
            <PlayCircle className="w-4 h-4" />
            Play ({startTime})
          </button>
        );
      }
      
      return (
        <span key={index}>
          {part?.split('\n').map((line, i) => (
            <React.Fragment key={i}>
              <span dangerouslySetInnerHTML={{ 
                __html: line.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>') 
              }} />
              {i !== part.split('\n').length - 1 && <br />}
            </React.Fragment>
          ))}
        </span>
      );
    });
  };

  const handleSendMessage = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!question.trim() || !videoId) return;

    const currentQuestion = question;
    setQuestion('');
    
    const userMessage: ChatMessage = { 
      role: 'user', 
      content: currentQuestion 
    };
    
    const newHistory = [...chatHistory, userMessage];
    setChatHistory(newHistory);
    setIsTyping(true);

    try {
      const response = await fetch(`${API_BASE_URL}/api/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          video_id: videoId,
          question: currentQuestion,
          chat_history: chatHistory,
        }),
      });

      const data = await response.json();

      if (response.ok) {
        const assistantMessage: ChatMessage = { 
          role: 'assistant', 
          content: data.answer 
        };
        const updatedHistory = [...newHistory, assistantMessage];
        setChatHistory(updatedHistory);
        localStorage.setItem(`chat_${videoId}`, JSON.stringify(updatedHistory));
      } else {
        const errorMessage: ChatMessage = { 
          role: 'assistant', 
          content: `❌ Error: ${data.detail}` 
        };
        setChatHistory([...newHistory, errorMessage]);
      }
    } catch (error) {
      const errorMessage: ChatMessage = { 
        role: 'assistant', 
        content: `❌ Network Error: Could not connect.` 
      };
      setChatHistory([...newHistory, errorMessage]);
    } finally {
      setIsTyping(false);
    }
  };

  if (isLoading || isFetchingUrl) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <div className="text-center">
          <Loader2 className="w-12 h-12 animate-spin text-brand mx-auto mb-4" />
          <p className="text-muted-foreground">
            {isFetchingUrl ? 'Loading video...' : 'Loading...'}
          </p>
        </div>
      </div>
    );
  }

  if (!video) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <div className="text-center">
          <h2 className="text-xl font-semibold text-foreground mb-2">Video not found</h2>
          <p className="text-muted-foreground mb-4">The video you're looking for doesn't exist.</p>
          <Button onClick={() => navigate('/dashboard')} variant="outline">
            Back to Dashboard
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background">
      <div className="bg-sidebar border-b border-border sticky top-0 z-10">
        <div className="max-w-7xl mx-auto px-4 py-3 flex items-center gap-4">
          <Button
            variant="ghost"
            size="icon"
            onClick={() => navigate('/dashboard', { state: { fromWatch: true } })}
            className="text-sidebar-foreground hover:text-sidebar-foreground/80 hover:bg-white/10"
          >
            <ArrowLeft className="w-5 h-5" />
          </Button>
          <h1 className="text-lg font-semibold text-sidebar-foreground truncate">{video.title}</h1>
        </div>
      </div>

      <main className="max-w-7xl mx-auto p-4 md:p-6 grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 space-y-4">
          {videoError ? (
            <div className="bg-destructive/10 border border-destructive rounded-lg p-8 text-center">
              <p className="text-destructive font-medium">⚠️ Video Error</p>
              <p className="text-sm text-destructive/80 mt-1">{videoError}</p>
              <Button 
                onClick={() => navigate('/dashboard')} 
                variant="outline" 
                className="mt-4"
              >
                Back to Dashboard
              </Button>
            </div>
          ) : (
            <VideoPlayer
              src={video.s3Url || ''}
              title={video.title}
              onSeek={(time) => setCurrentVideoTime(time)}
              className="aspect-video"
              onError={(error) => {
                console.error('Video player error:', error);
                setVideoError(error);
              }}
            />
          )}
        </div>

        <div className="bg-card rounded-2xl shadow-sm border border-border flex flex-col h-[600px]">
          <div className="bg-sidebar p-4 rounded-t-2xl flex items-center gap-2">
            <Bot className="w-5 h-5 text-brand" />
            <h2 className="text-sidebar-foreground font-semibold">AI Teaching Assistant</h2>
          </div>

          <div className="flex-1 overflow-y-auto p-4 space-y-4 bg-muted/30">
            {chatHistory.length === 0 ? (
              <div className="h-full flex flex-col items-center justify-center text-muted-foreground gap-3">
                <Bot className="w-12 h-12 text-muted-foreground/30" />
                <p className="text-sm text-center px-4">
                  Ask questions about this video and get answers with timestamps!
                </p>
              </div>
            ) : (
              chatHistory.map((msg, idx) => (
                <div key={idx} className={`flex gap-3 ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                  {msg.role === 'assistant' && (
                    <div className="w-8 h-8 rounded-full bg-sidebar flex-shrink-0 flex items-center justify-center mt-1">
                      <Bot className="w-4 h-4 text-sidebar-foreground" />
                    </div>
                  )}
                  
                  <div className={`max-w-[85%] rounded-2xl p-3.5 text-sm shadow-sm ${
                    msg.role === 'user' 
                      ? 'bg-brand text-brand-foreground rounded-tr-none' 
                      : 'bg-card border border-border text-foreground rounded-tl-none'
                  }`}>
                    {renderMessageContent(msg.content)}
                  </div>

                  {msg.role === 'user' && (
                    <div className="w-8 h-8 rounded-full bg-muted flex-shrink-0 flex items-center justify-center mt-1">
                      <User className="w-4 h-4 text-muted-foreground" />
                    </div>
                  )}
                </div>
              ))
            )}
            
            {isTyping && (
              <div className="flex gap-3 justify-start">
                <div className="w-8 h-8 rounded-full bg-sidebar flex items-center justify-center mt-1">
                  <Bot className="w-4 h-4 text-sidebar-foreground" />
                </div>
                <div className="bg-card border border-border rounded-2xl rounded-tl-none p-4 flex gap-1">
                  <div className="w-2 h-2 bg-muted-foreground/30 rounded-full animate-bounce"></div>
                  <div className="w-2 h-2 bg-muted-foreground/30 rounded-full animate-bounce" style={{ animationDelay: '0.2s' }}></div>
                  <div className="w-2 h-2 bg-muted-foreground/30 rounded-full animate-bounce" style={{ animationDelay: '0.4s' }}></div>
                </div>
              </div>
            )}
            <div ref={chatEndRef} />
          </div>

          <div className="p-4 bg-card border-t border-border rounded-b-2xl">
            <form onSubmit={handleSendMessage} className="flex gap-2">
              <input
                type="text"
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                placeholder="Ask a question about the video..."
                className="flex-1 bg-background border border-input rounded-xl px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-ring focus:border-transparent"
              />
              <button
                type="submit"
                disabled={!question.trim() || isTyping}
                className="bg-brand hover:bg-brand/90 text-brand-foreground rounded-xl px-5 py-3 transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center"
              >
                <Send className="w-5 h-5" />
              </button>
            </form>
          </div>
        </div>
      </main>
    </div>
  );
};