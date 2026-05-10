import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'

// Preload the heavy 3D scene chunk in parallel with React bootstrap.
// Fires during module evaluation — earlier than any useEffect path — so
// it usually finishes before the Loader dismisses. App.tsx's lazy import
// retries on render if this best-effort kick misses; Vite dedupes both
// against the same chunk.
import('./components/scene/Scene').catch(() => {})

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
