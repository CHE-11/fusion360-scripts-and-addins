import React from 'react';
import ReactDOM from 'react-dom/client';

import App from './components/App';
import './globals.css';

const rootEl = document.getElementById('root');
if (!rootEl) throw new Error('Missing #root element');

const root = ReactDOM.createRoot(rootEl);
root.render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
