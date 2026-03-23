import React, { useState, useRef, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { ArrowLeft, Bot, User, Send, PlayCircle, Loader2, Trash2 } from 'lucide-react';
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
  const [seekToTime, setSeekToTime] = useState<number | null>(null);
  const processedSeekRef = useRef<number | null>(null);
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
        console.log('Using existing signed URL', video);
        setIsLoading(false);
        return;
      }

      setIsFetchingUrl(true);
      try {
        console.log('Fetching signed URL for:', video.video_id);
        
        
          
        // Update the video in store with signed URL
        updateVideo(video.id, { 
          s3Url: video.s3Url 
        });
        setVideoError(null);
       
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

  const handleClearChat = () => {
    setChatHistory([]);
    localStorage.removeItem(`chat_${videoId}`);
  };


  useEffect(() => {
    if (seekToTime !== null && processedSeekRef.current !== seekToTime) {
      processedSeekRef.current = seekToTime;
      // Reset seekToTime after a short delay to allow the video to seek
      const timer = setTimeout(() => {
        setSeekToTime(null);
        processedSeekRef.current = null;
      }, 100);
      
      return () => clearTimeout(timer);
    }
  }, [seekToTime]);

  const handleSeek = (timeString: string) => {
    const [minutes, seconds] = timeString.split(':').map(Number);
    const totalSeconds = (minutes * 60) + seconds;
    console.log("Seeked: ", totalSeconds);
    setSeekToTime(totalSeconds);
    setCurrentVideoTime(totalSeconds);
  };

  const handleVideoSeek = (time: number) => {
    console.log("Video seeked to:", time);
    setCurrentVideoTime(time);
  };

  const renderMessageContent = (content: string) => {
    // Use a regex that captures both times as separate groups
    const regex = /⏱️\s*\[▶ Play Video \((\d{2}:\d{2})\s*-\s*(\d{2}:\d{2})\)\]/g;
    const parts = [];
    let lastIndex = 0;
    let match;
    
    // Manual splitting to preserve matches with both times
    while ((match = regex.exec(content)) !== null) {
      // Add text before the match
      if (match.index > lastIndex) {
        parts.push(content.substring(lastIndex, match.index));
      }
      
      // Add the match with captured times
      parts.push({
        type: 'timestamp',
        fullMatch: match[0],
        startTime: match[1],
        endTime: match[2],
        index: match.index
      });
      
      lastIndex = match.index + match[0].length;
    }
    
    // Add remaining text
    if (lastIndex < content.length) {
      parts.push(content.substring(lastIndex));
    }
    
    return parts.map((part, index) => {
      // Handle timestamp parts
      if (typeof part !== 'string' && part.type === 'timestamp') {
        console.log("Found timestamp:", part.startTime, "-", part.endTime);
        
        return (
          <div key={index} className="flex flex-col content-between items-center gap-2 mb-3">
            {/* Timestamp buttons - Top row */}
            <div className="flex flex-row gap-1">
              <button 
                onClick={() => handleSeek(part.startTime)}
                className="inline-flex items-center gap-1.5 bg-accent text-brand px-3 py-1.5 rounded-lg text-sm font-bold hover:bg-accent/80 transition-colors border border-border shadow-sm"
                title={`Click to play video from ${part.startTime}`}
              >
                <PlayCircle className="w-4 h-4" />
                {part.startTime}
              </button>
              <button 
                onClick={() => handleSeek(part.endTime)}
                className="inline-flex items-center gap-1.5 bg-accent text-brand px-3 py-1.5 rounded-lg text-sm font-bold hover:bg-accent/80 transition-colors border border-border shadow-sm"
                title={`Click to play video from ${part.endTime}`}
              >
                <PlayCircle className="w-4 h-4" />
                {part.endTime}
              </button>
            </div>
          </div>
        );
      }
      
      // Handle regular text
      return (
        <span key={index}>
          {(typeof part === 'string' ? part : '').split('\n').map((line, i) => (
            <React.Fragment key={i}>
              <span dangerouslySetInnerHTML={{ 
                __html: line.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>') 
              }} />
              {i !== (typeof part === 'string' ? part : '').split('\n').length - 1 && <br />}
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
      console.log('API response:', data);

      if (response.ok) {
        const assistantMessage: ChatMessage = { 
          role: 'assistant', 
          content: data.answer 
        };
        const updatedHistory = [...newHistory, assistantMessage];
        setChatHistory(updatedHistory);
        localStorage.setItem(`chat_${videoId}`, JSON.stringify(updatedHistory));
      } else {
         // Handle different error types
        let errorMessage = '';
        
        if (response.status === 429) {
          // Rate limit error
          errorMessage = getRateLimitMessage(data);
        } else if (response.status === 503 || response.status === 504) {
          errorMessage = 'Service temporarily unavailable. Please try again in a few moments.';
        } else if (response.status === 500) {
          errorMessage = 'Server error. Our team has been notified. Please try again later.';
        } else {
          errorMessage = `Error: ${data.detail || 'Something went wrong'}`;
        }
        
        const errorMessageObj: ChatMessage = { 
          role: 'assistant', 
          content: errorMessage
        };
        setChatHistory([...newHistory, errorMessageObj]);
      }
    } catch (error) {
      const errorMessage: ChatMessage = { 
        role: 'assistant', 
        content: `Network Error: Could not connect.` 
      };
      setChatHistory([...newHistory, errorMessage]);
    } finally {
      setIsTyping(false);
    }
  };

  const getRateLimitMessage = (data: any): string => {
    let retryTime = '';
    
    // Try to extract retry time from error details
    if (data.details && data.details[2] && data.details[2].retryDelay) {
      const delaySeconds = data.details[2].retryDelay.replace('s', '');
      retryTime = ` Please try again in ${Math.ceil(parseInt(delaySeconds))} seconds.`;
    } else if (data.error?.details) {
      const retryInfo = data.error.details.find((d: any) => d.retryDelay);
      if (retryInfo) {
        const delaySeconds = retryInfo.retryDelay.replace('s', '');
        retryTime = ` Please try again in ${Math.ceil(parseInt(delaySeconds))} seconds.`;
      }
    }
    
    return `**Rate Limit Reached**\n\nThe AI assistant is currently busy. ${retryTime}\n\n*Free tier has a limit of 20 requests per day. Please wait a moment before sending more questions.*\n\n💡 **Tip**: You can still use the video player normally and review previous answers.`;
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
              onSeek={handleVideoSeek}
              seekTo={seekToTime}
              className="aspect-video"
              onError={(error) => {
                console.error('Video player error:', error);
                setVideoError(error);
              }}
            />
          )}
        </div>

        <div className="bg-card rounded-2xl shadow-sm border border-border flex flex-col h-[600px]">
          <div className="bg-sidebar p-4 rounded-t-2xl flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Bot className="w-5 h-5 text-brand" />
              <h2 className="text-sidebar-foreground font-semibold">AI Teaching Assistant</h2>
            </div>
            {chatHistory.length > 0 && (
              <Button
                variant="ghost"
                size="sm"
                onClick={handleClearChat}
                className="text-sidebar-foreground/70 hover:text-destructive hover:bg-destructive/10 gap-1.5"
                title="Clear chat history"
              >
                <Trash2 className="w-4 h-4" />
                <span className="text-xs">Clear</span>
              </Button>
            )}
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