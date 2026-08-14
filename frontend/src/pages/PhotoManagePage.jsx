import React, { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { ArrowLeft, Plus, Edit3, Trash2, Star, X } from "lucide-react";
import apiClient from "../utils/request";
import { API_ENDPOINTS } from "../config";
import { getImageUrl } from "../utils/imageHelper";

const PhotoManagePage = ({ styles, isDark }) => {
  const navigate = useNavigate();
  const [photos, setPhotos] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showModal, setShowModal] = useState(false);
  const [editingPhoto, setEditingPhoto] = useState(null);

  // 表单数据
  const [photoUrl, setPhotoUrl] = useState("");
  const [photoFile, setPhotoFile] = useState(null);
  const [photoFiles, setPhotoFiles] = useState([]); // 批量上传
  const [caption, setCaption] = useState("");
  const [location, setLocation] = useState("");
  const [isFeatured, setIsFeatured] = useState(false);
  const [tags, setTags] = useState([]); // 🆕 Tags
  const [newTagName, setNewTagName] = useState("");
  const [uploading, setUploading] = useState(false);
  const [previewUrl, setPreviewUrl] = useState("");

  useEffect(() => {
    fetchPhotos();
  }, []);

  const fetchPhotos = async () => {
    try {
      const response = await apiClient.get(API_ENDPOINTS.PHOTOS);
      setPhotos(response.data || []);
    } catch (error) {
      console.error("获取照片失败:", error);
    } finally {
      setLoading(false);
    }
  };

  const openEditModal = (photo) => {
    setEditingPhoto(photo);
    setPhotoUrl(photo.url);
    setPhotoFile(null);
    setPhotoFiles([]);
    setPreviewUrl(getImageUrl(photo.url));
    setCaption(photo.caption || "");
    setLocation(photo.location || "");
    setIsFeatured(photo.is_featured);
    setTags(photo.tags ? photo.tags.map(t => t.name) : []); // Load tags
    setShowModal(true);
  };

  const openCreateModal = () => {
    setEditingPhoto(null);
    setPhotoUrl("");
    setPhotoFile(null);
    setPhotoFiles([]);
    setPreviewUrl("");
    setCaption("");
    setLocation("");
    setIsFeatured(false);
    setTags([]); // Reset tags
    setShowModal(true);
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

  const handleFileSelect = (e) => {
    const files = Array.from(e.target.files || []);
    if (files.length === 0) return;

    // 批量上传模式
    if (files.length > 1) {
      const validFiles = files.filter(file => {
        if (!file.type.startsWith('image/')) {
          alert(`${file.name} 不是图片文件`);
          return false;
        }
        if (file.size > 10 * 1024 * 1024) {
          alert(`${file.name} 大小超过10MB`);
          return false;
        }
        return true;
      });

      setPhotoFiles(validFiles);
      setPhotoFile(null);
      setPhotoUrl("");
      // 使用第一张图片作为预览
      if (validFiles.length > 0) {
        const reader = new FileReader();
        reader.onloadend = () => {
          setPreviewUrl(reader.result);
        };
        reader.readAsDataURL(validFiles[0]);
      }
    } else {
      // 单文件上传
      const file = files[0];
      if (!file.type.startsWith('image/')) {
        alert('请选择图片文件');
        return;
      }
      if (file.size > 10 * 1024 * 1024) {
        alert('图片大小不能超过10MB');
        return;
      }
      setPhotoFile(file);
      setPhotoFiles([]);
      setPhotoUrl("");
      const reader = new FileReader();
      reader.onloadend = () => {
        setPreviewUrl(reader.result);
      };
      reader.readAsDataURL(file);
    }
  };

  const handleSave = async (e) => {
    e.preventDefault();

    // 批量上传模式
    if (photoFiles.length > 0) {
      setUploading(true);
      try {
        let successCount = 0;
        for (const file of photoFiles) {
          const formData = new FormData();
          formData.append('file', file);

          const uploadResponse = await apiClient.post(`${API_ENDPOINTS.PHOTOS}/upload`, formData);

          const photoData = {
            url: uploadResponse.data.url,
            caption: null,
            location: null,
            is_featured: false,
            tags: tags,
          };

          await apiClient.post(API_ENDPOINTS.PHOTOS, photoData);
          successCount++;
        }

        setShowModal(false);
        fetchPhotos();
        alert(`成功上传 ${successCount} 张照片！`);
      } catch (error) {
        console.error("批量上传失败:", error);
        alert(error.response?.data?.detail || "批量上传失败,请重试");
      } finally {
        setUploading(false);
      }
      return;
    }

    // 单文件上传模式
    if (!photoFile && !photoUrl) {
      alert('请选择图片文件或输入图片URL');
      return;
    }

    setUploading(true);
    try {
      let finalUrl = photoUrl;

      // 如果选择了本地文件,先上传
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
        tags: tags,
      };

      if (editingPhoto) {
        await apiClient.put(
          API_ENDPOINTS.PHOTO_DETAIL(editingPhoto.id),
          photoData
        );
      } else {
        await apiClient.post(API_ENDPOINTS.PHOTOS, photoData);
      }

      setShowModal(false);
      fetchPhotos();
    } catch (error) {
      console.error("保存照片失败:", error);
      alert(error.response?.data?.detail || "保存失败,请重试");
    } finally {
      setUploading(false);
    }
  };

  const handleDelete = async (id) => {
    if (!confirm("确定要删除这张照片吗?")) return;

    try {
      await apiClient.delete(API_ENDPOINTS.PHOTO_DETAIL(id));
      fetchPhotos();
    } catch (error) {
      console.error("删除照片失败:", error);
      alert("删除失败,请重试");
    }
  };

  const toggleFeatured = async (photo) => {
    try {
      await apiClient.put(API_ENDPOINTS.PHOTO_DETAIL(photo.id), {
        ...photo,
        is_featured: !photo.is_featured,
      });
      fetchPhotos();
    } catch (error) {
      console.error("更新照片失败:", error);
    }
  };

  if (loading) {
    return (
      <div className="pt-32 pb-20 min-h-screen flex items-center justify-center">
        <div className="animate-spin w-12 h-12 border-4 border-gray-300 border-t-blue-500 rounded-full"></div>
      </div>
    );
  }

  return (
    <div className={`pt-32 pb-20 min-h-screen ${styles.bgSecondary} transition-colors duration-1000 animate-fade-in`}>
      <div className="max-w-7xl mx-auto px-6">
        {/* 头部 */}
        <div className="flex items-center justify-between mb-12">
          <div>
            <button
              onClick={() => navigate("/account")}
              className={`flex items-center gap-2 ${styles.textMuted} hover:${styles.text} mb-4 transition-colors`}
            >
              <ArrowLeft size={16} />
              返回账户页面
            </button>
            <h2 className={`text-4xl font-serif ${styles.text}`}>照片管理</h2>
            <p className={`text-sm ${styles.textMuted} mt-2`}>
              管理首页精选照片和相册
            </p>
          </div>

          <button
            onClick={openCreateModal}
            className={`flex items-center gap-2 px-4 py-2 rounded-lg text-white transition-colors ${
              isDark
                ? "bg-orange-600 hover:bg-orange-500"
                : "bg-[#189BCC] hover:bg-[#1589b5]"
            }`}
          >
            <Plus size={16} />
            添加照片
          </button>
        </div>

        {/* 照片表格 */}
        <div
          className={`${styles.bg} rounded-xl border ${styles.border} overflow-hidden`}
        >
          <table className="w-full">
            <thead className={`${isDark ? "bg-gray-800" : "bg-gray-50"}`}>
              <tr>
                <th
                  className={`px-6 py-3 text-left text-xs font-bold ${styles.text} uppercase`}
                >
                  预览
                </th>
                <th
                  className={`px-6 py-3 text-left text-xs font-bold ${styles.text} uppercase`}
                >
                  地点
                </th>
                <th
                  className={`px-6 py-3 text-left text-xs font-bold ${styles.text} uppercase`}
                >
                  注释
                </th>
                <th
                  className={`px-6 py-3 text-left text-xs font-bold ${styles.text} uppercase`}
                >
                  精选展示
                </th>
                <th
                  className={`px-6 py-3 text-left text-xs font-bold ${styles.text} uppercase`}
                >
                  操作
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200 dark:divide-gray-700">
              {photos.map((photo) => (
                <tr
                  key={photo.id}
                  className={`transition-colors ${
                    photo.is_featured
                      ? isDark
                        ? 'bg-orange-500/10 hover:bg-orange-500/20 border-l-4 border-orange-500'
                        : 'bg-[#189BCC]/10 hover:bg-[#189BCC]/20 border-l-4 border-[#189BCC]'
                      : 'hover:bg-gray-50 dark:hover:bg-gray-800'
                  }`}
                >
                  <td className="px-6 py-4">
                    <div className="relative">
                      <img
                        src={getImageUrl(photo.url)}
                        alt={photo.caption}
                        className={`w-32 h-32 object-cover rounded-lg shadow-sm transition-all ${
                          photo.is_featured ? 'ring-2 ring-offset-2' + (isDark ? ' ring-orange-500' : ' ring-[#189BCC]') : ''
                        }`}
                      />
                    </div>
                  </td>
                  <td className={`px-6 py-4 text-sm ${styles.text} ${photo.is_featured ? 'font-medium' : ''}`}>
                    {photo.location || "-"}
                  </td>
                  <td
                    className={`px-6 py-4 text-sm ${styles.text} max-w-xs truncate ${photo.is_featured ? 'font-medium' : ''}`}
                  >
                    {photo.caption || "-"}
                  </td>
                  <td className="px-6 py-4">
                    <button
                      onClick={() => toggleFeatured(photo)}
                      className={`flex items-center gap-2 px-3 py-2 rounded-lg transition-all ${
                        photo.is_featured
                          ? isDark
                            ? "bg-orange-500 text-white hover:bg-orange-600"
                            : "bg-[#189BCC] text-white hover:bg-[#1589b5]"
                          : `${styles.textMuted} hover:${styles.text} ${isDark ? 'hover:bg-gray-700' : 'hover:bg-gray-100'}`
                      }`}
                      title={photo.is_featured ? "取消首页展示" : "设为首页展示"}
                    >
                      <Star
                        size={18}
                        fill={photo.is_featured ? "currentColor" : "none"}
                      />
                      {photo.is_featured && <span className="text-xs font-medium">首页展示</span>}
                    </button>
                  </td>
                  <td className="px-6 py-4">
                    <div className="flex gap-2">
                      <button
                        onClick={() => openEditModal(photo)}
                        className={`p-2 rounded ${styles.textMuted} hover:${styles.text} ${
                          isDark ? 'hover:bg-gray-700' : 'hover:bg-gray-100'
                        } transition-colors`}
                        title="编辑"
                      >
                        <Edit3 size={16} />
                      </button>
                      <button
                        onClick={() => handleDelete(photo.id)}
                        className="p-2 rounded text-red-500 hover:text-red-700 hover:bg-red-50 dark:hover:bg-red-900/20 transition-colors"
                        title="删除"
                      >
                        <Trash2 size={16} />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* 添加/编辑照片模态框 */}
      {showModal && (
        <div className="fixed inset-0 bg-black/50 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div
            className={`${styles.bg} rounded-xl p-8 max-w-2xl w-full max-h-[90vh] overflow-y-auto`}
          >
            <h3 className={`text-xl font-bold ${styles.text} mb-6`}>
              {editingPhoto ? "编辑照片" : "添加照片"}
            </h3>

            <form onSubmit={handleSave} className="space-y-4">
              {/* 照片上传方式选择 */}
              <div>
                <label
                  className={`block text-sm font-medium ${styles.text} mb-3`}
                >
                  照片来源
                </label>
                <div className="grid grid-cols-1 gap-3">
                  {/* 本地上传 */}
                  <div>
                    <label
                      className={`flex items-center justify-center gap-2 px-4 py-8 border-2 border-dashed rounded-lg cursor-pointer transition-all ${
                        photoFile
                          ? isDark
                            ? 'border-orange-500 bg-orange-500/10'
                            : 'border-[#189BCC] bg-[#189BCC]/10'
                          : `${styles.border} hover:${isDark ? 'border-orange-500 bg-orange-500/5' : 'border-[#189BCC] bg-[#189BCC]/5'}`
                      }`}
                    >
                      <Plus size={20} />
                      <span className={`text-sm ${styles.text}`}>
                        {photoFiles.length > 0
                          ? `已选择 ${photoFiles.length} 张照片`
                          : photoFile
                          ? `已选择: ${photoFile.name}`
                          : '从本地选择图片（可多选）'}
                      </span>
                      <input
                        type="file"
                        accept="image/*"
                        multiple
                        onChange={handleFileSelect}
                        className="hidden"
                      />
                    </label>
                  </div>

                  {/* 分隔符 */}
                  <div className="relative">
                    <div className={`absolute inset-0 flex items-center`}>
                      <div className={`w-full border-t ${styles.border}`}></div>
                    </div>
                    <div className="relative flex justify-center text-xs">
                      <span className={`px-2 ${styles.bgSecondary} ${styles.textMuted}`}>
                        或者
                      </span>
                    </div>
                  </div>

                  {/* URL输入 */}
                  <div>
                    {editingPhoto && photoUrl.startsWith('/uploads/') ? (
                      // 编辑本地上传照片时，显示只读信息
                      <div className={`w-full px-4 py-2 border ${styles.border} rounded-lg ${isDark ? 'bg-gray-800' : 'bg-gray-100'} ${styles.textMuted} text-sm`}>
                        <div className="flex items-center gap-2">
                          <span className="text-xs">📁</span>
                          <span>本地上传的照片</span>
                        </div>
                        <div className="text-xs mt-1 opacity-70">{photoUrl}</div>
                      </div>
                    ) : (
                      // 创建新照片或外部URL时，显示可编辑输入框
                      <input
                        type="url"
                        value={photoUrl}
                        onChange={(e) => {
                          setPhotoUrl(e.target.value);
                          setPhotoFile(null);
                          setPhotoFiles([]);
                          setPreviewUrl(e.target.value);
                        }}
                        className={`w-full px-4 py-2 border ${styles.border} rounded-lg ${styles.bgSecondary} ${styles.text} transition-colors focus:ring-2 ${
                          isDark ? 'focus:ring-orange-500' : 'focus:ring-[#189BCC]'
                        }`}
                        placeholder="或输入图片URL: https://example.com/photo.jpg"
                        disabled={!!photoFile || photoFiles.length > 0}
                      />
                    )}
                  </div>
                </div>

                {/* 图片预览 */}
                {previewUrl && (
                  <div className="mt-4">
                    <img
                      src={previewUrl}
                      alt="预览"
                      className="w-full max-h-64 object-contain rounded-lg shadow-md"
                      onError={(e) => {
                        e.target.style.display = "none";
                      }}
                    />
                  </div>
                )}
              </div>

              <div>
                <label
                  className={`block text-sm font-medium ${styles.text} mb-2`}
                >
                  地点 {photoFiles.length > 0 && <span className="text-xs text-gray-500">（将应用于所有照片）</span>}
                </label>
                <input
                  type="text"
                  value={location}
                  onChange={(e) => setLocation(e.target.value)}
                  className={`w-full px-4 py-2 border ${styles.border} rounded-lg ${styles.bgSecondary} ${styles.text} transition-colors focus:ring-2 ${
                    isDark ? 'focus:ring-orange-500' : 'focus:ring-[#189BCC]'
                  }`}
                  placeholder="例: 杭州西湖"
                />
              </div>

              <div>
                <label
                  className={`block text-sm font-medium ${styles.text} mb-2`}
                >
                  注释 {photoFiles.length > 0 && <span className="text-xs text-gray-500">（将应用于所有照片）</span>}
                </label>
                <textarea
                  value={caption}
                  onChange={(e) => setCaption(e.target.value)}
                  className={`w-full px-4 py-2 border ${styles.border} rounded-lg ${styles.bgSecondary} ${styles.text} transition-colors focus:ring-2 ${
                    isDark ? 'focus:ring-orange-500' : 'focus:ring-[#189BCC]'
                  }`}
                  rows="3"
                  placeholder="照片的描述或故事..."
                />
              </div>

              <div className={`flex items-center gap-2 p-4 rounded-lg ${isDark ? 'bg-gray-800' : 'bg-gray-50'}`}>
                <input
                  type="checkbox"
                  id="featured"
                  checked={isFeatured}
                  onChange={(e) => setIsFeatured(e.target.checked)}
                  className={`w-4 h-4 rounded ${isDark ? 'text-orange-500 focus:ring-orange-500' : 'text-[#189BCC] focus:ring-[#189BCC]'}`}
                />
                <label htmlFor="featured" className={`text-sm ${styles.text} flex items-center gap-2`}>
                  <Star size={16} className={isFeatured ? (isDark ? 'text-orange-500' : 'text-[#189BCC]') : styles.textMuted} />
                  <span>在首页展示 {isFeatured && '✓'}</span>
                </label>
              </div>

              <div className="flex gap-3 mt-6">
                <button
                  type="submit"
                  disabled={uploading}
                  className={`flex-1 py-3 text-white rounded-lg font-medium transition-all ${
                    uploading
                      ? 'opacity-50 cursor-not-allowed'
                      : isDark
                        ? "bg-orange-600 hover:bg-orange-500 hover:shadow-lg"
                        : "bg-[#189BCC] hover:bg-[#1589b5] hover:shadow-lg"
                  }`}
                >
                  {uploading
                    ? '保存中...'
                    : photoFiles.length > 0
                    ? `保存 ${photoFiles.length} 张照片`
                    : '保存照片'}
                </button>
                <button
                  type="button"
                  onClick={() => setShowModal(false)}
                  disabled={uploading}
                  className={`flex-1 py-3 border ${styles.border} rounded-lg ${styles.textMuted} hover:${styles.text} transition-colors ${
                    uploading ? 'opacity-50 cursor-not-allowed' : ''
                  }`}
                >
                  取消
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};

export default PhotoManagePage;
