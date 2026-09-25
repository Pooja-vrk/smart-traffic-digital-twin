import React from 'react';

/**
 * Reusable card shell.
 * Props:
 *   title       – card header title text
 *   titleIcon   – Lucide icon element to display before title
 *   badge       – JSX rendered right-side of header (status badge, link, etc.)
 *   noPadding   – suppress body padding (when you handle it yourself)
 *   className   – extra class names on the root element
 *   style       – inline styles on root element
 *   children    – card body content
 */
const Card = ({
  title,
  titleIcon,
  badge,
  noPadding = false,
  className = '',
  style,
  children,
}) => {
  return (
    <div className={`card ${className}`} style={style}>
      {(title || badge) && (
        <div className="card-header">
          <div className="card-title">
            {titleIcon && <span className="card-title-icon">{titleIcon}</span>}
            {title}
          </div>
          {badge && <div>{badge}</div>}
        </div>
      )}
      {noPadding ? children : <div className="card-body">{children}</div>}
    </div>
  );
};

export default Card;
