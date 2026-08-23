import React, { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { ArrowLeft, MapPin, Calendar, Edit3, Trash2, Plus, Upload } from "lucide-react";
import apiClient from "../utils/request";
import { API_ENDPOINTS } from "../config";
import { useAuth } from "../contexts/AuthContext";
import { getImageUrl } from "../utils/imageHelper";

const PhotosPage = ({ styles, isDark }) => {
  const navigate = useNavigate();
  const { isAdmin } = useAuth();
  const [photos, setPhotos] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedPhoto, setSelectedPhoto] = useState(null);

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
              onClick={() => navigate("/posts")}
              className={`flex items-center gap-2 ${styles.textMuted} hover:${styles.text} mb-4 transition-colors`}
            >
              <ArrowLeft size={16} />
              返回文章列表
            </button>
            <h2 className={`text-4xl font-serif ${styles.text}`}>
              Photo Gallery
            </h2>
            <p className={`text-sm ${styles.textMuted} mt-2`}>
              按时间顺序排列的影像记录
            </p>
          </div>

          {isAdmin && (
            <button
              onClick={() => navigate("/account/admin/content/photos")}
              className={`flex items-center gap-2 px-4 py-2 rounded-lg text-white transition-colors ${
                isDark
                  ? "bg-orange-600 hover:bg-orange-500"
                  : "bg-[#189BCC] hover:bg-[#1589b5]"
              }`}
            >
              <Upload size={16} />
              上传照片
            </button>
          )}
        </div>

        {/* 照片网格 */}
        {photos.length === 0 ? (
          <div className={`text-center py-20 ${styles.textMuted}`}>
            <p>暂无照片</p>
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
                      {photo.location && (
                        <div
                          className={`flex items-center gap-1 text-xs ${styles.textMuted} mb-2`}
                        >
                          <MapPin size={12} />
                          <span>{photo.location}</span>
                        </div>
                      )}
                      {photo.caption && (
                        <p
                          className={`text-sm ${styles.text} mb-2 leading-relaxed`}
                        >
                          {photo.caption}
                        </p>
                      )}
                      <div
                        className={`flex items-center gap-1 text-xs ${styles.textMuted}`}
                      >
                        <Calendar size={12} />
                        <span>
                          {new Date(photo.created_at).toLocaleDateString(
                            "zh-CN"
                          )}
                        </span>
                      </div>
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

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
    </div>
  );
};

export default PhotosPage;
