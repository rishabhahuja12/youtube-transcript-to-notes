import React, { createContext, useContext, useState, useEffect } from 'react';

const AppContext = createContext();

export const AppProvider = ({ children }) => {
  const [activeTab, setActiveTab] = useState('process');
  const [ollamaStatus, setOllamaStatus] = useState('loading'); // online, offline, loading
  const [progress, setProgress] = useState(0);
  const [currentStep, setCurrentStep] = useState('Idle');
  const [logs, setLogs] = useState([]);
  
  // Mock status check
  useEffect(() => {
    setTimeout(() => {
      setOllamaStatus('online');
    }, 2000);
  }, []);

  const addLog = (message, type = 'info') => {
    setLogs(prev => [...prev, { id: Date.now(), message, type, time: new Date().toLocaleTimeString() }]);
  };

  const value = {
    activeTab,
    setActiveTab,
    ollamaStatus,
    setOllamaStatus,
    progress,
    setProgress,
    currentStep,
    setCurrentStep,
    logs,
    addLog
  };

  return (
    <AppContext.Provider value={value}>
      {children}
    </AppContext.Provider>
  );
};

export const useAppContext = () => useContext(AppContext);
