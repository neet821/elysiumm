import React, { useState, useEffect } from "react";
import { useParams, useNavigate } from "react-router-dom";
import {
  ArrowLeft,
  Edit3,
  Trash2,
  Eye,
  Calendar,
  User as UserIcon,
} from "lucide-react";
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import apiClient from "../utils/request";
import { API_ENDPOINTS } from "../config";
import { useAuth } from "../contexts/AuthContext";

const PostDetailPage = ({ styles, isDark }) => {
  const { id } = useParams();
  const navigate = useNavigate();
  const { user, isAdmin } = useAuth();
  const [post, setPost] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchPost();
  }, [id]);

  const fetchPost = async () => {
    try {
      const response = await apiClient.get(API_ENDPOINTS.POST_DETAIL(id));
      setPost(response.data);
    } catch (error) {
      console.error("获取文章详情失败:", error);
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = async () => {
    if (!window.confirm("确定要删除这篇文章吗？")) return;

    try {
      await apiClient.delete(API_ENDPOINTS.POST_DETAIL(post.id));
      navigate("/posts");
    } catch (error) {
      console.error("删除文章失败:", error);
      alert("删除失败，请重试");
    }
  };

  const canEdit = user && (user.id === post?.author_id || isAdmin);

  if (loading) {
    return (
      <div className="pt-32 pb-20 min-h-screen flex items-center justify-center">
        <div className="animate-spin w-12 h-12 border-4 border-gray-300 border-t-blue-500 rounded-full"></div>
      </div>
    );
  }

  if (!post) {
    return (
      <div className={`pt-32 pb-20 min-h-screen ${styles.bgSecondary} transition-colors duration-1000 animate-fade-in`}>
        <div className="max-w-3xl mx-auto px-6 text-center">
          <p className={`text-xl ${styles.textMuted}`}>文章不存在</p>
          <button
            onClick={() => navigate("/posts")}
            className={`mt-6 ${styles.accentClass} hover:underline`}
          >
            返回文章列表
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className={`pt-32 pb-20 min-h-screen ${styles.bg} transition-colors duration-1000 animate-fade-in`}>
      <div className="max-w-3xl mx-auto px-6">
        <button
          onClick={() => navigate("/posts")}
          className={`flex items-center gap-2 ${styles.textMuted} hover:${styles.text} mb-8 transition-colors`}
        >
          <ArrowLeft size={16} />
          返回列表
        </button>

        <article
          className={`${styles.bg} rounded-xl shadow-sm border ${styles.border} p-8 md:p-12`}
        >
          {/* 文章元信息 */}
          <div className="mb-8">
            <h1
              className={`text-3xl md:text-4xl font-serif font-bold ${styles.text} mb-4 leading-tight`}
            >
              {post.title}
            </h1>

            <div
              className={`flex flex-wrap items-center gap-4 text-sm ${styles.textMuted} pb-6 border-b ${styles.border}`}
            >
              <span className="flex items-center gap-1">
                <UserIcon size={14} />
                {post.author?.username || "匿名"}
              </span>
              <span className="flex items-center gap-1">
                <Calendar size={14} />
                {new Date(post.created_at).toLocaleDateString("zh-CN", {
                  year: "numeric",
                  month: "long",
                  day: "numeric",
                })}
              </span>
              <span className="flex items-center gap-1">
                <Eye size={14} />
                {post.views || 0} 次浏览
              </span>
              {post.category && (
                <span
                  className={`px-2 py-1 rounded text-xs ${
                    isDark
                      ? "bg-gray-800 text-gray-300"
                      : "bg-gray-100 text-gray-600"
                  }`}
                >
                  {post.category}
                </span>
              )}
            </div>
          </div>

          {/* 文章内容 */}
          <div
            className={`prose prose-lg max-w-none ${
              isDark ? "prose-invert" : ""
            } ${styles.text}`}
          >
            <ReactMarkdown remarkPlugins={[remarkGfm]}>
              {post.content}
            </ReactMarkdown>
          </div>

          {/* Tags */}
          {post.tags && post.tags.length > 0 && (
              <div className="mt-8 pt-6 border-t border-dashed border-gray-200 dark:border-gray-700 flex flex-wrap gap-2">
                  {post.tags.map(tag => (
                      <span key={tag.id} className={`px-3 py-1 rounded-full text-sm ${isDark ? 'bg-gray-800 text-gray-300' : 'bg-gray-100 text-gray-600'}`}>
                          #{tag.name}
                      </span>
                  ))}
              </div>
          )}

          {/* 操作按钮 */}
          {canEdit && (
            <div className="mt-12 pt-8 border-t border-gray-200 dark:border-gray-800 flex gap-4">
              <button
                onClick={() => navigate(`/posts/${post.id}/edit`)}
                className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm transition-colors ${
                  isDark
                    ? "bg-orange-600 hover:bg-orange-500"
                    : "bg-[#189BCC] hover:bg-[#1589b5]"
                } text-white`}
              >
                <Edit3 size={16} />
                编辑文章
              </button>
              <button
                onClick={handleDelete}
                className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm border ${styles.border} ${styles.textMuted} hover:text-red-500 hover:border-red-500 transition-colors`}
              >
                <Trash2 size={16} />
                删除文章
              </button>
            </div>
          )}
        </article>
      </div>
    </div>
  );
};

export default PostDetailPage;
