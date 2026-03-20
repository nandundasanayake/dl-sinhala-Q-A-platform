// src/App.tsx
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Header } from './components/layout/Header';
import { VideoDashboard } from './features/video/pages/VideoDashboard';
import { VideoWatch } from './features/video/pages/VideoWatch';

const queryClient = new QueryClient();

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <div className="min-h-screen bg-gray-50">
          {/* <Header /> */}
          <Routes>
            <Route path="/" element={<Navigate to="/dashboard" replace />} />
            <Route path="/dashboard" element={<VideoDashboard />} />
            <Route path="/watch/:videoId" element={<VideoWatch />} />
          </Routes>
        </div>
      </BrowserRouter>
    </QueryClientProvider>
  );
}

export default App;





// import React, { useState, useRef, useEffect } from 'react';
// import { UploadCloud, Send, Loader2, PlayCircle, MessageSquare, Bot, User } from 'lucide-react';

// export default function App() {
//   const [videoFile, setVideoFile] = useState(null);
//   const [videoUrl, setVideoUrl] = useState(null);
//   const [videoId, setVideoId] = useState(null);
//   const [isUploading, setIsUploading] = useState(false);
//   const [uploadStatus, setUploadStatus] = useState('');
  
//   const [chatHistory, setChatHistory] = useState([]);
//   const [question, setQuestion] = useState('');
//   const [isTyping, setIsTyping] = useState(false);

//   const videoRef = useRef(null);
//   const chatEndRef = useRef(null);

//   useEffect(() => {
//     chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
//   }, [chatHistory]);

//   const handleFileChange = (e) => {
//     const file = e.target.files[0];
//     if (file) {
//       setVideoFile(file);
//       setVideoUrl(URL.createObjectURL(file));
//       setUploadStatus('');
//       setVideoId(null);
//       setChatHistory([]);
//     }
//   };

// const handleUpload = async () => {
//   if (!videoFile) return;

//   setIsUploading(true);
  
//   // STEP 1: Uploading
//   setUploadStatus('⏳ Uploading Video to Server...');

//   const formData = new FormData();
//   formData.append('file', videoFile);

//   try {
//     const response = await fetch('http://localhost:8000/api/upload-video', {
//       method: 'POST',
//       body: formData,
//     });

//     // STEP 2: Processing (This happens while we wait for the response)
//     setUploadStatus('⚙️ Generating Timestamped Transcript via Gemini...');

//     const data = await response.json();

//     if (response.ok) {
//       // STEP 3: Embedding & Indexing
//       setUploadStatus('🧠 Processing AI Embeddings & Indexing in OpenSearch...');
      
//       // Delay for a second to let the user see the embedding status
//       setTimeout(() => {
//         setVideoId(data.video_id);
//         // STEP 4: Done
//         setUploadStatus('✅ Ready for Students!');
//         setChatHistory([{ 
//           role: 'assistant', 
//           content: 'Hello! The video is processed. You can now ask any question!' 
//         }]);
//       }, 1500);

//     } else {
//       setUploadStatus(`❌ Error: ${data.detail}`);
//     }
//   } catch (error) {
//     setUploadStatus(`❌ Network Error: Check Backend Connection.`);
//   } finally {
//     setIsUploading(false);
//   }
// };

//   const handleSendMessage = async (e) => {
//     e.preventDefault();
//     if (!question.trim() || !videoId) return;

//     const currentQuestion = question;
//     setQuestion('');
    
//     setChatHistory(prev => [...prev, { role: 'user', content: currentQuestion }]);
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
//         setChatHistory(prev => [...prev, { role: 'assistant', content: data.answer }]);
//       } else {
//         setChatHistory(prev => [...prev, { role: 'assistant', content: `❌ Error: ${data.detail}` }]);
//       }
//     } catch (error) {
//       setChatHistory(prev => [...prev, { role: 'assistant', content: `❌ Network Error: Could not connect.` }]);
//     } finally {
//       setIsTyping(false);
//     }
//   };

//   // --- NEW: Function to handle video seeking when timestamp is clicked ---
//   const handleSeek = (timeString) => {
//     if (!videoRef.current) return;
    
//     // Convert MM:SS to total seconds
//     const [minutes, seconds] = timeString.split(':').map(Number);
//     const totalSeconds = (minutes * 60) + seconds;
    
//     // Jump the video to that specific time and play
//     videoRef.current.currentTime = totalSeconds;
//     videoRef.current.play();
//   };

