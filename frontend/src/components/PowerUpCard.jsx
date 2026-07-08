import React from 'react';
import { Check } from 'lucide-react';

const PowerUpCard = ({ icon, title, description, isActive, onToggle }) => {
  return (
    <div 
      className={`power-up-card ${isActive ? 'active' : ''}`}
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
      {isActive && (
        <div className="power-up-checkmark">
          <Check size={16} />
        </div>
      )}
    </div>
  );
};

export default PowerUpCard;
