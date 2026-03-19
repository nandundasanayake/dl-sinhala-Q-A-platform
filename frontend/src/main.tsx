// src/main.tsx
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App'

// Find the root element
const rootElement = document.getElementById('root');

// Ensure the root element exists
if (!rootElement) {
  throw new Error('Failed to find the root element. Make sure there is a <div id="root"></div> in your index.html');
}

// Create the root and render the app
createRoot(rootElement).render(
  <StrictMode>
    <App />
  </StrictMode>,
)