//   // --- NEW: Function to parse and render clickable timestamps in chat ---
//   const renderMessageContent = (content) => {
//     // Regex to find the timestamp format sent by our backend
//     const regex = /(⏱️\s*\[▶ Play Video \(\d{2}:\d{2}\s*-\s*\d{2}:\d{2}\)\])/g;
//     const parts = content.split(regex);
    
//     return parts.map((part, index) => {
//       if (part && part.startsWith('⏱️')) {
//         // Extract the start time (e.g., "05:20" from the string)
//         const timeMatch = part.match(/(\d{2}:\d{2})/);
//         const startTime = timeMatch ? timeMatch[0] : "00:00";
        
//         return (
//           <button 
//             key={index}
//             onClick={() => handleSeek(startTime)}
//             className="inline-flex items-center gap-1.5 bg-purple-100 text-purple-700 px-3 py-1.5 rounded-lg text-sm font-bold hover:bg-purple-200 transition-colors mt-2 border border-purple-200 shadow-sm ml-2"
//             title={`Click to play video from ${startTime}`}
//           >
//             <PlayCircle className="w-4 h-4" />
//             Play ({startTime})
//           </button>
//         );
//       }
      
//       // Render normal text with proper line breaks
//       return (
//         <span key={index}>
//           {part?.split('\n').map((line, i) => (
//             <React.Fragment key={i}>
//               <span dangerouslySetInnerHTML={{ __html: line.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>') }} />
//               {i !== part.split('\n').length - 1 && <br />}
//             </React.Fragment>
//           ))}
//         </span>
//       );
//     });
//   };

//   return (
//     <div className="min-h-screen bg-gray-50 font-sans text-gray-800">
      
//       {/* Top Navigation */}
//       <header className="bg-white border-b border-gray-200 px-6 py-4 flex items-center justify-between shadow-sm sticky top-0 z-10">
//         <div className="flex items-center gap-2">
//           <div className="bg-dopamine-dark p-2 rounded-lg">
//             <PlayCircle className="text-white w-5 h-5" />
//           </div>
//           <h1 className="text-xl font-bold text-gray-800">Dopamine AI Player</h1>
//         </div>
//         <div className="flex items-center gap-3">
//           <div className="w-8 h-8 rounded-full bg-dopamine-accent flex items-center justify-center text-white font-bold text-sm">
//             ND
//           </div>
//         </div>
//       </header>

//       <main className="max-w-7xl mx-auto p-4 md:p-6 grid grid-cols-1 lg:grid-cols-3 gap-6">
        
//         {/* LEFT COLUMN: Video Player & Upload */}
//         <div className="lg:col-span-2 flex flex-col gap-4">
          
//           <div className="bg-white rounded-2xl shadow-sm border border-gray-100 overflow-hidden">
//             <div className="bg-dopamine-dark p-4 flex items-center justify-between">
//               <h2 className="text-white font-semibold flex items-center gap-2">
//                 <PlayCircle className="w-5 h-5 text-dopamine-accent" />
//                 Lesson Video
//               </h2>
//               {videoId && <span className="bg-dopamine-accent text-white text-xs px-2 py-1 rounded-md font-medium">Processed & Indexed</span>}
//             </div>
            
//             <div className="aspect-video bg-black flex items-center justify-center relative">
//               {videoUrl ? (
//                 <video 
//                   ref={videoRef}
//                   src={videoUrl} 
//                   controls 
//                   className="w-full h-full object-contain"
//                 />
//               ) : (
//                 <div className="text-gray-400 flex flex-col items-center">
//                   <PlayCircle className="w-16 h-16 mb-2 opacity-50" />
//                   <p>No video selected</p>
//                 </div>
//               )}
//             </div>
//           </div>

//           <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-5">
//             <h3 className="font-semibold text-gray-800 mb-3 flex items-center gap-2">
//               <UploadCloud className="w-5 h-5 text-dopamine-accent" />
//               Upload & Process
//             </h3>
            
//             <div className="flex flex-col md:flex-row gap-3">
//               <input 
//                 type="file" 
//                 accept="video/*" 
//                 onChange={handleFileChange}
//                 className="flex-1 block w-full text-sm text-gray-500 file:mr-4 file:py-2.5 file:px-4 file:rounded-lg file:border-0 file:text-sm file:font-semibold file:bg-dopamine-light file:text-dopamine-accent hover:file:bg-purple-100 cursor-pointer border border-gray-200 rounded-lg p-1"
//               />
//               <button 
//                 onClick={handleUpload}
//                 disabled={!videoFile || isUploading}
//                 className="bg-dopamine-dark text-white px-6 py-2.5 rounded-lg font-medium hover:bg-opacity-90 transition-all disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2 min-w-[140px]"
//               >
//                 {isUploading ? <Loader2 className="w-5 h-5 animate-spin" /> : 'Process Video'}
//               </button>
//             </div>

