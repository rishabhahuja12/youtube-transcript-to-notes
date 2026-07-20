import React, { createContext, useContext, useReducer, useEffect, useCallback, useMemo } from 'react';
import { fetchOllamaStatus } from '../utils/api';

const AppContext = createContext();

const initialState = {
  currentScreen: 'newPipeline',
  activeCourseDir: null,
  activeJobId: null,
  pipelineStatus: 'idle',
  pipelineLogs: [],
  pipelineProgress: { current: 0, total: 100 },
  ollamaStatus: 'loading'
};

function reducer(state, action) {
  switch (action.type) {
    case 'SET_SCREEN': return { ...state, currentScreen: action.payload };
    case 'SET_COURSE_DIR': return { ...state, activeCourseDir: action.payload };
    case 'SET_ACTIVE_JOB_ID': return { ...state, activeJobId: action.payload };
    case 'SET_PIPELINE_STATUS': return { ...state, pipelineStatus: action.payload };
    case 'SET_PIPELINE_LOGS': return { ...state, pipelineLogs: typeof action.payload === 'function' ? action.payload(state.pipelineLogs) : action.payload };
    case 'SET_PIPELINE_PROGRESS': return { ...state, pipelineProgress: action.payload };
    case 'SET_OLLAMA_STATUS': return { ...state, ollamaStatus: action.payload };
    default: return state;
  }
}

export const AppProvider = ({ children }) => {
  const [state, dispatch] = useReducer(reducer, initialState);

  useEffect(() => {
    const checkStatus = async () => {
      try {
        const data = await fetchOllamaStatus();
        dispatch({ type: 'SET_OLLAMA_STATUS', payload: data.ollama === true ? 'online' : 'offline' });
      } catch (error) {
        dispatch({ type: 'SET_OLLAMA_STATUS', payload: 'offline' });
      }
    };
    checkStatus();
    const interval = setInterval(checkStatus, 15000);
    return () => clearInterval(interval);
  }, []);

  const addLog = useCallback((message, type = 'info') => {
    dispatch({ 
      type: 'SET_PIPELINE_LOGS', 
      payload: (prev) => {
        const newLogs = [...prev, { id: crypto.randomUUID ? crypto.randomUUID() : Math.random().toString(36).substring(2), message, type, time: new Date().toLocaleTimeString() }];
        return newLogs.slice(-500);
      }
    });
  }, []);

  const setCurrentScreen = useCallback((val) => dispatch({ type: 'SET_SCREEN', payload: val }), []);
  const setActiveCourseDir = useCallback((val) => dispatch({ type: 'SET_COURSE_DIR', payload: val }), []);
  const setActiveJobId = useCallback((val) => dispatch({ type: 'SET_ACTIVE_JOB_ID', payload: val }), []);
  const setPipelineStatus = useCallback((val) => dispatch({ type: 'SET_PIPELINE_STATUS', payload: val }), []);
  const setPipelineLogs = useCallback((val) => dispatch({ type: 'SET_PIPELINE_LOGS', payload: val }), []);
  const setPipelineProgress = useCallback((val) => dispatch({ type: 'SET_PIPELINE_PROGRESS', payload: val }), []);
  const setOllamaStatus = useCallback((val) => dispatch({ type: 'SET_OLLAMA_STATUS', payload: val }), []);

  const value = useMemo(() => ({
    ...state,
    setCurrentScreen,
    setActiveCourseDir,
    setActiveJobId,
    setPipelineStatus,
    setPipelineLogs,
    setPipelineProgress,
    setOllamaStatus,
    addLog
  }), [state, setCurrentScreen, setActiveCourseDir, setActiveJobId, setPipelineStatus, setPipelineLogs, setPipelineProgress, setOllamaStatus, addLog]);

  return (
    <AppContext.Provider value={value}>
      {children}
    </AppContext.Provider>
  );
};

export const useAppContext = () => useContext(AppContext);
