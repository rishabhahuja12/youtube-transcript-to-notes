import React from 'react';
import PropTypes from 'prop-types';

const ThemeCard = ({ theme, isSelected, onClick }) => {
  return (
    <div 
      className={`theme-card panel-card ${isSelected ? 'selected' : ''}`} 
      onClick={onClick}
    >
      <div className={`theme-preview theme-${theme.id}`}>
        <div className="theme-preview-header"></div>
        <div className="theme-preview-body"></div>
        <div className="theme-preview-footer"></div>
      </div>
      <div className="theme-info">
        <h4 className="theme-name">{theme.name}</h4>
        <p className="theme-desc">{theme.description}</p>
      </div>
      {isSelected && (
        <div className="theme-check">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <polyline points="20 6 9 17 4 12"></polyline>
          </svg>
        </div>
      )}
    </div>
  );
};

ThemeCard.propTypes = {
  theme: PropTypes.shape({
    id: PropTypes.string.isRequired,
    name: PropTypes.string.isRequired,
    description: PropTypes.string.isRequired,
  }).isRequired,
  isSelected: PropTypes.bool.isRequired,
  onClick: PropTypes.func.isRequired,
};

export default ThemeCard;
