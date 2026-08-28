import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import {
  Video, Music, Users, Clock, User, Settings,
  Eye, Trash2, Lock, PlayCircle, PauseCircle,
  AlertCircle, CheckCircle
} from "lucide-react";
import apiClient from "../utils/request";
import { API_ENDPOINTS } from "../config";

const AdminRoomsPage = ({ styles, isDark }) => {
  const navigate = useNavigate();
  const [rooms, setRooms] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [roomToDelete, setRoomToDelete] = useState(null);
  const [deleting, setDeleting] = useState(false);

  useEffect(() => {
    fetchRooms();
    // 每10秒刷新一次
    const interval = setInterval(fetchRooms, 10000);
    return () => clearInterval(interval);
  }, []);

  const fetchRooms = async () => {
    try {
      setError(null);
      const response = await apiClient.get(API_ENDPOINTS.ADMIN_ROOMS);
      console.log("Rooms data:", response.data);

      // 后端返回 {rooms: [...], total: number} 格式
      let roomsData = response.data?.rooms || response.data;

      // 确保返回的是数组
      if (!Array.isArray(roomsData)) {
        console.warn("API返回的不是数组格式:", roomsData);
        roomsData = [];
      }

      setRooms(roomsData);
      setLoading(false);
    } catch (error) {
      console.error("获取房间列表失败:", error);
      const errorMsg = error.response?.data?.detail || error.message || "获取房间失败";
      setError(errorMsg);
      setLoading(false);
    }
  };

  const getStatusColor = (isPlaying) => {
    if (isPlaying) return "bg-green-500";
    return "bg-gray-400";
  };

  const getStatusText = (isPlaying) => {
    if (isPlaying) return "播放中";
    return "暂停";
  };

  const formatTime = (dateString) => {
    if (!dateString) return "未知";
    const date = new Date(dateString);
    return date.toLocaleString("zh-CN", {
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    });
  };

  const getAutoCloseMinutes = (lastActivityAt) => {
    if (!lastActivityAt) return "30分钟后";
    const lastActivity = new Date(lastActivityAt);
    const autoCloseTime = new Date(lastActivity.getTime() + 30 * 60 * 1000); // +30分钟
    const now = new Date();
    const remaining = Math.floor((autoCloseTime - now) / 1000 / 60); // 剩余分钟数

    if (remaining <= 0) return "0分钟后";  // 🔧 显示具体数字
    if (remaining < 60) return `${remaining}分钟后`;
    const hours = Math.floor(remaining / 60);
    const mins = remaining % 60;
    return `${hours}小时${mins}分钟后`;
  };

  // 删除房间
  const handleDeleteRoom = async (roomId) => {
    setDeleting(true);
    try {
      await apiClient.delete(`${API_ENDPOINTS.ADMIN_ROOMS}/${roomId}`);
      setRooms(rooms.filter(room => room.id !== roomId));
      setShowDeleteConfirm(false);
      setRoomToDelete(null);
    } catch (error) {
      console.error('删除房间失败:', error);
      alert(error.response?.data?.detail || '删除房间失败');
    } finally {
      setDeleting(false);
    }
  };

  // 查房 - 进入房间
  const handleInspectRoom = (room) => {
    navigate(`/rooms/watch/${room.id}?stealth=1`);
  };

  // 分离视频和音乐房间
  const videoRooms = rooms.filter(room => room.room_type !== 'music');
  const musicRooms = rooms.filter(room => room.room_type === 'music');

  if (loading) {
    return (
      <div className={`admin-legacy-panel ${styles.bg} flex items-center justify-center`}>
        <div className="animate-spin w-12 h-12 border-4 border-gray-300 border-t-blue-500 rounded-full"></div>
      </div>
    );
  }

  return (
    <div className={`admin-legacy-panel ${styles.bg} transition-colors duration-1000 animate-fade-in`}>
      <div className="max-w-7xl mx-auto">
        {/* 标题 */}
        <h2 className={`text-3xl font-bold ${styles.text} mb-8`}>房间管理</h2>

        <div className={`${styles.bgSecondary} border ${styles.border} p-4 mb-8`} aria-label="房间汇总">
          <p className={`text-sm ${styles.textMuted}`}>
            {videoRooms.length + musicRooms.length} 个活跃媒体房
          </p>
        </div>

        {/* 错误提示 */}
        {error && (
          <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 p-6 text-center mb-8">
            <p className="text-red-600 dark:text-red-400 font-medium mb-2">加载失败</p>
            <p className="text-red-500 dark:text-red-300 text-sm mb-4">{error}</p>
            <button
              onClick={fetchRooms}
              className="px-4 py-2 bg-red-600 hover:bg-red-500 text-white rounded-lg transition-colors"
            >
              重试
            </button>
          </div>
        )}

        {/* 视频房间区域 */}
        <div className="mb-12">
          <div className={`flex items-center gap-3 mb-6 pb-3 border-b-2 ${isDark ? 'border-orange-500/30' : 'border-[#189BCC]/30'}`}>
            <Video size={24} className={isDark ? 'text-orange-500' : 'text-[#189BCC]'} />
            <h3 className={`text-xl font-bold ${styles.text}`}>
              视频房间
              <span className={`ml-2 text-sm ${styles.textMuted}`}>({videoRooms.length})</span>
            </h3>
          </div>

          {videoRooms.length === 0 ? (
            <div className={`${styles.bg} border ${styles.border} p-12 text-center`}>
              <Video size={48} className={`${styles.textMuted} mx-auto mb-4`} />
              <p className={`${styles.textMuted}`}>暂无视频房间</p>
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
              {videoRooms.map((room) => (
                <div
                  key={room.id}
                  className={`${styles.bg} border ${styles.border} p-6 transition-all hover:shadow-lg ${
                    isDark ? 'hover:border-orange-500/50' : 'hover:border-[#189BCC]/50'
                  }`}
                >
                  {/* 头部 - 状态和操作按钮 */}
                  <div className="flex items-center justify-between mb-3">
                    <div className="flex items-center gap-2">
                      <div className={`w-2 h-2 rounded-full ${getStatusColor(room.is_playing)} ${room.is_playing ? 'animate-pulse' : ''}`}></div>
                      <span className={`text-xs font-medium ${
                        room.is_playing
                          ? isDark ? 'text-orange-500' : 'text-[#189BCC]'
                          : styles.textMuted
                      }`}>
                        {getStatusText(room.is_playing)}
                      </span>
                      {room.password_hash && (
                        <Lock size={12} className={`${styles.textMuted}`} title="密码保护" />
                      )}
                      {room.is_locked && (
                        <Lock size={12} className="text-amber-500" title="已锁定，不自动删除" />
                      )}
                      {room.is_active ? (
                        <CheckCircle size={12} className="text-green-500" title="房间活跃" />
                      ) : (
                        <AlertCircle size={12} className="text-yellow-500" title="房间不活跃" />
                      )}
                    </div>

                    {/* 操作按钮 */}
                    <div className="flex items-center gap-1">
                      <button
                        onClick={() => handleInspectRoom(room)}
                        className={`p-1.5 rounded ${isDark ? 'hover:bg-gray-700' : 'hover:bg-gray-100'} transition-colors`}
                        title="查房"
                      >
                        <Eye size={14} className={isDark ? 'text-orange-400' : 'text-[#189BCC]'} />
                      </button>
                      <button
                        onClick={() => {
                          setRoomToDelete(room);
                          setShowDeleteConfirm(true);
                        }}
                        className={`p-1.5 rounded hover:bg-red-50 dark:hover:bg-red-900/20 transition-colors`}
                        title="删除房间"
                      >
                        <Trash2 size={14} className="text-red-500" />
                      </button>
                    </div>
                  </div>

                  {/* 房间信息 */}
                  <h4 className={`font-bold ${styles.text} text-lg mb-2 truncate`}>
                    {room.room_name}
                  </h4>
                  <p className={`${styles.textMuted} text-xs mb-1 font-mono`}>
                    #{room.room_code}
                  </p>

                  <div className="space-y-2 mt-4 pt-4 border-t border-gray-200 dark:border-gray-700">
                    <div className="flex items-center gap-2 text-xs">
                      <User size={12} className={styles.textMuted} />
                      <span className={styles.textMuted}>
                        房主: {room.host?.username || "未知"}
                      </span>
                    </div>

                    <div className="flex items-center gap-2 text-xs">
                      <Users size={12} className={styles.textMuted} />
                      <span className={styles.textMuted}>
                        成员: {room.member_count || 0} 人
                      </span>
                    </div>

                    <div className="flex items-center gap-2 text-xs">
                      {room.is_playing ? (
                        <PlayCircle size={12} className="text-green-500" />
                      ) : (
                        <PauseCircle size={12} className={styles.textMuted} />
                      )}
                      <span className={styles.textMuted}>
                        模式: {room.mode === 'link' ? '在线' : room.mode === 'upload' ? '上传' : '本地'}
                      </span>
                    </div>

                    <div className="flex items-center gap-2 text-xs">
                      <Settings size={12} className={styles.textMuted} />
                      <span className={styles.textMuted}>
                        控制: {room.control_mode === 'host_only' ? '仅房主' : '所有人'}
                      </span>
                    </div>

                    <div className="flex items-center gap-2 text-xs">
                      <Clock size={12} className={styles.textMuted} />
                      <span className={styles.textMuted}>
                        创建: {formatTime(room.created_at)}
                      </span>
                    </div>

                    {room.video_source && (
                      <div className={`text-xs ${styles.textMuted} truncate`} title={room.video_source}>
                        🎬 {room.video_source}
                      </div>
                    )}

                    {room.is_locked ? (
                      <div className="text-xs text-amber-500 mt-2 pt-2 border-t border-gray-200 dark:border-gray-700">
                        🔒 已锁定，不自动删除
                      </div>
                    ) : (room.last_activity_at || room.created_at) && (
                      <div className={`text-xs mt-2 pt-2 border-t border-gray-200 dark:border-gray-700 ${
                        isDark ? 'text-orange-400' : 'text-[#189BCC]'
                      }`}>
                        🕐 自动关闭: {getAutoCloseMinutes(room.last_activity_at || room.created_at)}
                      </div>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* 音乐房间区域 */}
        <div>
          <div className={`flex items-center gap-3 mb-6 pb-3 border-b-2 border-purple-500/30`}>
            <Music size={24} className="text-purple-500" />
            <h3 className={`text-xl font-bold ${styles.text}`}>
              音乐房间
              <span className={`ml-2 text-sm ${styles.textMuted}`}>({musicRooms.length})</span>
            </h3>
          </div>

          {musicRooms.length === 0 ? (
            <div className={`${styles.bg} border ${styles.border} p-12 text-center`}>
              <Music size={48} className={`${styles.textMuted} mx-auto mb-4`} />
              <p className={`${styles.textMuted}`}>暂无音乐房间</p>
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
              {musicRooms.map((room) => (
                <div
                  key={room.id}
                  className={`${styles.bg} border ${styles.border} p-6 transition-all hover:shadow-lg hover:border-purple-500/50`}
                >
                  {/* 头部 - 状态和操作按钮 */}
                  <div className="flex items-center justify-between mb-3">
                    <div className="flex items-center gap-2">
                      <div className={`w-2 h-2 rounded-full ${getStatusColor(room.is_playing)} ${room.is_playing ? 'animate-pulse' : ''}`}></div>
                      <span className={`text-xs font-medium ${room.is_playing ? 'text-purple-500' : styles.textMuted}`}>
                        {getStatusText(room.is_playing)}
                      </span>
                      {room.password_hash && (
                        <Lock size={12} className={`${styles.textMuted}`} title="密码保护" />
                      )}
                      {room.is_locked && (
                        <Lock size={12} className="text-amber-500" title="已锁定，不自动删除" />
                      )}
                      {room.is_active ? (
                        <CheckCircle size={12} className="text-green-500" title="房间活跃" />
                      ) : (
                        <AlertCircle size={12} className="text-yellow-500" title="房间不活跃" />
                      )}
                    </div>

                    {/* 操作按钮 */}
                    <div className="flex items-center gap-1">
                      <button
                        onClick={() => handleInspectRoom(room)}
                        className={`p-1.5 rounded ${isDark ? 'hover:bg-gray-700' : 'hover:bg-gray-100'} transition-colors`}
                        title="查房"
                      >
                        <Eye size={14} className="text-purple-400" />
                      </button>
                      <button
                        onClick={() => {
                          setRoomToDelete(room);
                          setShowDeleteConfirm(true);
                        }}
                        className={`p-1.5 rounded hover:bg-red-50 dark:hover:bg-red-900/20 transition-colors`}
                        title="删除房间"
                      >
                        <Trash2 size={14} className="text-red-500" />
                      </button>
                    </div>
                  </div>

                  <h4 className={`font-bold ${styles.text} text-lg mb-2 truncate`}>
                    {room.room_name}
                  </h4>
                  <p className={`${styles.textMuted} text-xs mb-1 font-mono`}>
                    #{room.room_code}
                  </p>

                  <div className="space-y-2 mt-4 pt-4 border-t border-gray-200 dark:border-gray-700">
                    <div className="flex items-center gap-2 text-xs">
                      <User size={12} className={styles.textMuted} />
                      <span className={styles.textMuted}>
                        房主: {room.host?.username || "未知"}
                      </span>
                    </div>

                    <div className="flex items-center gap-2 text-xs">
                      <Users size={12} className={styles.textMuted} />
                      <span className={styles.textMuted}>
                        成员: {room.member_count || 0} 人
                      </span>
                    </div>

                    <div className="flex items-center gap-2 text-xs">
                      <Clock size={12} className={styles.textMuted} />
                      <span className={styles.textMuted}>
                        创建: {formatTime(room.created_at)}
                      </span>
                    </div>

                    {room.is_locked ? (
                      <div className="text-xs text-amber-500 mt-2 pt-2 border-t border-gray-200 dark:border-gray-700">
                        🔒 已锁定，不自动删除
                      </div>
                    ) : (room.last_activity_at || room.created_at) && (
                      <div className="text-xs text-purple-400 mt-2 pt-2 border-t border-gray-200 dark:border-gray-700">
                        🕐 自动关闭: {getAutoCloseMinutes(room.last_activity_at || room.created_at)}
                      </div>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* 删除确认模态框 */}
      {showDeleteConfirm && roomToDelete && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm animate-fade-in">
          <div className={`${styles.bg} p-6 max-w-md w-full shadow-2xl border ${styles.border}`}>
            <div className="flex items-center gap-3 mb-4">
              <div className="p-3 rounded-full bg-red-100 dark:bg-red-900/30">
                <Trash2 size={24} className="text-red-600 dark:text-red-400" />
              </div>
              <div>
                <h3 className={`text-lg font-bold ${styles.text}`}>删除房间</h3>
                <p className={`text-sm ${styles.textMuted}`}>此操作不可撤销</p>
              </div>
            </div>

            <div className={`${styles.bgSecondary} p-4 mb-4`}>
              <p className={`text-sm ${styles.text} mb-2`}>
                确定要删除以下房间吗？
              </p>
              <p className={`font-bold ${styles.text}`}>{roomToDelete.room_name}</p>
              <p className={`text-xs ${styles.textMuted} font-mono mt-1`}>
                #{roomToDelete.room_code}
              </p>
              {roomToDelete.member_count > 0 && (
                <p className={`text-xs text-yellow-600 dark:text-yellow-400 mt-2`}>
                  ⚠️ 房间内还有 {roomToDelete.member_count} 位成员
                </p>
              )}
            </div>

            <div className="flex gap-3">
              <button
                onClick={() => {
                  setShowDeleteConfirm(false);
                  setRoomToDelete(null);
                }}
                disabled={deleting}
                className={`flex-1 px-4 py-2 rounded-lg border ${styles.border} ${styles.text} hover:${styles.bgSecondary} transition-colors disabled:opacity-50`}
              >
                取消
              </button>
              <button
                onClick={() => handleDeleteRoom(roomToDelete.id)}
                disabled={deleting}
                className="flex-1 px-4 py-2 rounded-lg bg-red-600 hover:bg-red-500 text-white transition-colors disabled:opacity-50"
              >
                {deleting ? '删除中...' : '确认删除'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default AdminRoomsPage;
