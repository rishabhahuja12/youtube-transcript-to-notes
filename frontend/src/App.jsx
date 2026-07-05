import React from 'react';
import Sidebar from './components/Sidebar';
import FooterDock from './components/FooterDock';
import { AppProvider, useAppContext } from './context/AppContext';

const MainContent = () => {
  const { activeTab } = useAppContext();
  
  return (
    <main className="main-content">
      <div className="content-area">
        {/* Placeholder for content based on activeTab */}
        <div className="glass-card placeholder-view">
          <h2 className="placeholder-title">
            {activeTab.charAt(0).toUpperCase() + activeTab.slice(1)} View
          </h2>
          <p className="placeholder-text">
            This area will contain the main functionality for the {activeTab} section. Select a different tab in the sidebar to navigate.
          </p>
        </div>
      </div>
      <FooterDock />
    </main>
  );
};

function App() {
  return (
    <AppProvider>
      <div className="app-container">
        <Sidebar />
        <MainContent />
      </div>
    </AppProvider>
  );
}

export default App;
