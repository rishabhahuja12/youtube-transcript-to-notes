import React from 'react';
import PropTypes from 'prop-types';

const HealthCard = ({ title, status, icon, desc }) => (
  <div className="health-card">
    <div className={`health-icon-wrapper ${status ? 'success' : 'error'}`}>
      {icon}
    </div>
    <div>
      <h3 className="health-card-title">
        {title}
        <span className={`status-indicator ${status ? 'online' : 'error'}`}></span>
      </h3>
      <p className="health-card-desc">{desc}</p>
      <p className={`health-status ${status ? 'success' : 'error'}`}>
        {status ? 'Online & Ready' : 'Unavailable'}
      </p>
    </div>
  </div>
);

HealthCard.propTypes = {
  title: PropTypes.string.isRequired,
  status: PropTypes.bool.isRequired,
  icon: PropTypes.node.isRequired,
  desc: PropTypes.string.isRequired,
};

export default HealthCard;
