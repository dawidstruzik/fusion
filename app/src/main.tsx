import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import '@fontsource-variable/libre-franklin/index.css'
import '@fontsource/courier-prime/400.css'
import '@fontsource/courier-prime/700.css'
import './index.css'
import App from './App.tsx'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
