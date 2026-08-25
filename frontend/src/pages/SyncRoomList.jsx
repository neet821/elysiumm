import React, { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import {
  ArrowLeft,
  Plus,
  Film,
  Users,
  Lock,
  Clock,
  Play,
  Pause,
  Trash2,
  ExternalLink,
  User,
  Gamepad2,
} from "lucide-react";
import { useAuth } from "../contexts/AuthContext";
import apiClient from "../utils/request";
import { API_ENDPOINTS } from "../config";
import {
  formatEmptyRoomCountdown,
  getOnlineMemberCount,
} from "./syncRoomListUtils.js";

const buildRoomPayload = (roomName, isMusicRoom) => {
  const payload = { room_name: roomName };
  if (isMusicRoom) {
    Object.assign(payload, {
      control_mode: "host_only",
      mode: "music",
      type: "video",
    });
  }
  return payload;
};

const SyncRoomList = ({ styles, isDark, embedded = false, roomMode = "video" }) => {
  const navigate = useNavigate();
  const { user } = useAuth();
  const isMusicRoom = roomMode === "music";
  const pageTitle = isMusicRoom ? "同步听歌室管理" : "同步观影室管理";
  const pageDescription = isMusicRoom
    ? "创建或加入房间，与朋友一起听歌 · 空房间将在10分钟后自动关闭"
    : "创建或加入房间，与朋友一起观看视频 · 空房间将在10分钟后自动关闭";
  const createButtonLabel = isMusicRoom ? "创建听歌房" : "创建新房间";
  const modalTitle = isMusicRoom ? "创建听歌房间" : "创建观影房间";
  const matchesRoomMode = (room) => (isMusicRoom ? room.mode === "music" : room.mode !== "music");
  const [rooms, setRooms] = useState([]);
  const [myRooms, setMyRooms] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [roomName, setRoomName] = useState("");
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    fetchRooms();
    const refreshInterval = setInterval(fetchRooms, 10000); // 每10秒刷新一次
    const clockInterval = setInterval(() => setNow(Date.now()), 1000);
    return () => {
      clearInterval(refreshInterval);
      clearInterval(clockInterval);
    };
  }, []);

  const fetchRooms = async () => {
    try {
      const response = await apiClient.get(API_ENDPOINTS.SYNC_ROOMS);
      const allRooms = response.data || [];
      const visibleRooms = allRooms.filter(matchesRoomMode);
      setRooms(visibleRooms);

      // 筛选出我创建的房间
      if (user) {
        const userRooms = visibleRooms.filter(room => room.host?.id === user.id);
        setMyRooms(userRooms);
      }
    } catch (error) {
      console.error("获取房间列表失败:", error);
    } finally {
      setLoading(false);
    }
  };

  const handleCreateRoom = async (e) => {
    e.preventDefault();

    // 检查用户是否登录
    if (!user) {
      alert("请先登录后再创建房间");
      navigate("/login");
      return;
    }

    try {
      const payload = buildRoomPayload(roomName, isMusicRoom);

      const response = await apiClient.post(API_ENDPOINTS.SYNC_ROOMS, payload);

      setShowCreateModal(false);
      resetForm();
      navigate(`${isMusicRoom ? "/rooms/music" : "/rooms/watch"}/${response.data.id}`);
    } catch (error) {
      console.error("创建房间失败:", error);
      alert(error.response?.data?.detail || "创建失败，请重试");
    }
  };

  const handleJoinRoom = async (roomId) => {
    try {
      await apiClient.post(API_ENDPOINTS.SYNC_ROOM_JOIN(roomId));
      navigate(`${isMusicRoom ? "/rooms/music" : "/rooms/watch"}/${roomId}`);
    } catch (error) {
      console.error("加入房间失败:", error);
      alert(error.response?.data?.detail || "加入失败，请重试");
    }
  };

  const handleDeleteRoom = async (roomId) => {
    if (!confirm("确定要删除这个房间吗？")) return;

    try {
      await apiClient.delete(`${API_ENDPOINTS.SYNC_ROOMS}/${roomId}`);
      fetchRooms();
    } catch (error) {
      console.error("删除房间失败:", error);
      alert("删除失败，请重试");
    }
  };

  const resetForm = () => {
    setRoomName("");
  };

  const RoomCard = ({ room, showDelete = false }) => {
    const onlineMemberCount = getOnlineMemberCount(room);
    const isEmpty = onlineMemberCount === 0;

    return (
    <div
      className={`${styles.bg} p-4 sm:p-6 rounded-xl border ${
        styles.border
      } shadow-sm transition-all duration-300 group relative overflow-hidden
        ${isDark ? "hover:border-orange-500" : "hover:border-[#189BCC] hover:shadow-lg"}
      `}
    >
      <div className="flex justify-between items-start mb-4">
        <div className="flex-1">
          <div className="flex items-center gap-2 mb-2">
            <div
              className={`w-2 h-2 rounded-full ${
                room.is_playing
                  ? "bg-green-500 animate-pulse"
                  : "bg-gray-400"
              }`}
            ></div>
            <h4
              className={`font-bold text-base sm:text-lg ${styles.text} group-hover:${styles.accentClass} transition-colors`}
            >
              {room.room_name}
            </h4>
            {room.type === 'game' && (
              <span className={`px-1.5 py-0.5 rounded text-[10px] bg-purple-100 text-purple-700 dark:bg-purple-900 dark:text-purple-300`}>
                {room.game_type === 'gomoku' ? '五子棋' : room.game_type}
              </span>
            )}
            {room.control_mode === "host_only" && (
              <Lock size={14} className={styles.textMuted} />
            )}
          </div>

          <div className="flex items-center gap-2 text-xs sm:text-sm mb-2">
            <span className={`${styles.textMuted} flex items-center gap-1`}>
              <User size={12} />
              房主：{room.host?.username || "未知"}
            </span>
          </div>
        </div>

        {showDelete && (
          <button
            onClick={(e) => {
              e.stopPropagation();
              handleDeleteRoom(room.id);
            }}
            className="relative z-10 text-red-500 hover:text-red-600 p-2"
            title="删除房间"
          >
            <Trash2 size={16} />
          </button>
        )}
      </div>

      <div className="space-y-2 mb-4">
        <div
          className={`flex items-center justify-between text-xs sm:text-sm p-2 rounded ${
            isDark ? "bg-gray-800" : "bg-gray-50"
          }`}
        >
          <span className={`${styles.textMuted} flex items-center gap-1`}>
            <Users size={14} />
            {isEmpty ? "空房间" : `在线成员 ${onlineMemberCount} / ${room.max_members || 10}`}
          </span>
          <span
            className={`flex items-center gap-1 px-2 py-0.5 rounded text-xs ${
              room.is_playing
                ? "bg-green-100 text-green-700 dark:bg-green-900 dark:text-green-300"
                : "bg-gray-200 text-gray-600 dark:bg-gray-700 dark:text-gray-400"
            }`}
          >
            {room.is_playing ? <Play size={10} /> : <Pause size={10} />}
            {room.is_playing ? "播放中" : "已暂停"}
          </span>
        </div>

        <div className={`text-xs ${styles.textMuted} flex items-center justify-between`}>
          <span className="flex items-center gap-1">
            {room.type === 'game' ? <Gamepad2 size={12} /> : <Film size={12} />}
            {isMusicRoom
              ? "同步听歌"
              : room.type === 'game'
                ? '桌游房间'
                : (room.mode === "url" || room.mode === "link" ? "网络地址" : room.mode === "upload" ? "上传视频" : "本地同步")
            }
          </span>
          <span>房间号: {room.room_code}</span>
        </div>

        {isEmpty && (
          <div className={`text-xs ${styles.textMuted} flex items-center gap-1`} role="status">
            <Clock size={12} />
            {formatEmptyRoomCountdown(room.last_activity_at, now)}
          </div>
        )}
      </div>

      <button
        onClick={() => handleJoinRoom(room.id)}
        className={`w-full py-2 rounded-lg text-white text-sm font-medium transition-colors ${
          isDark
            ? "bg-orange-600 hover:bg-orange-500"
            : "bg-[#189BCC] hover:bg-[#1589b5]"
        }`}
      >
        <span className="flex items-center justify-center gap-2">
          进入房间
          <ExternalLink size={14} />
        </span>
      </button>

      <div
        aria-hidden="true"
        className={`pointer-events-none absolute right-0 top-0 w-20 h-20 rounded-bl-full -mr-10 -mt-10 transition-transform group-hover:scale-150 ${
          isDark ? "bg-orange-500/10" : "bg-[#189BCC]/5"
        }`}
      ></div>
    </div>
    );
  };

  return (
    <div className={(embedded ? "pt-6" : `pt-24 sm:pt-28 md:pt-32 pb-16 md:pb-20 min-h-screen ${styles.bgSecondary}`) + " transition-colors duration-1000 animate-fade-in"}>
      <div className={embedded ? "max-w-6xl mx-auto px-6" : "max-w-7xl mx-auto px-4 sm:px-6 lg:px-8"}>
        {!embedded && (
          <button
            onClick={() => navigate("/rooms")}
            className={`flex items-center gap-2 ${styles.textMuted} hover:${styles.text} mb-6 md:mb-8 transition-colors text-sm`}
          >
            <ArrowLeft size={16} />
            返回房间
          </button>
        )}

        <div
          className={`${styles.bg} border ${styles.border} rounded-xl p-4 sm:p-6 shadow-sm mb-6 md:mb-8`}
        >
          <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
            <div className="flex-1">
              <h3
                className={`text-lg sm:text-xl font-bold ${styles.text} flex items-center gap-2 mb-1`}
              >
                <Film size={20} className={styles.accentClass} />
                {pageTitle}
              </h3>
              <p className={`text-xs sm:text-sm ${styles.textMuted}`}>
                {pageDescription}
              </p>
            </div>
            <button
              onClick={() => setShowCreateModal(true)}
              className={`w-full sm:w-auto flex items-center justify-center gap-2 text-white px-4 py-2 rounded-lg text-sm transition-colors ${
                isDark
                  ? "bg-orange-600 hover:bg-orange-500"
                  : "bg-[#189BCC] hover:bg-[#1589b5]"
              }`}
            >
              <Plus size={16} />
              {createButtonLabel}
            </button>
          </div>
        </div>

        {loading ? (
          <div className="flex justify-center py-12">
            <div className="animate-spin w-12 h-12 border-4 border-gray-300 border-t-blue-500 rounded-full"></div>
          </div>
        ) : (
          <>
            {/* 我创建的房间 */}
            {myRooms.length > 0 && (
              <div className="mb-8 md:mb-12">
                <h3 className={`text-lg sm:text-xl font-bold ${styles.text} mb-4 flex items-center gap-2`}>
                  <User size={20} />
                  我创建的房间
                </h3>
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 md:gap-6">
                  {myRooms.map((room) => (
                    <RoomCard key={room.id} room={room} showDelete={true} />
                  ))}
                </div>
              </div>
            )}

            {/* 所有活跃房间 */}
            <div>
              <h3 className={`text-lg sm:text-xl font-bold ${styles.text} mb-4 flex items-center gap-2`}>
                <Film size={20} />
                所有活跃房间 ({rooms.length})
              </h3>

              {rooms.length === 0 ? (
                <div
                  className={`${styles.bg} rounded-xl border ${styles.border} p-12 text-center`}
                >
                  <Film size={48} className={`${styles.textMuted} mx-auto mb-4`} />
                  <p className={`${styles.textMuted}`}>暂无活跃房间</p>
                  <p className={`${styles.textMuted} text-sm mt-2`}>点击上方按钮创建第一个房间</p>
                </div>
              ) : (
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 md:gap-6 animate-fade-in">
                  {rooms.map((room) => (
                    <RoomCard key={room.id} room={room} showDelete={false} />
                  ))}
                </div>
              )}
            </div>
          </>
        )}
      </div>

      {/* 创建房间模态框 */}
      {showCreateModal && (
        <div className="fixed inset-0 bg-black/50 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className={`${styles.bg} rounded-xl p-6 max-w-lg w-full max-h-[90vh] overflow-y-auto`}>
            <h3 className={`text-xl font-bold ${styles.text} mb-6`}>
              {modalTitle}
            </h3>

            <form onSubmit={handleCreateRoom} className="space-y-4">
              <div>
                <label htmlFor="sync-room-name" className={`block text-sm ${styles.text} mb-2`}>
                  房间名称
                </label>
                <input
                  id="sync-room-name"
                  type="text"
                  value={roomName}
                  onChange={(e) => setRoomName(e.target.value)}
                  className={`w-full px-4 py-2 border ${styles.border} rounded ${styles.bgSecondary} ${styles.text} focus:outline-none focus:ring-2 ${
                    isDark ? "focus:ring-orange-500" : "focus:ring-[#189BCC]"
                  }`}
                  placeholder="输入房间名称"
                  required
                />
              </div>

              <p className={`text-sm ${styles.textMuted}`}>{isMusicRoom ? "播放曲目和控制权限将在进入房间后设置。" : "视频来源和控制权限将在进入房间后设置。"}</p>

              <div className="flex gap-3 mt-6">
                <button
                  type="submit"
                  className={`flex-1 py-2 text-white rounded transition-colors ${
                    isDark
                      ? "bg-orange-600 hover:bg-orange-500"
                      : "bg-[#189BCC] hover:bg-[#1589b5]"
                  }`}
                >
                  创建房间
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setShowCreateModal(false);
                    resetForm();
                  }}
                  className={`flex-1 py-2 border ${styles.border} rounded ${styles.text} hover:${styles.bgSecondary} transition-colors`}
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

export default SyncRoomList;