//             {uploadStatus && (
//               <div className={`mt-4 p-3 rounded-lg text-sm font-medium ${uploadStatus.includes('✅') ? 'bg-green-50 text-green-700 border border-green-200' : uploadStatus.includes('❌') ? 'bg-red-50 text-red-700 border border-red-200' : 'bg-blue-50 text-blue-700 border border-blue-200 flex items-center gap-2'}`}>
//                 {uploadStatus.includes('Uploading') && <Loader2 className="w-4 h-4 animate-spin" />}
//                 {uploadStatus}
//               </div>
//             )}
//           </div>
//         </div>

//         {/* RIGHT COLUMN: Chat Interface */}
//         <div className="bg-white rounded-2xl shadow-sm border border-gray-100 flex flex-col h-[calc(100vh-120px)] lg:h-[800px]">
          
//           <div className="bg-dopamine-dark p-4 rounded-t-2xl flex items-center gap-2">
//             <MessageSquare className="w-5 h-5 text-dopamine-accent" />
//             <h2 className="text-white font-semibold">AI Teaching Assistant</h2>
//           </div>

//           <div className="flex-1 overflow-y-auto p-4 space-y-4 bg-gray-50">
//             {chatHistory.length === 0 ? (
//               <div className="h-full flex flex-col items-center justify-center text-gray-400 gap-3">
//                 <Bot className="w-12 h-12 text-gray-300" />
//                 <p className="text-sm text-center px-4">Upload and process a video to start asking questions.</p>
//               </div>
//             ) : (
//               chatHistory.map((msg, idx) => (
//                 <div key={idx} className={`flex gap-3 ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
//                   {msg.role === 'assistant' && (
//                     <div className="w-8 h-8 rounded-full bg-dopamine-dark flex-shrink-0 flex items-center justify-center mt-1">
//                       <Bot className="w-4 h-4 text-white" />
//                     </div>
//                   )}
                  
//                   <div className={`max-w-[85%] rounded-2xl p-3.5 text-sm shadow-sm ${
//                     msg.role === 'user' 
//                       ? 'bg-dopamine-accent text-white rounded-tr-none' 
//                       : 'bg-white border border-gray-200 text-gray-800 rounded-tl-none leading-relaxed'
//                   }`}>
//                     {/* NEW: Using the custom renderer here */}
//                     {renderMessageContent(msg.content)}
//                   </div>

//                   {msg.role === 'user' && (
//                     <div className="w-8 h-8 rounded-full bg-gray-200 flex-shrink-0 flex items-center justify-center mt-1">
//                       <User className="w-4 h-4 text-gray-500" />
//                     </div>
//                   )}
//                 </div>
//               ))
//             )}
            
//             {isTyping && (
//               <div className="flex gap-3 justify-start">
//                 <div className="w-8 h-8 rounded-full bg-dopamine-dark flex items-center justify-center mt-1">
//                   <Bot className="w-4 h-4 text-white" />
//                 </div>
//                 <div className="bg-white border border-gray-200 rounded-2xl rounded-tl-none p-4 flex gap-1">
//                   <div className="w-2 h-2 bg-gray-300 rounded-full animate-bounce"></div>
//                   <div className="w-2 h-2 bg-gray-300 rounded-full animate-bounce" style={{ animationDelay: '0.2s' }}></div>
//                   <div className="w-2 h-2 bg-gray-300 rounded-full animate-bounce" style={{ animationDelay: '0.4s' }}></div>
//                 </div>
//               </div>
//             )}
//             <div ref={chatEndRef} />
//           </div>

//           <div className="p-4 bg-white border-t border-gray-100 rounded-b-2xl">
//             <form onSubmit={handleSendMessage} className="flex gap-2">
//               <input
//                 type="text"
//                 value={question}
//                 onChange={(e) => setQuestion(e.target.value)}
//                 placeholder={videoId ? "Ask a question about the video..." : "Process a video first..."}
//                 disabled={!videoId || isTyping}
//                 className="flex-1 border border-gray-300 rounded-xl px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-dopamine-accent focus:border-transparent disabled:bg-gray-100 disabled:cursor-not-allowed"
//               />
//               <button
//                 type="submit"
//                 disabled={!question.trim() || !videoId || isTyping}
//                 className="bg-dopamine-accent hover:bg-purple-600 text-white rounded-xl px-5 py-3 transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center"
//               >
//                 <Send className="w-5 h-5" />
//               </button>
//             </form>
//           </div>
          
//         </div>
//       </main>
//     </div>
//   );
// }