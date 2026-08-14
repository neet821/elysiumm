import React, { useState, useEffect } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { ArrowLeft, Save, Upload, Tag, Hash, EyeOff, Pin, X } from "lucide-react";
import apiClient from "../utils/request";
import { API_ENDPOINTS } from "../config";

const PostEditorPage = ({ styles, isDark }) => {
  const { id } = useParams();
  const navigate = useNavigate();
  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");
  const [category, setCategory] = useState("");
  const [categories, setCategories] = useState([]);
  const [showNewCategory, setShowNewCategory] = useState(false);
  const [newCategoryName, setNewCategoryName] = useState("");

  // New Fields
  const [slug, setSlug] = useState("");
  const [pinPriority, setPinPriority] = useState(0);
  const [isHidden, setIsHidden] = useState(false);
  const [tags, setTags] = useState([]); // Selected tag names
  const [availableTags, setAvailableTags] = useState([]); // All tags from backend
  const [newTagName, setNewTagName] = useState("");

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const isEdit = !!id;

  useEffect(() => {
    if (isEdit) {
      fetchPost();
    }
    fetchCategories();
    fetchTags();
  }, [id]);

  const fetchTags = async () => {
    try {
      const res = await apiClient.get("/api/tags");
      setAvailableTags(res.data);
    } catch (error) {
      console.error("Failed to fetch tags", error);
    }
  };

  const fetchCategories = async () => {
    try {
      const response = await apiClient.get(API_ENDPOINTS.POSTS);
      const posts = response.data;
      // 提取所有唯一的分类
      const uniqueCategories = [...new Set(posts.map(post => post.category).filter(Boolean))];
      setCategories(uniqueCategories);
    } catch (error) {
      console.error("获取分类失败:", error);
    }
  };

  const fetchPost = async () => {
    try {
      const response = await apiClient.get(API_ENDPOINTS.POST_DETAIL(id));
      const post = response.data;
      setTitle(post.title);
      setContent(post.content || "");
      setCategory(post.category || "");
      setSlug(post.slug || "");
      setPinPriority(post.pin_priority || 0);
      setIsHidden(post.is_hidden || false);
      setTags(post.tags ? post.tags.map(t => t.name) : []);
    } catch (error) {
      console.error("获取文章失败:", error);
      setError("加载文章失败");
    }
  };

  const handleFileUpload = (e) => {
    const file = e.target.files[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = (e) => {
      setContent(e.target.result);
    };
    reader.readAsText(file);
  };

  const handleAddTag = () => {
      if (newTagName && !tags.includes(newTagName)) {
          setTags([...tags, newTagName]);
          setNewTagName("");
      }
  };

  const handleRemoveTag = (tagToRemove) => {
      setTags(tags.filter(t => t !== tagToRemove));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError("");
    setLoading(true);

    try {
      // 如果选择了新建分类，使用新分类名称
      const finalCategory = showNewCategory ? newCategoryName : category;
      const postData = {
          title,
          content,
          category: finalCategory,
          slug,
          pin_priority: pinPriority,
          is_hidden: isHidden,
          tags
      };

      if (isEdit) {
        const response = await apiClient.put(API_ENDPOINTS.POST_DETAIL(id), postData);
        setSlug(response.data.slug || response.data.id);
      } else {
        const response = await apiClient.post(API_ENDPOINTS.POSTS, postData);
        setSlug(response.data.slug || response.data.id);
        navigate(`/posts/${response.data.slug || response.data.id}`);
        return;
      }

      navigate(`/posts/${slug || id}`);
    } catch (error) {
      console.error("保存文章失败:", error);
      setError(error.response?.data?.detail || "保存失败，请重试");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className={`pt-32 pb-20 min-h-screen ${styles.bgSecondary} transition-colors duration-1000 animate-fade-in`}>
      <div className="max-w-4xl mx-auto px-6">
        <button
          onClick={() => navigate(-1)}
          className={`flex items-center gap-2 ${styles.textMuted} hover:${styles.text} mb-8 transition-colors`}
        >
          <ArrowLeft size={16} />
          返回
        </button>

        <div
          className={`${styles.bg} rounded-xl shadow-sm border ${styles.border} p-8`}
        >
          <h1 className={`text-3xl font-serif font-bold ${styles.text} mb-8`}>
            {isEdit ? "编辑文章" : "新建文章"}
          </h1>

          {error && (
            <div className="mb-6 p-4 bg-red-50 border border-red-200 rounded-lg">
              <p className="text-red-600 text-sm">{error}</p>
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-6">
            <div>
              <label
                className={`block text-sm font-medium ${styles.text} mb-2`}
              >
                文章标题
              </label>
              <input
                type="text"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                className={`w-full px-4 py-3 border ${
                  styles.border
                } rounded-lg ${styles.bgSecondary} ${
                  styles.text
                } focus:outline-none focus:ring-2 ${
                  isDark ? "focus:ring-orange-500" : "focus:ring-[#189BCC]"
                }`}
                placeholder="输入文章标题"
                required
              />
            </div>

            <div>
              <label
                className={`block text-sm font-medium ${styles.text} mb-2`}
              >
                分类
              </label>
              {!showNewCategory ? (
                <div className="space-y-2">
                  <select
                    value={category}
                    onChange={(e) => {
                      if (e.target.value === '__new__') {
                        setShowNewCategory(true);
                        setCategory('');
                      } else {
                        setCategory(e.target.value);
                      }
                    }}
                    className={`w-full px-4 py-3 border ${
                      styles.border
                    } rounded-lg ${styles.bgSecondary} ${
                      styles.text
                    } focus:outline-none focus:ring-2 ${
                      isDark ? "focus:ring-orange-500" : "focus:ring-[#189BCC]"
                    }`}
                  >
                    <option value="">选择分类（可选）</option>
                    {categories.map((cat) => (
                      <option key={cat} value={cat}>
                        {cat}
                      </option>
                    ))}
                    <option value="__new__">➕ 新建分类...</option>
                  </select>
                </div>
              ) : (
                <div className="space-y-2">
                  <input
                    type="text"
                    value={newCategoryName}
                    onChange={(e) => setNewCategoryName(e.target.value)}
                    className={`w-full px-4 py-3 border ${
                      styles.border
                    } rounded-lg ${styles.bgSecondary} ${
                      styles.text
                    } focus:outline-none focus:ring-2 ${
                      isDark ? "focus:ring-orange-500" : "focus:ring-[#189BCC]"
                    }`}
                    placeholder="输入新分类名称"
                    autoFocus
                  />
                  <button
                    type="button"
                    onClick={() => {
                      setShowNewCategory(false);
                      setNewCategoryName('');
                    }}
                    className={`text-sm ${styles.textMuted} hover:${styles.text}`}
                  >
                    ← 返回选择现有分类
                  </button>
                </div>
              )}
            </div>

            {/* Slug, Pin, Hidden */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <div>
                    <label className={`block text-sm font-medium ${styles.text} mb-2`}>网址短标识</label>
                    <input
                        type="text"
                        value={slug}
                        onChange={(e) => setSlug(e.target.value)}
                        className={`w-full px-4 py-3 border ${styles.border} rounded-lg ${styles.bgSecondary} ${styles.text} focus:outline-none focus:ring-2 ${isDark ? "focus:ring-orange-500" : "focus:ring-[#189BCC]"}`}
                        placeholder="留空时根据标题自动生成（custom-url-slug）"
                    />
                </div>
                <div>
                    <label className={`block text-sm font-medium ${styles.text} mb-2`}>置顶优先级 (0-3)</label>
                    <select
                        value={pinPriority}
                        onChange={(e) => setPinPriority(Number(e.target.value))}
                        className={`w-full px-4 py-3 border ${styles.border} rounded-lg ${styles.bgSecondary} ${styles.text} focus:outline-none focus:ring-2 ${isDark ? "focus:ring-orange-500" : "focus:ring-[#189BCC]"}`}
                    >
                        <option value={0}>无 (0)</option>
                        <option value={1}>低 (1)</option>
                        <option value={2}>中 (2)</option>
                        <option value={3}>高 (3)</option>
                    </select>
                </div>
                <div className="flex items-center pt-8">
                    <label className="flex items-center gap-2 cursor-pointer">
                        <input
                            type="checkbox"
                            checked={isHidden}
                            onChange={(e) => setIsHidden(e.target.checked)}
                            className="w-5 h-5 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                        />
                        <span className={`${styles.text}`}>隐藏文章</span>
                    </label>
                </div>
            </div>

            {/* Tags */}
            <div>
                <label className={`block text-sm font-medium ${styles.text} mb-2`}>标签</label>
                <div className="flex flex-wrap gap-2 mb-2">
                    {tags.map(tag => (
                        <span key={tag} className={`px-2 py-1 rounded-full text-sm flex items-center gap-1 ${isDark ? 'bg-blue-900 text-blue-200' : 'bg-blue-100 text-blue-800'}`}>
                            {tag}
                            <button type="button" onClick={() => handleRemoveTag(tag)} className="hover:text-red-500"><X size={14} /></button>
                        </span>
                    ))}
                </div>
                <div className="flex gap-2">
                    <input
                        type="text"
                        value={newTagName}
                        onChange={(e) => setNewTagName(e.target.value)}
                        onKeyDown={(e) => e.key === 'Enter' && (e.preventDefault(), handleAddTag())}
                        placeholder="添加标签..."
                        className={`flex-1 px-4 py-2 border ${styles.border} rounded-lg ${styles.bgSecondary} ${styles.text} focus:outline-none focus:ring-2 ${isDark ? "focus:ring-orange-500" : "focus:ring-[#189BCC]"}`}
                        list="available-tags"
                    />
                    <datalist id="available-tags">
                        {availableTags.map(t => <option key={t.id} value={t.name} />)}
                    </datalist>
                    <button type="button" onClick={handleAddTag} className={`px-4 py-2 rounded-lg ${isDark ? 'bg-gray-700 hover:bg-gray-600' : 'bg-gray-200 hover:bg-gray-300'} ${styles.text}`}>
                        添加
                    </button>
                </div>
            </div>

            <div>
              <div className="flex justify-between items-center mb-2">
                  <label className={`block text-sm font-medium ${styles.text}`}>
                    文章内容 (Markdown)
                  </label>
                  <label className={`cursor-pointer flex items-center gap-1 text-sm ${isDark ? 'text-blue-400 hover:text-blue-300' : 'text-blue-600 hover:text-blue-500'}`}>
                      <Upload size={14} />
                      <span>导入 .md/.txt</span>
                      <input type="file" accept=".md,.txt" onChange={handleFileUpload} className="hidden" />
                  </label>
              </div>
              <textarea
                value={content}
                onChange={(e) => setContent(e.target.value)}
                rows={20}
                className={`w-full px-4 py-3 border ${
                  styles.border
                } rounded-lg ${styles.bgSecondary} ${
                  styles.text
                } focus:outline-none focus:ring-2 ${
                  isDark ? "focus:ring-orange-500" : "focus:ring-[#189BCC]"
                } resize-y`}
                placeholder="开始写作..."
                required
              />
            </div>

            <div className="flex gap-4">
              <button
                type="submit"
                disabled={loading}
                className={`flex items-center gap-2 px-6 py-3 rounded-lg text-white transition-colors ${
                  loading ? "opacity-50 cursor-not-allowed" : ""
                } ${
                  isDark
                    ? "bg-orange-600 hover:bg-orange-500"
                    : "bg-[#189BCC] hover:bg-[#1589b5]"
                }`}
              >
                <Save size={16} />
                {loading ? "保存中..." : "保存文章"}
              </button>
              <button
                type="button"
                onClick={() => navigate(-1)}
                className={`px-6 py-3 rounded-lg border ${styles.border} ${styles.textMuted} hover:${styles.text} transition-colors`}
              >
                取消
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>
  );
};

export default PostEditorPage;
