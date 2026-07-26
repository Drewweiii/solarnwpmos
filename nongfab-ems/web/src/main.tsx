import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
// After index.css on purpose: the print rules override the theme tokens, and
// they can only win at equal specificity if they come later.
import './print.css'
import App from './App.tsx'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
