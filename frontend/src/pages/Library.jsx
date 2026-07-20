import React, { useEffect, useState, useMemo } from 'react';
import CourseCard from '../components/CourseCard';
import { fetchLibrary } from '../utils/api';
import { useAppContext } from '../context/AppContext';
import { RefreshCw, BookOpen, Plus, Search, Filter } from 'lucide-react';

const Library = () => {
  const [courses, setCourses] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [sortBy, setSortBy] = useState('date');
  const { setCurrentScreen, setActiveCourseDir, activeJobId, pipelineStatus } = useAppContext();

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

  useEffect(() => {
    loadLibrary();
  }, [activeJobId, pipelineStatus]);

  const handleCourseClick = (course) => {
    setActiveCourseDir({ ...course });
    setCurrentScreen('courseWorkspace');
  };

  const goToNewPipeline = () => {
    setCurrentScreen('newPipeline');
  };

  const filteredAndSortedCourses = useMemo(() => {
    let result = courses.filter(course => 
      course.title?.toLowerCase().includes(searchQuery.toLowerCase())
    );
    
    if (sortBy === 'date') {
      result.sort((a, b) => new Date(b.date || 0) - new Date(a.date || 0));
    } else if (sortBy === 'status') {
      result.sort((a, b) => (a.status || '').localeCompare(b.status || ''));
    }
    
    return result;
  }, [courses, searchQuery, sortBy]);

  if (loading && courses.length === 0) {
    return (
      <div className="library-page fade-in">
        <div className="empty-state panel-card">
          <RefreshCw className="empty-state-icon loader-spin" size={48} />
          <h3 className="serif-heading">Loading Library...</h3>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="library-page fade-in">
        <div className="empty-state panel-card">
          <div className="error-text">
            <h3 className="serif-heading">Error loading library</h3>
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
      <div className="library-header">
        <div className="library-title-group">
          <h2 className="serif-heading">Library</h2>
          <span className="course-count mono-text">{courses.length} courses</span>
        </div>
        <div className="search-field library-controls">
          <div className="search-input-wrapper">
            <Search size={16} className="search-icon" />
            <input 
              type="text" 
              placeholder="Search courses..." 
              className="text-input search-input"
              value={searchQuery}
              onChange={e => setSearchQuery(e.target.value)}
            />
          </div>
          <select 
            className="text-input sort-select" 
            value={sortBy} 
            onChange={e => setSortBy(e.target.value)}
          >
            <option value="date">Sort by Date</option>
            <option value="status">Sort by Status</option>
          </select>
        </div>
      </div>
      
      {courses.length === 0 ? (
        <div className="empty-state panel-card">
          <BookOpen className="empty-state-icon" size={64} />
          <h3 className="serif-heading">No courses found</h3>
          <p>You haven't processed any courses yet. Start a new pipeline to build your library.</p>
          <button className="primary-button" onClick={goToNewPipeline}>
            Start your first course
          </button>
        </div>
      ) : (
        <div className="course-grid">
          {filteredAndSortedCourses.map((course, index) => (
            <div key={course.id || index} className="course-card-wrapper">
               <CourseCard 
                 course={course} 
                 isRecent={index === 0 && sortBy === 'date' && searchQuery === ''}
                 onClick={() => handleCourseClick(course)} 
               />
               <span className={`status-badge-overlay ${course.status}`}>
                  {course.status || 'complete'}
               </span>
            </div>
          ))}
          <div 
            className="panel-card course-card new-course-tile" 
            onClick={goToNewPipeline}
            role="button"
            tabIndex={0}
            onKeyDown={(e) => {
              if (e.key === 'Enter') goToNewPipeline();
              if (e.key === ' ') { e.preventDefault(); goToNewPipeline(); }
            }}
          >
            <div className="new-course-content">
              <Plus size={24} />
              <span>start a new course</span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default Library;
