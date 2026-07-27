import React, { useState, useEffect } from 'react';
import { listDirectories } from '../utils/api';
import { X, Folder, HardDrive, ArrowUp, Check, RefreshCw } from 'lucide-react';
import './FolderPickerModal.css';

const FolderPickerModal = ({ isOpen, onClose, onSelect, initialPath = '' }) => {
  const [currentPath, setCurrentPath] = useState(initialPath);
  const [parentPath, setParentPath] = useState('');
  const [subdirectories, setSubdirectories] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const fetchFolderContents = async (targetPath) => {
    setLoading(true);
    setError(null);
    try {
      const data = await listDirectories(targetPath);
      setCurrentPath(data.current_path || '');
      setParentPath(data.parent_path || '');
      setSubdirectories(data.subdirectories || []);
    } catch (err) {
      console.error('Failed to list directory contents:', err);
      setError(err.message || 'Failed to read directory');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (isOpen) {
      fetchFolderContents(initialPath);
    }
  }, [isOpen, initialPath]);

  if (!isOpen) return null;

  return (
    <div className="folder-picker-overlay fade-in">
      <div className="folder-picker-modal panel-card">
        <div className="folder-picker-header">
          <div className="header-title-group">
            <Folder className="header-icon" size={20} color="var(--highlighter)" />
            <h3>Select Output Directory</h3>
          </div>
          <button type="button" className="close-btn" onClick={onClose}>
            <X size={18} />
          </button>
        </div>

        <div className="folder-picker-path-bar">
          <button
            type="button"
            className="up-button secondary-button"
            onClick={() => fetchFolderContents(parentPath)}
            disabled={!parentPath || loading}
            title="Go up one folder"
          >
            <ArrowUp size={16} /> Up
          </button>
          <input
            type="text"
            className="text-input current-path-input"
            value={currentPath}
            onChange={(e) => setCurrentPath(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') fetchFolderContents(currentPath);
            }}
            placeholder="Type or paste path..."
          />
          <button
            type="button"
            className="secondary-button refresh-btn"
            onClick={() => fetchFolderContents(currentPath)}
            disabled={loading}
          >
            <RefreshCw size={16} className={loading ? 'loader-spin' : ''} />
          </button>
        </div>

        <div className="folder-picker-body">
          {error && <div className="status-alert error">{error}</div>}
          
          {loading ? (
            <div className="folder-picker-loading">
              <RefreshCw className="loader-spin" size={24} />
              <span>Loading folders...</span>
            </div>
          ) : subdirectories.length === 0 ? (
            <div className="folder-picker-empty">No subdirectories in this folder</div>
          ) : (
            <div className="folder-list">
              {subdirectories.map((dir) => {
                const isDrive = dir.name.startsWith('Local Disk') || dir.name.startsWith('Drive');
                return (
                  <div
                    key={dir.path}
                    className="folder-item"
                    onClick={() => fetchFolderContents(dir.path)}
                    role="button"
                    tabIndex={0}
                  >
                    {isDrive ? (
                      <HardDrive size={18} color="var(--highlighter)" />
                    ) : (
                      <Folder size={18} color="var(--text-secondary)" />
                    )}
                    <span className="folder-name">{dir.name}</span>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        <div className="folder-picker-footer">
          <button type="button" className="secondary-button" onClick={onClose}>
            Cancel
          </button>
          <button
            type="button"
            className="primary-button"
            disabled={!currentPath}
            onClick={() => {
              onSelect(currentPath);
              onClose();
            }}
          >
            <Check size={18} /> Select This Folder
          </button>
        </div>
      </div>
    </div>
  );
};

export default FolderPickerModal;
