import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { App } from './App/App';
import './global.css';

const container = document.getElementById('root');
if (container === null) {
  throw new Error('в index.html нет контейнера #root');
}

createRoot(container).render(
  <StrictMode>
    <App />
  </StrictMode>
);
