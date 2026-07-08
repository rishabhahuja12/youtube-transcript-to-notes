import React from 'react';
import { Play, Eye, Share2, FileText } from 'lucide-react';

const CourseCard = ({ course, isRecent, onClick }) => {
  const { title, path, date, badges = {}, duration = "42:10" } = course;
  
  return (
    <div 
      className={`panel-card course-card ${isRecent ? 'recent-card' : ''}`} 
      onClick={onClick} 
      role="button" 
      tabIndex={0} 
      onKeyDown={(e) => { 
        if (e.key === 'Enter') onClick();
        if (e.key === ' ') { e.preventDefault(); onClick(); }
      }}
    >
      <div className="course-thumbnail">
        <div className="play-icon-wrapper">
          <Play size={20} fill="currentColor" />
        </div>
        <div className="duration-badge mono-text">{duration}</div>
      </div>
      
      <div className="course-card-content">
        <h3 className="course-title">{title || 'Untitled Course'}</h3>
        
        <div className="course-status-icons">
          <Eye size={14} className={badges?.vision ? 'active-icon' : 'inactive-icon'} />
          <Share2 size={14} className={badges?.kag ? 'active-icon' : 'inactive-icon'} />
          <FileText size={14} className={badges?.pdf ? 'active-icon' : 'inactive-icon'} />
        </div>

        <div className="course-footer mono-text">
          {isRecent ? 'continue · just now' : `processed ${date || 'recently'}`}
        </div>
      </div>
    </div>
  );
};

export default CourseCard;
