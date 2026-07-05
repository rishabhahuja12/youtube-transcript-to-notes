import React, { createContext, useContext, useReducer, useEffect } from 'react';
import { fetchOllamaStatus } from '../utils/api';

const AppContext = createContext();

const initialState = {
  currentScreen: 'newPipeline',
  activeCourseDir: null,
  pipelineStatus: 'idle',
  pipelineLogs: [],
  pipelineProgress: { current: 0, total: 100 },
  ollamaStatus: 'loading'
};

function reducer(state, action) {
  switch (action.type) {
    case 'SET_SCREEN': return { ...state, currentScreen: action.payload };
    case 'SET_COURSE_DIR': return { ...state, activeCourseDir: action.payload };
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
  }, []);

  const addLog = (message, type = 'info') => {
    dispatch({ 
      type: 'SET_PIPELINE_LOGS', 
      payload: (prev) => [...prev, { id: Date.now(), message, type, time: new Date().toLocaleTimeString() }] 
    });
  };

  const value = {
    ...state,
    setCurrentScreen: (val) => dispatch({ type: 'SET_SCREEN', payload: val }),
    setActiveCourseDir: (val) => dispatch({ type: 'SET_COURSE_DIR', payload: val }),
    setPipelineStatus: (val) => dispatch({ type: 'SET_PIPELINE_STATUS', payload: val }),
    setPipelineLogs: (val) => dispatch({ type: 'SET_PIPELINE_LOGS', payload: val }),
    setPipelineProgress: (val) => dispatch({ type: 'SET_PIPELINE_PROGRESS', payload: val }),
    setOllamaStatus: (val) => dispatch({ type: 'SET_OLLAMA_STATUS', payload: val }),
    addLog
  };

  return (
    <AppContext.Provider value={value}>
      {children}
    </AppContext.Provider>
  );
};

export const useAppContext = () => useContext(AppContext);
