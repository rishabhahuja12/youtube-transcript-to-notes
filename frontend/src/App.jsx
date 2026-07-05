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

class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, errorInfo) {
    console.error('ErrorBoundary caught an error:', error, errorInfo);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div style={{ padding: '2rem', color: 'red' }}>
          <h2>Something went wrong.</h2>
          <pre>{this.state.error.toString()}</pre>
        </div>
      );
    }
    return this.props.children;
  }
}

function App() {
  return (
    <ErrorBoundary>
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
