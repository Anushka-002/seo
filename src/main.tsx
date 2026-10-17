import '@fontsource-variable/inter'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import App from './App'
import './index.css'
import { applyTheme, getInitialTheme } from './lib/theme'

applyTheme(getInitialTheme(), false) // match the saved/OS theme; do not persist an unchosen default

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
