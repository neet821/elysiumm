import React from "react";
import { X, ArrowRight, Calendar, User, Tag } from "lucide-react";
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { useNavigate } from "react-router-dom";

const PostPreviewModal = ({ post, isOpen, onClose, isDark }) => {
  const navigate = useNavigate();

  if (!isOpen || !post) return null;

  const styles = isDark
    ? {
        bg: "bg-[#1a1a1a]",
        text: "text-gray-200",
        textMuted: "text-gray-400",
        border: "border-gray-700",
        secondary: "bg-[#2a2a2a]",
      }
    : {
        bg: "bg-white",
        text: "text-gray-800",
        textMuted: "text-gray-500",
        border: "border-gray-200",
        secondary: "bg-gray-50",
      };

  const handleReadMore = () => {
      onClose();
      navigate(`/posts/${post.slug || post.id}`);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm animate-fade-in" onClick={onClose}>
      <div
        className={`${styles.bg} ${styles.text} w-full max-w-3xl rounded-xl shadow-2xl overflow-hidden flex flex-col max-h-[85vh] animate-scale-in relative`}
        onClick={(e) => e.stopPropagation()}
      >
        <button
          onClick={onClose}
          className={`absolute top-4 right-4 p-2 rounded-full hover:bg-gray-200 dark:hover:bg-gray-700 transition-colors z-10`}
        >
          <X className="w-5 h-5" />
        </button>

        <div className="p-8 overflow-y-auto custom-scrollbar">
            <div className="mb-6">
                <div className="flex items-center gap-3 text-sm opacity-70 mb-3">
                    <span className="flex items-center gap-1"><Calendar size={14}/> {new Date(post.created_at).toLocaleDateString()}</span>
                    <span className="flex items-center gap-1"><User size={14}/> {post.author?.username || '未知作者'}</span>
                    {post.category && <span className={`px-2 py-0.5 rounded text-xs border ${styles.border}`}>{post.category}</span>}
                </div>
                <h2 className="text-3xl font-serif font-bold mb-4">{post.title}</h2>
            </div>

            <div className={`prose prose-lg max-w-none ${isDark ? "prose-invert" : ""} mb-8 opacity-90`}>
                 {/* Show only first 500 chars or so, or just render it and let it scroll */}
                 {/* Requirement says "包含大部分文章信息... 预览要可滑动" */}
                 <ReactMarkdown remarkPlugins={[remarkGfm]}>
                    {post.content}
                 </ReactMarkdown>
            </div>

            {post.tags && post.tags.length > 0 && (
                <div className="flex flex-wrap gap-2 mb-8">
                    {post.tags.map(tag => (
                        <span key={tag.id} className={`text-xs px-2 py-1 rounded-full ${styles.secondary}`}>#{tag.name}</span>
                    ))}
                </div>
            )}
        </div>

        <div className={`p-4 border-t ${styles.border} flex justify-end ${styles.secondary}`}>
            <button
                onClick={handleReadMore}
                className="flex items-center gap-2 px-6 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-full transition-colors font-medium"
            >
                阅读全文 / Read Full Article <ArrowRight size={16} />
            </button>
        </div>
      </div>
    </div>
  );
};

export default PostPreviewModal;
