import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowUpRight, BookOpen, ImageIcon, PenTool, Upload, X, MapPin, Calendar, Search } from 'lucide-react';
import apiClient from '../utils/request';
import { API_ENDPOINTS } from '../config';
import { useAuth } from '../contexts/AuthContext';
import { getImageUrl } from '../utils/imageHelper';

const PostsPage = ({ styles, isDark }) => {
  const navigate = useNavigate();
  const { isAdmin } = useAuth();
  const [viewMode, setViewMode] = useState('list');
  const [posts, setPosts] = useState([]);
  const [photos, setPhotos] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [searchQuery, setSearchQuery] = useState("");

  // 上传照片相关状态
  const [showUploadModal, setShowUploadModal] = useState(false);
  const [photoUrl, setPhotoUrl] = useState("");
  const [photoFile, setPhotoFile] = useState(null);
  const [caption, setCaption] = useState("");
  const [location, setLocation] = useState("");
  const [isFeatured, setIsFeatured] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [previewUrl, setPreviewUrl] = useState("");
  const [selectedPhoto, setSelectedPhoto] = useState(null);

  useEffect(() => {
    const fetchData = async () => {
      try {
        setError(null);

        // 并行请求博客和照片数据
        const [postsResponse, photosResponse] = await Promise.allSettled([
          apiClient.get(API_ENDPOINTS.POSTS),
          apiClient.get(API_ENDPOINTS.PHOTOS),
        ]);

        // 处理文章数据
        if (postsResponse.status === 'fulfilled') {
          const sortedPosts = (postsResponse.value.data || []).sort(
            (a, b) => new Date(b.created_at) - new Date(a.created_at)
          );
          setPosts(sortedPosts);
        } else {
          console.error('获取文章失败:', postsResponse.reason);
        }

        // 处理照片数据
        if (photosResponse.status === 'fulfilled') {
          setPhotos(photosResponse.value.data || []);
        } else {
          console.error('获取照片失败:', photosResponse.reason);
        }

        // 如果两个请求都失败,显示错误
        if (
          postsResponse.status === 'rejected' &&
          photosResponse.status === 'rejected'
        ) {
          setError('无法连接到服务器');
        }
      } catch (error) {
        console.error('获取数据失败:', error);
        setError('加载数据时出错');
      } finally {
        setLoading(false);
      }
    };

    fetchData();
  }, []);

  // 上传照片相关函数
  const openUploadModal = () => {
    setPhotoUrl("");
    setPhotoFile(null);
    setPreviewUrl("");
    setCaption("");
    setLocation("");
    setIsFeatured(false);
    setShowUploadModal(true);
  };

  const handleFileSelect = (e) => {
    const file = e.target.files?.[0];
    if (file) {
      if (!file.type.startsWith('image/')) {
        alert('请选择图片文件');
        return;
      }
      if (file.size > 10 * 1024 * 1024) {
        alert('图片大小不能超过10MB');
        return;
      }
      setPhotoFile(file);
      setPhotoUrl("");
      const reader = new FileReader();
      reader.onloadend = () => {
        setPreviewUrl(reader.result);
      };
      reader.readAsDataURL(file);
    }
  };

  const handleUploadPhoto = async (e) => {
    e.preventDefault();

    if (!photoFile && !photoUrl) {
      alert('请选择图片文件或输入图片URL');
      return;
    }

    setUploading(true);
    try {
      let finalUrl = photoUrl;

      if (photoFile) {
        const formData = new FormData();
        formData.append('file', photoFile);

        const uploadResponse = await apiClient.post(`${API_ENDPOINTS.PHOTOS}/upload`, formData);
        finalUrl = uploadResponse.data.url;
      }

      const photoData = {
        url: finalUrl,
        caption: caption || null,
        location: location || null,
        is_featured: isFeatured,
      };

      await apiClient.post(API_ENDPOINTS.PHOTOS, photoData);
      setShowUploadModal(false);

      // 重新获取照片列表
      const response = await apiClient.get(API_ENDPOINTS.PHOTOS);
      setPhotos(response.data || []);

      alert('照片上传成功！');
    } catch (error) {
      console.error("上传照片失败:", error);
      alert(error.response?.data?.detail || "上传失败,请重试");
    } finally {
      setUploading(false);
    }
  };

  if (loading) {
    return (
      <div className={`pt-32 pb-20 min-h-screen ${styles.bgSecondary} flex items-center justify-center`}>
        <div className="text-center">
          <div className={`animate-spin w-12 h-12 border-4 ${isDark ? 'border-gray-800 border-t-orange-500' : 'border-gray-200 border-t-[#189BCC]'} rounded-full mx-auto mb-4`}></div>
          <p className={styles.textMuted}>正在载入归档…</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className={`pt-32 pb-20 min-h-screen ${styles.bgSecondary} flex items-center justify-center`}>
        <div className="text-center">
          <div className={`text-2xl mb-4 ${styles.textMuted}`}>⚠️</div>
          <p className={styles.text}>{error}</p>
          <button
            onClick={() => window.location.reload()}
            className={`mt-4 px-6 py-2 rounded-lg text-white ${isDark ? 'bg-orange-600 hover:bg-orange-500' : 'bg-gray-900 hover:bg-[#189BCC]'} transition-colors`}
          >
            重试
          </button>
        </div>
      </div>
    );
  }

  const filteredPosts = posts.filter(post =>
    post.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
    (post.content && post.content.toLowerCase().includes(searchQuery.toLowerCase()))
  );

  return (
    <div className={`pt-32 pb-20 min-h-screen ${styles.bgSecondary} transition-colors duration-1000 animate-fade-in`}>
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        {/* 头部区域 */}
        <div className={`flex flex-col md:flex-row items-start md:items-end justify-between mb-12 border-b ${styles.border} pb-6 gap-4`}>
          <div>
            <h2 className={`text-3xl font-serif ${styles.text}`}>归档</h2>
            <p className={`text-sm ${styles.textMuted} mt-2 font-light`}>
              All writings and visual memories.
            </p>
          </div>

          <div className="flex items-center gap-4">
            {/* 搜索框 */}
            {viewMode === 'list' && (
              <div className={`relative hidden sm:block`}>
                <input
                  type="text"
                  placeholder="搜索文章..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className={`pl-9 pr-4 py-1.5 text-sm rounded-lg border outline-none transition-all w-48 focus:w-64 ${
                    isDark
                      ? 'bg-gray-800 border-gray-700 text-white placeholder-gray-500 focus:border-orange-500'
                      : 'bg-white border-gray-200 text-gray-900 placeholder-gray-400 focus:border-[#189BCC]'
                  }`}
                />
                <Search
                  size={14}
                  className={`absolute left-3 top-1/2 -translate-y-1/2 ${isDark ? 'text-gray-500' : 'text-gray-400'}`}
                />
              </div>
            )}

            <div className={`flex gap-2 p-1 rounded-lg ${isDark ? 'bg-gray-800' : 'bg-gray-100'}`}>
              <button
                onClick={() => setViewMode('list')}
                className={`px-4 py-1.5 text-xs font-medium rounded-md transition-all
                  ${viewMode === 'list'
                    ? `${isDark ? 'bg-gray-700 text-orange-500' : 'bg-white text-[#189BCC] shadow-sm'}`
                    : `${styles.textMuted} hover:${styles.text}`}`}
              >
                Writings
              </button>
              <button
                onClick={() => setViewMode('photos')}
                className={`px-4 py-1.5 text-xs font-medium rounded-md transition-all
                  ${viewMode === 'photos'
                    ? `${isDark ? 'bg-gray-700 text-orange-500' : 'bg-white text-[#189BCC] shadow-sm'}`
                    : `${styles.textMuted} hover:${styles.text}`}`}
              >
                Photos
              </button>
            </div>

            {/* 管理按钮 - 仅管理员可见 */}
            {isAdmin && viewMode === 'list' && (
              <button
                onClick={() => navigate('/posts/new')}
                className={`flex items-center gap-2 px-4 py-2 rounded-lg text-white transition-colors text-xs sm:text-sm ${
                  isDark
                    ? "bg-orange-600 hover:bg-orange-500"
                    : "bg-[#189BCC] hover:bg-[#1589b5]"
                }`}
                title="编写文章"
              >
                <PenTool size={14} />
                <span className="hidden sm:inline">编写</span>
              </button>
            )}

            {isAdmin && viewMode === 'photos' && (
              <button
                onClick={openUploadModal}
                className={`flex items-center gap-2 px-4 py-2 rounded-lg text-white transition-colors text-xs sm:text-sm ${
                  isDark
                    ? "bg-orange-600 hover:bg-orange-500"
                    : "bg-[#189BCC] hover:bg-[#1589b5]"
                }`}
                title="上传照片"
              >
                <Upload size={14} />
                <span className="hidden sm:inline">上传</span>
              </button>
            )}
          </div>
        </div>

        {/* 内容区域 */}
        <div className="animate-fade-in">
          {viewMode === 'list' ? (
            // 博客列表视图
            <div className="space-y-8 max-w-4xl mx-auto">
              {filteredPosts.length === 0 ? (
                <div className="text-center py-12">
                  <BookOpen size={48} className={`${styles.textMuted} mx-auto mb-4 opacity-30`} />
                  <p className={styles.textMuted}>没有找到文章。</p>
                </div>
              ) : (
                filteredPosts.map((post) => (
                  <div
                    key={post.id}
                    className="group cursor-pointer"
                    onClick={() => navigate(`/posts/${post.id}`)}
                  >
                    <div className="flex flex-col md:flex-row md:items-baseline gap-2 md:gap-8">
                      <span className={`text-xs font-mono ${styles.textMuted} w-24 shrink-0`}>
                        {new Date(post.created_at).toLocaleDateString('zh-CN')}
                      </span>
                      <div className="flex-1">
                        <h3 className={`text-xl font-serif font-medium ${styles.text} group-hover:${styles.accentClass} transition-colors flex items-center gap-2`}>
                          {post.title}
                          <ArrowUpRight
                            size={14}
                            className={`opacity-0 -translate-x-2 group-hover:opacity-100 group-hover:translate-x-0 transition-all ${styles.accentClass}`}
                          />
                        </h3>
                        <p className={`${styles.textMuted} text-sm mt-2 line-clamp-2 leading-relaxed max-w-2xl`}>
                          {post.content?.substring(0, 200) || '暂无内容...'}
                        </p>
                      </div>
                    </div>
                  </div>
                ))
              )}
            </div>
          ) : (
            // 照片瀑布流视图 - 使用PhotosPage的样式
            <div>
              {photos.length === 0 ? (
                <div className={`text-center py-20 ${styles.textMuted}`}>
                  <ImageIcon size={48} className={`${styles.textMuted} mx-auto mb-4 opacity-30`} />
                  <p className={styles.textMuted}>暂无照片</p>
                </div>
              ) : (
                <div className="columns-1 sm:columns-2 lg:columns-3 xl:columns-4 gap-4">
                  {photos.map((photo, idx) => (
                    <div
                      key={photo.id}
                      className="break-inside-avoid mb-4 group cursor-pointer animate-fade-in-up"
                      style={{ animationDelay: `${idx * 30}ms` }}
                      onClick={() => setSelectedPhoto(photo)}
                    >
                      <div
                        className={`${styles.bg} rounded-lg overflow-hidden shadow-sm
                        hover:shadow-xl transition-all duration-300 hover:-translate-y-1`}
                      >
                        <div className="relative overflow-hidden bg-gray-200 dark:bg-gray-800">
                          <img
                            src={getImageUrl(photo.url)}
                            alt={photo.caption || "照片"}
                            className="w-full h-auto object-cover transition-transform duration-700 group-hover:scale-110"
                            loading="lazy"
                            onError={(e) => {
                              console.error('图片加载失败:', photo.url);
                              e.target.src = 'data:image/svg+xml,%3Csvg xmlns="http://www.w3.org/2000/svg" width="400" height="300"%3E%3Crect fill="%23ddd" width="400" height="300"/%3E%3Ctext fill="%23999" x="50%25" y="50%25" text-anchor="middle" dy=".3em"%3E图片加载失败%3C/text%3E%3C/svg%3E';
                            }}
                          />
                          {photo.is_featured && (
                            <div
                              className={`absolute top-2 right-2 px-2 py-1 rounded text-xs font-bold ${
                                isDark ? "bg-orange-500" : "bg-[#189BCC]"
                              } text-white`}
                            >
                              精选
                            </div>
                          )}
                        </div>

                        {(photo.caption || photo.location || photo.created_at) && (
                          <div className="p-4">
                            {photo.caption && (
                              <p
                                className={`text-sm ${styles.text} mb-2 leading-relaxed`}
                              >
                                {photo.caption}
                              </p>
                            )}
                            <div
                              className={`flex items-center gap-3 text-xs ${styles.textMuted} flex-wrap`}
                            >
                              {photo.created_at && (
                                <div className="flex items-center gap-1">
                                  <Calendar size={12} />
                                  <span>
                                    {new Date(photo.created_at).toLocaleDateString(
                                      "zh-CN"
                                    )}
                                  </span>
                                </div>
                              )}
                              {photo.location && (
                                <div className="flex items-center gap-1">
                                  <MapPin size={12} />
                                  <span>{photo.location}</span>
                                </div>
                              )}
                            </div>
                          </div>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {/* 上传照片模态框 */}
      {showUploadModal && (
        <div className="fixed inset-0 bg-black/50 backdrop-blur-sm z-50 flex items-center justify-center p-4" onClick={() => setShowUploadModal(false)}>
          <div className={`${styles.bg} rounded-xl p-6 max-w-lg w-full max-h-[90vh] overflow-y-auto`} onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between mb-6">
              <h3 className={`text-xl font-bold ${styles.text}`}>上传照片</h3>
              <button
                onClick={() => setShowUploadModal(false)}
                className={`p-2 rounded-lg ${isDark ? 'hover:bg-gray-700' : 'hover:bg-gray-100'} transition-colors`}
              >
                <X size={20} />
              </button>
            </div>

            <form onSubmit={handleUploadPhoto} className="space-y-4">
              {/* 图片预览 */}
              {previewUrl && (
                <div className="mb-4">
                  <img src={previewUrl} alt="预览" className="w-full h-48 object-cover rounded-lg" />
                </div>
              )}

              {/* 上传方式选择 */}
              <div className="flex gap-4 mb-4">
                <label className={`flex-1 cursor-pointer`}>
                  <div className={`p-4 border-2 border-dashed rounded-lg text-center transition-colors ${
                    isDark
                      ? 'border-gray-600 hover:border-orange-500'
                      : 'border-gray-300 hover:border-[#189BCC]'
                  }`}>
                    <Upload size={32} className={`mx-auto mb-2 ${styles.textMuted}`} />
                    <p className={`text-sm ${styles.text}`}>选择文件</p>
                    <p className={`text-xs ${styles.textMuted} mt-1`}>最大10MB</p>
                  </div>
                  <input
                    type="file"
                    accept="image/*"
                    onChange={handleFileSelect}
                    className="hidden"
                  />
                </label>
              </div>

              {/* 或者输入URL */}
              <div>
                <label className={`block text-sm ${styles.text} mb-2`}>或输入图片URL</label>
                <input
                  type="url"
                  value={photoUrl}
                  onChange={(e) => {
                    setPhotoUrl(e.target.value);
                    setPhotoFile(null);
                    setPreviewUrl(e.target.value);
                  }}
                  placeholder="https://example.com/image.jpg"
                  className={`w-full px-4 py-2 border ${styles.border} rounded ${styles.bgSecondary} ${styles.text} focus:outline-none focus:ring-2 ${
                    isDark ? 'focus:ring-orange-500' : 'focus:ring-[#189BCC]'
                  }`}
                />
              </div>

              {/* 标题 */}
              <div>
                <label className={`block text-sm ${styles.text} mb-2`}>标题（可选）</label>
                <input
                  type="text"
                  value={caption}
                  onChange={(e) => setCaption(e.target.value)}
                  placeholder="照片标题或描述"
                  className={`w-full px-4 py-2 border ${styles.border} rounded ${styles.bgSecondary} ${styles.text} focus:outline-none focus:ring-2 ${
                    isDark ? 'focus:ring-orange-500' : 'focus:ring-[#189BCC]'
                  }`}
                />
              </div>

              {/* 地点 */}
              <div>
                <label className={`block text-sm ${styles.text} mb-2`}>拍摄地点（可选）</label>
                <input
                  type="text"
                  value={location}
                  onChange={(e) => setLocation(e.target.value)}
                  placeholder="地点"
                  className={`w-full px-4 py-2 border ${styles.border} rounded ${styles.bgSecondary} ${styles.text} focus:outline-none focus:ring-2 ${
                    isDark ? 'focus:ring-orange-500' : 'focus:ring-[#189BCC]'
                  }`}
                />
              </div>

              {/* 精选 */}
              <div className="flex items-center gap-2">
                <input
                  type="checkbox"
                  id="featured"
                  checked={isFeatured}
                  onChange={(e) => setIsFeatured(e.target.checked)}
                  className="w-4 h-4"
                />
                <label htmlFor="featured" className={`text-sm ${styles.text}`}>
                  设为精选照片（在首页展示）
                </label>
              </div>

              {/* 按钮 */}
              <div className="flex gap-3 pt-4">
                <button
                  type="submit"
                  disabled={uploading}
                  className={`flex-1 py-2 text-white rounded transition-colors ${
                    uploading
                      ? 'bg-gray-400 cursor-not-allowed'
                      : isDark
                      ? 'bg-orange-600 hover:bg-orange-500'
                      : 'bg-[#189BCC] hover:bg-[#1589b5]'
                  }`}
                >
                  {uploading ? '上传中...' : '上传照片'}
                </button>
                <button
                  type="button"
                  onClick={() => setShowUploadModal(false)}
                  className={`flex-1 py-2 border ${styles.border} rounded ${styles.text} hover:${styles.bgSecondary} transition-colors`}
                >
                  取消
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* 照片详情模态框 */}
      {selectedPhoto && (
        <div
          className="fixed inset-0 bg-black/90 z-50 flex items-center justify-center p-4"
          onClick={() => setSelectedPhoto(null)}
        >
          <div
            className="relative max-w-6xl max-h-[90vh] w-full"
            onClick={(e) => e.stopPropagation()}
          >
            <button
              onClick={() => setSelectedPhoto(null)}
              className="absolute -top-12 right-0 text-white hover:text-gray-300 transition-colors"
            >
              <svg
                className="w-8 h-8"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M6 18L18 6M6 6l12 12"
                />
              </svg>
            </button>

            <img
              src={getImageUrl(selectedPhoto.url)}
              alt={selectedPhoto.caption || "照片"}
              className="max-w-full max-h-[80vh] mx-auto rounded-lg"
              onError={(e) => {
                console.error('图片加载失败:', selectedPhoto.url);
                e.target.src = 'data:image/svg+xml,%3Csvg xmlns="http://www.w3.org/2000/svg" width="800" height="600"%3E%3Crect fill="%23333" width="800" height="600"/%3E%3Ctext fill="%23999" x="50%25" y="50%25" text-anchor="middle" dy=".3em"%3E图片加载失败%3C/text%3E%3C/svg%3E';
              }}
            />

            {(selectedPhoto.caption || selectedPhoto.location) && (
              <div className="mt-4 text-center text-white">
                {selectedPhoto.location && (
                  <div className="flex items-center justify-center gap-2 text-sm mb-2">
                    <MapPin size={14} />
                    <span>{selectedPhoto.location}</span>
                  </div>
                )}
                {selectedPhoto.caption && (
                  <p className="text-base">{selectedPhoto.caption}</p>
                )}
              </div>
            )}
          </div>
        </div>
      )}

      {/* 动画样式 */}
      <style>{`
        @keyframes fade-in { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }
        .animate-fade-in { animation: fade-in 0.5s ease-out forwards; }
        .animate-fade-in-up { animation: fade-in 0.6s ease-out forwards; }
      `}</style>
    </div>
  );
};

export default PostsPage;
