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
    let totalSeconds = 0;
    
    // Check if the timestamp has hours (format: HH:MM:SS)
    const parts = timeString.split(':');
    
    if (parts.length === 3) {
      // Format: HH:MM:SS
      const hours = parseInt(parts[0]);
      const minutes = parseInt(parts[1]);
      const seconds = parseInt(parts[2]);
      totalSeconds = (hours * 3600) + (minutes * 60) + seconds;
    } else if (parts.length === 2) {
      // Format: MM:SS
      const minutes = parseInt(parts[0]);
      const seconds = parseInt(parts[1]);
      totalSeconds = (minutes * 60) + seconds;
    } else {
      // Invalid format, try to parse as seconds
      console.error('Invalid time format:', timeString);
      return;
    }
    
    console.log("Seeking to:", timeString, "->", totalSeconds, "seconds");
    setSeekToTime(totalSeconds);
    setCurrentVideoTime(totalSeconds);
  };

  const handleVideoSeek = (time: number) => {
    console.log("Video seeked to:", time);
    setCurrentVideoTime(time);
  };

  const cleanContent = (content: string): string => {
    // Remove multiple consecutive newlines (3 or more) and replace with single newline
    let cleaned = content.replace(/\n{3,}/g, '\n\n');
    
    // Remove empty lines that contain only whitespace
    cleaned = cleaned.replace(/^\s*$\n/gm, '');
    
    // Remove spaces before timestamps
    cleaned = cleaned.replace(/\s*\n\s*(\d{2}:\d{2})/g, '\n$1');
    
    return cleaned;
  };

  const renderMessageContent = (content: string) => {
    // First, clean the content to remove extra blank lines
    let processedContent = cleanContent(content);
    
    // Step 1: Convert the specific format "⏱️ [▶ Play Video (HH:MM:SS - HH:MM:SS)]" 
    // to individual timestamp buttons (only showing start time)
    
    // Handle timestamps with hours (HH:MM:SS format)
    const timestampWithHoursRegex = /⏱️\s*\[▶ Play Video\s*\((\d{2}:\d{2}:\d{2})\s*-\s*(\d{2}:\d{2}:\d{2})\)\]/g;
    
    // Handle timestamps without hours (MM:SS format)
    const timestampWithoutHoursRegex = /⏱️\s*\[▶ Play Video\s*\((\d{2}:\d{2})\s*-\s*(\d{2}:\d{2})\)\]/g;
    
    // Replace both formats with a placeholder marker that we'll parse later
    // This ensures we don't lose any timestamps during other transformations
    processedContent = processedContent.replace(timestampWithHoursRegex, (match, start, end) => {
      return `⏱️_TIMESTAMP_${start}_${end}`;
    });
    
    processedContent = processedContent.replace(timestampWithoutHoursRegex, (match, start, end) => {
      return `⏱️_TIMESTAMP_${start}_${end}`;
    });
    
    // Now handle the existing transformations for other timestamp formats
    // Convert standalone timestamps (like "07:50\n08:31") into proper format
    processedContent = processedContent.replace(
      /(\d{2}:\d{2})\s*\n\s*(\d{2}:\d{2})/g,
      (match, start, end) => {
        return `⏱️_TIMESTAMP_${start}_${end}`;
      }
    );
    
    // Convert timestamps in format "07:50 - 08:31" that aren't already wrapped
    processedContent = processedContent.replace(
      /(?<!⏱️_TIMESTAMP_)(\d{2}:\d{2})\s*-\s*(\d{2}:\d{2})(?!_)/g,
      (match, start, end) => {
        return `⏱️_TIMESTAMP_${start}_${end}`;
      }
    );
    
    // Pattern 1: Handle combined timestamps with one "▶ Play Video" and multiple timestamps
    const pattern1 = /⏱️\s*\[▶ Play Video\s*\(([^)]+)\)(?:,\s*\(([^)]+)\))*\]/g;
    
    processedContent = processedContent.replace(pattern1, (match: string) => {
      const timestampRegex = /(\d{2}:\d{2})\s*-\s*(\d{2}:\d{2})/g;
      const timestamps: Array<{start: string; end: string}> = [];
      let timestampMatch;
      
      while ((timestampMatch = timestampRegex.exec(match)) !== null) {
        timestamps.push({
          start: timestampMatch[1],
          end: timestampMatch[2]
        });
      }
      
      const newBlocks = timestamps.map(ts => {
        return `⏱️_TIMESTAMP_${ts.start}_${ts.end}`;
      });
      
      return '\n' + newBlocks.join('\n');
    });
    
    // Pattern 2: Handle combined timestamps with multiple "▶ Play Video" in one line
    const pattern2 = /⏱️\s*\[▶ Play Video\s*\(([^)]+)\)\],?\s*⏱️\s*\[▶ Play Video\s*\(([^)]+)\)\]/g;
    
    processedContent = processedContent.replace(pattern2, (match: string, ts1: string, ts2: string) => {
      const timeMatch1 = ts1.match(/(\d{2}:\d{2})\s*-\s*(\d{2}:\d{2})/);
      const timeMatch2 = ts2.match(/(\d{2}:\d{2})\s*-\s*(\d{2}:\d{2})/);
      
      const blocks = [];
      if (timeMatch1) {
        blocks.push(`⏱️_TIMESTAMP_${timeMatch1[1]}_${timeMatch1[2]}`);
      }
      if (timeMatch2) {
        blocks.push(`⏱️_TIMESTAMP_${timeMatch2[1]}_${timeMatch2[2]}`);
      }
      
      return '\n' + blocks.join('\n');
    });
    
    // Pattern 3: Handle format where timestamps are in parentheses without the emoji repeated
    const pattern3 = /⏱️\s*\[▶ Play Video\s*\(([^)]+)\)(?:,\s*\(([^)]+)\))*\]/g;
    
    processedContent = processedContent.replace(pattern3, (match: string) => {
      const allTimestamps = [];
      const tsRegex = /(\d{2}:\d{2})\s*-\s*(\d{2}:\d{2})/g;
      let tsMatch;
      
      while ((tsMatch = tsRegex.exec(match)) !== null) {
        allTimestamps.push({
          start: tsMatch[1],
          end: tsMatch[2]
        });
      }
      
      if (allTimestamps.length > 0) {
        const blocks = allTimestamps.map(ts => 
          `⏱️_TIMESTAMP_${ts.start}_${ts.end}`
        );
        return '\n' + blocks.join('\n');
      }
      
      return match;
    });
    
    // Now parse all the timestamp markers we've created
    const timestampMarkerRegex = /⏱️_TIMESTAMP_(\d{2}:\d{2}(?::\d{2})?)_(\d{2}:\d{2}(?::\d{2})?)/g;
    const parts: (string | { type: 'timestamp'; startTime: string; endTime: string })[] = [];
    let lastIndex = 0;
    let match: RegExpExecArray | null;
    
    while ((match = timestampMarkerRegex.exec(processedContent)) !== null) {
      if (match.index > lastIndex) {
        const textBefore = processedContent.substring(lastIndex, match.index);
        // Only add if it's not just whitespace
        if (textBefore.trim()) {
          parts.push(textBefore);
        }
      }
      
      parts.push({
        type: 'timestamp',
        startTime: match[1],
        endTime: match[2]
      });
      
      lastIndex = match.index + match[0].length;
    }
    
    if (lastIndex < processedContent.length) {
      const remainingText = processedContent.substring(lastIndex);
      if (remainingText.trim()) {
        parts.push(remainingText);
      }
    }
    
    return parts.map((part, index) => {
      if (typeof part !== 'string' && part.type === 'timestamp') {
        return (
          <div key={index} className="inline-flex flex-row gap-1 mr-1 mb-3 mt-1 mx-0">
            <button 
              onClick={() => handleSeek(part.startTime)}
              className="inline-flex items-center gap-1.2 bg-accent text-brand px-2 py-1 rounded-md text-xs font-medium hover:bg-accent/80 transition-colors border border-border"
              title={`Click to play video from ${part.startTime}`}
            >
              <PlayCircle className="w-3 h-3" />
              {part.startTime}
            </button>
          </div>
        );
      }
      
      const textContent = typeof part === 'string' ? part : '';
      // Remove any remaining multiple newlines
      const cleanedText = textContent.replace(/\n{2,}/g, '\n');
      
      return (
        <span key={index} className="leading-none">
          {cleanedText.split('\n').map((line: string, i: number) => (
            <React.Fragment key={i}>
              <span dangerouslySetInnerHTML={{ 
                __html: line.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>') 
              }} />
              {i !== cleanedText.split('\n').length - 1 && <br />}
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
      console.log('Updated chat history:', [...newHistory, { role: 'assistant', content: data.answer }]);
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
                  
                  <div className={`max-w-[85%] mx-1 mb-5 rounded-2xl p-3.5 text-sm shadow-sm ${
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