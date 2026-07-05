import React from 'react';
import Sidebar from './components/Sidebar';
import FooterDock from './components/FooterDock';
import { AppProvider, useAppContext } from './context/AppContext';

const MainContent = () => {
  const { currentScreen, pipelineStatus, pipelineLogs } = useAppContext();
  
  const showFooter = pipelineStatus === 'running' || pipelineLogs.length > 0;

  return (
    <main className="main-content">
      <div className="content-area">
        <div className="glass-card placeholder-view">
          <h2 className="placeholder-title">
            {currentScreen.charAt(0).toUpperCase() + currentScreen.slice(1).replace(/([A-Z])/g, ' $1')} View
          </h2>
          <p className="placeholder-text">
            This area will contain the main functionality for the {currentScreen} section. Select a different tab in the sidebar to navigate.
          </p>
        </div>
      </div>
      {showFooter && <FooterDock />}
    </main>
  );
};

import { ErrorBoundary } from 'react-error-boundary';

function Fallback({ error }) {
  return (
    <div className="error-fallback">
      <h2>Something went wrong.</h2>
      <pre>{error.message}</pre>
    </div>
  );
}

function App() {
  return (
    <ErrorBoundary FallbackComponent={Fallback}>
      <AppProvider>
        <div className="app-container">
          <Sidebar />
          <MainContent />
        </div>
      </AppProvider>
    </ErrorBoundary>
  );
}

export default App;
