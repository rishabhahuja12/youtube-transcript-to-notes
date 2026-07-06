import React, { useEffect, useState } from 'react';
import CourseCard from '../components/CourseCard';
import { fetchLibrary } from '../utils/api';
import { useAppContext } from '../context/AppContext';
import { RefreshCw, BookOpen } from 'lucide-react';

const Library = () => {
  const [courses, setCourses] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const { setCurrentScreen, setActiveCourseDir } = useAppContext();

  useEffect(() => {
    const loadLibrary = async () => {
      try {
        setLoading(true);
        const data = await fetchLibrary();
        setCourses(data || []);
      } catch (err) {
        setError(err.message || 'Failed to load library');
      } finally {
        setLoading(false);
      }
    };
    loadLibrary();
  }, []);

  const handleCourseClick = (path) => {
    setActiveCourseDir(path);
    // In Stage 5 this will switch to Course Workspace
  };

  const goToNewPipeline = () => {
    setCurrentScreen('newPipeline');
  };

  if (loading) {
    return (
      <div className="library-page fade-in">
        <div className="empty-state glass-card">
          <RefreshCw className="empty-state-icon" size={48} style={{ animation: 'spin 2s linear infinite' }} />
          <h3>Loading Library...</h3>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="library-page fade-in">
        <div className="empty-state glass-card">
          <div style={{ color: 'var(--error)' }}>
            <h3>Error loading library</h3>
            <p>{error}</p>
          </div>
          <button className="primary-button" onClick={() => window.location.reload()}>
            Retry
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="library-page fade-in">
      <div className="page-header">
        <h2>Your Library</h2>
        <button className="primary-button" onClick={goToNewPipeline}>
          + New Course
        </button>
      </div>
      
      {courses.length === 0 ? (
        <div className="empty-state glass-card">
          <BookOpen className="empty-state-icon" size={64} />
          <h3>No courses found</h3>
          <p>You haven't processed any courses yet. Start a new pipeline to build your library.</p>
          <button className="primary-button" onClick={goToNewPipeline}>
            Start a new pipeline
          </button>
        </div>
      ) : (
        <div className="course-grid">
          {courses.map((course, index) => (
            <CourseCard 
              key={index} 
              course={course} 
              onClick={() => handleCourseClick(course.path)} 
            />
          ))}
        </div>
      )}
    </div>
  );
};

export default Library;
