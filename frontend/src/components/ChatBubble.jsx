import React from 'react';
import PropTypes from 'prop-types';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import rehypeHighlight from 'rehype-highlight';

const ChatBubble = ({ message, isUser }) => {
  return (
    <div className={`chat-bubble-container ${isUser ? 'user-message' : 'ai-message'}`}>
      {!isUser && (
        <div className="chat-avatar">
          <div className="avatar-circle ai-avatar">AI</div>
        </div>
      )}
      <div className={`chat-bubble ${isUser ? 'user-bubble' : 'ai-bubble'}`}>
        {isUser ? (
          <div className="chat-text">{message}</div>
        ) : (
          <div className="chat-markdown">
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              rehypePlugins={[rehypeHighlight]}
              components={{
                p: ({node, ...props}) => <p className="mb-2 last:mb-0" {...props} />,
                code: ({node, inline, className, children, ...props}) => {
                  const match = /language-(\w+)/.exec(className || '');
                  return !inline ? (
                    <div className="code-block-wrapper">
                      <code className={className} {...props}>
                        {children}
                      </code>
                    </div>
                  ) : (
                    <code className="inline-code" {...props}>
                      {children}
                    </code>
                  )
                }
              }}
            >
              {message}
            </ReactMarkdown>
          </div>
        )}
      </div>
      {isUser && (
        <div className="chat-avatar">
          <div className="avatar-circle user-avatar">U</div>
        </div>
      )}
    </div>
  );
};

ChatBubble.propTypes = {
  message: PropTypes.string.isRequired,
  isUser: PropTypes.bool.isRequired,
};

export default ChatBubble;
