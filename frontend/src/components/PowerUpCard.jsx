import React from 'react';

const PowerUpCard = ({ icon, title, description, timeHint, isActive, onToggle }) => {
  return (
    <div 
      className={`glass-card power-up-card ${isActive ? 'active' : ''}`}
      onClick={onToggle}
      role="switch"
      aria-checked={isActive}
      tabIndex={0}
      onKeyDown={(e) => { 
        if (e.key === 'Enter') onToggle();
        if (e.key === ' ') { e.preventDefault(); onToggle(); }
      }}
    >
      <div className="power-up-icon">{icon}</div>
      <div className="power-up-content">
        <h4 className="power-up-title">{title}</h4>
        <p className="power-up-description">{description}</p>
      </div>
      <div className="power-up-hint">+{timeHint}</div>
    </div>
  );
};

export default PowerUpCard;
