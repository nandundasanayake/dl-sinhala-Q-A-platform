// src/features/video/pages/VideoWatch.tsx
import React, { useState, useRef, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { ArrowLeft, Bot, User, Send, PlayCircle } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { VideoPlayer } from '../components/VideoPlayer';
import { useVideoStore } from '@/store/video.store';

interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
}

export const VideoWatch: React.FC = () => {
  const { videoId } = useParams<{ videoId: string }>();
  const navigate = useNavigate();
  const { getVideoById } = useVideoStore();
  
  const [chatHistory, setChatHistory] = useState<ChatMessage[]>([]);
  const [question, setQuestion] = useState('');
  const [isTyping, setIsTyping] = useState(false);
  const [currentVideoTime, setCurrentVideoTime] = useState(0);
  
  const chatEndRef = useRef<HTMLDivElement>(null);
  const video = getVideoById(videoId || '');

  useEffect(() => {
    // Load chat history from localStorage
    const saved = localStorage.getItem(`chat_${videoId}`);
    if (saved) {
      try {
        const parsed = JSON.parse(saved);
        // Validate the data matches ChatMessage type
        const validHistory: ChatMessage[] = parsed.filter(
          (msg: any) => msg.role === 'user' || msg.role === 'assistant'
        );
        setChatHistory(validHistory);
      } catch (error) {
        console.error('Failed to parse chat history:', error);
      }
    }
  }, [videoId]);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [chatHistory]);

  const handleSeek = (timeString: string) => {
    const [minutes, seconds] = timeString.split(':').map(Number);
    const totalSeconds = (minutes * 60) + seconds;
    setCurrentVideoTime(totalSeconds);
  };

  const renderMessageContent = (content: string) => {
    const regex = /(⏱️\s*\[Video Reference:\s*\d{2}:\d{2}\s*-\s*\d{2}:\d{2}\])/;
    const parts = content.split(regex);
    
    return parts.map((part, index) => {
      if (part && part.startsWith('⏱️')) {
        const timeMatch = part.match(/(\d{2}:\d{2})/);
        const startTime = timeMatch ? timeMatch[0] : "00:00";
        
        return (
          <button 
            key={index}
            onClick={() => handleSeek(startTime)}
            className="inline-flex items-center gap-1.5 bg-dopamine-light text-dopamine-accent px-3 py-1.5 rounded-lg text-sm font-bold hover:bg-purple-200 transition-colors mt-2 border border-purple-200 shadow-sm"
          >
            <PlayCircle className="w-4 h-4" />
            Play at {startTime}
          </button>
        );
      }
      
      return (
        <span key={index}>
          {part?.split('\n').map((line, i) => (
            <React.Fragment key={i}>
              {line}
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
    
    // FIX: Use 'as const' to ensure literal type
    const userMessage: ChatMessage = { 
      role: 'user' as const, 
      content: currentQuestion 
    };
    
    const newHistory = [...chatHistory, userMessage];
    setChatHistory(newHistory);
    setIsTyping(true);

    try {
      const response = await fetch('http://localhost:8000/api/chat', {
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
        // FIX: Use 'as const' to ensure literal type
        const assistantMessage: ChatMessage = { 
          role: 'assistant' as const, 
          content: data.answer 
        };
        const updatedHistory = [...newHistory, assistantMessage];
        setChatHistory(updatedHistory);
        localStorage.setItem(`chat_${videoId}`, JSON.stringify(updatedHistory));
      } else {
        const errorMessage: ChatMessage = { 
          role: 'assistant' as const, 
          content: `❌ Error: ${data.detail}` 
        };
        setChatHistory([...newHistory, errorMessage]);
      }
    } catch (error) {
      const errorMessage: ChatMessage = { 
        role: 'assistant' as const, 
        content: `❌ Network Error: Could not connect.` 
      };
      setChatHistory([...newHistory, errorMessage]);
    } finally {
      setIsTyping(false);
    }
  };

  if (!video) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="text-center">
          <h2 className="text-xl font-semibold text-gray-900 mb-2">Video not found</h2>
          <Button onClick={() => navigate('/dashboard')} variant="outline">
            Back to Dashboard
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <div className="bg-white border-b border-gray-200 sticky top-0 z-10">
        <div className="max-w-7xl mx-auto px-4 py-3 flex items-center gap-4">
          <Button
            variant="ghost"
            size="icon"
            onClick={() => navigate('/dashboard')}
            className="hover:bg-gray-100"
          >
            <ArrowLeft className="w-5 h-5" />
          </Button>
          <h1 className="text-lg font-semibold text-gray-900">{video.title}</h1>
        </div>
      </div>

      <main className="max-w-7xl mx-auto p-4 md:p-6 grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left Column: Video Player */}
        <div className="lg:col-span-2 space-y-4">
          <VideoPlayer
            src={video.s3Url || ''}
            title={video.title}
            onSeek={(time) => setCurrentVideoTime(time)}
            className="aspect-video"
          />
        </div>

        {/* Right Column: Chat */}
        <div className="bg-white rounded-2xl shadow-sm border border-gray-100 flex flex-col h-[600px]">
          <div className="bg-dopamine-dark p-4 rounded-t-2xl flex items-center gap-2">
            <Bot className="w-5 h-5 text-dopamine-accent" />
            <h2 className="text-white font-semibold">AI Teaching Assistant</h2>
          </div>

          <div className="flex-1 overflow-y-auto p-4 space-y-4 bg-gray-50">
            {chatHistory.length === 0 ? (
              <div className="h-full flex flex-col items-center justify-center text-gray-400 gap-3">
                <Bot className="w-12 h-12 text-gray-300" />
                <p className="text-sm text-center px-4">
                  Ask questions about this video and get answers with timestamps!
                </p>
              </div>
            ) : (
              chatHistory.map((msg, idx) => (
                <div key={idx} className={`flex gap-3 ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                  {msg.role === 'assistant' && (
                    <div className="w-8 h-8 rounded-full bg-dopamine-dark flex-shrink-0 flex items-center justify-center mt-1">
                      <Bot className="w-4 h-4 text-white" />
                    </div>
                  )}
                  
                  <div className={`max-w-[85%] rounded-2xl p-3.5 text-sm shadow-sm ${
                    msg.role === 'user' 
                      ? 'bg-dopamine-accent text-white rounded-tr-none' 
                      : 'bg-white border border-gray-200 text-gray-800 rounded-tl-none'
                  }`}>
                    {renderMessageContent(msg.content)}
                  </div>

                  {msg.role === 'user' && (
                    <div className="w-8 h-8 rounded-full bg-gray-200 flex-shrink-0 flex items-center justify-center mt-1">
                      <User className="w-4 h-4 text-gray-500" />
                    </div>
                  )}
                </div>
              ))
            )}
            
            {isTyping && (
              <div className="flex gap-3 justify-start">
                <div className="w-8 h-8 rounded-full bg-dopamine-dark flex items-center justify-center mt-1">
                  <Bot className="w-4 h-4 text-white" />
                </div>
                <div className="bg-white border border-gray-200 rounded-2xl rounded-tl-none p-4 flex gap-1">
                  <div className="w-2 h-2 bg-gray-300 rounded-full animate-bounce"></div>
                  <div className="w-2 h-2 bg-gray-300 rounded-full animate-bounce" style={{ animationDelay: '0.2s' }}></div>
                  <div className="w-2 h-2 bg-gray-300 rounded-full animate-bounce" style={{ animationDelay: '0.4s' }}></div>
                </div>
              </div>
            )}
            <div ref={chatEndRef} />
          </div>

          <div className="p-4 bg-white border-t border-gray-100 rounded-b-2xl">
            <form onSubmit={handleSendMessage} className="flex gap-2">
              <input
                type="text"
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                placeholder="Ask a question about the video..."
                className="flex-1 border border-gray-300 rounded-xl px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-dopamine-accent focus:border-transparent"
              />
              <button
                type="submit"
                disabled={!question.trim() || isTyping}
                className="bg-dopamine-accent hover:bg-purple-600 text-white rounded-xl px-5 py-3 transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center"
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