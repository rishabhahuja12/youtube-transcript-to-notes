import React from 'react';
import { BookOpen, Calendar, Folder, Video, Layers, Camera, Share2, FileText } from 'lucide-react';

const CourseCard = ({ course, onClick }) => {
  const { title, path, date, type = 'youtube', badges = {} } = course;
  
  return (
    <div 
      className="glass-card course-card" 
      onClick={onClick} 
      role="button" 
      tabIndex={0} 
      onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') onClick(); }}
    >
      <div className="course-card-icon">
        {type === 'youtube' ? <Video size={24} /> : <Folder size={24} />}
      </div>
      <div className="course-card-content">
        <h3 className="course-title">{title || 'Untitled Course'}</h3>
        <p className="course-path" title={path}>{path}</p>
        
        <div className="course-meta">
          <span className="course-meta-item">
            <Calendar size={14} /> {date || 'Recent'}
          </span>
          <div className="course-badges" style={{ display: 'flex', gap: '8px', marginLeft: 'auto' }}>
            {badges?.vision && <Camera size={14} title="Vision" />}
            {badges?.kag && <Share2 size={14} title="Knowledge Graph" />}
            {badges?.pdf && <FileText size={14} title="PDF Notes" />}
          </div>
        </div>
      </div>
    </div>
  );
};

export default CourseCard;
