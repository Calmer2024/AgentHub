import React from 'react'
import ReactDOM from 'react-dom/client'
import { AppRoot } from './app/AppRoot.tsx'
import './index.css'

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <AppRoot />
  </React.StrictMode>,
)
