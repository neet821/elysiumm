import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { Film, Plus, User } from "lucide-react";
import { useAuth } from "../contexts/AuthContext";
import { THEME } from "../theme.js";
import "../features/player/player.css";
import { useSyncRoomLobby } from "../features/video/useSyncRoomLobby.js";
import SyncRoomCard from "../features/video/SyncRoomCard.jsx";
import SyncRoomCreateModal from "../features/video/SyncRoomCreateModal.jsx";
import { buildRoomShareUrl, copyText } from '../features/video/roomShareUtils.js'

const SyncRoomList = ({ styles = THEME.light, isDark = false, roomMode = "video" }) => {
  const navigate = useNavigate();
  const { user, isAdmin } = useAuth();
  const isMusicRoom = roomMode === "music";
  const pageTitle = isMusicRoom ? "同步听歌室管理" : "同步观影室管理";
  const pageDescription = isMusicRoom
    ? "创建或加入房间，与朋友一起听歌 · 空房间将在10分钟后自动关闭"
    : "创建或加入房间，与朋友一起观看视频 · 空房间将在10分钟后自动关闭";
  const createButtonLabel = isMusicRoom ? "创建听歌房" : "创建新房间";
  const modalTitle = isMusicRoom ? "创建听歌房间" : "创建观影房间";
  const {
    rooms,
    myRooms,
    loading,
    createRoom,
    joinRoom,
    deleteRoom,
    toggleRoomLock,
  } = useSyncRoomLobby({ roomMode, user, isAdmin });
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [roomName, setRoomName] = useState("");
  const [now, setNow] = useState(() => Date.now());
  const [copiedRoomId, setCopiedRoomId] = useState(null)

  useEffect(() => {
    const clockInterval = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(clockInterval);
  }, []);

  const handleCreateRoom = async (e) => {
    e.preventDefault();

    // 检查用户是否登录
    if (!user) {
      alert("请先登录后再创建房间");
      navigate("/login");
      return;
    }

    try {
      const response = await createRoom(roomName);

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
      await joinRoom(roomId);
      navigate(`${isMusicRoom ? "/rooms/music" : "/rooms/watch"}/${roomId}`);
    } catch (error) {
      console.error("加入房间失败:", error);
      alert(error.response?.data?.detail || "加入失败，请重试");
    }
  };

  const handleDeleteRoom = async (roomId) => {
    if (!confirm("确定要删除这个房间吗？")) return;

    try {
      await deleteRoom(roomId);
    } catch (error) {
      console.error("删除房间失败:", error);
      alert("删除失败，请重试");
    }
  };

  const handleToggleRoomLock = async (room) => {
    try {
      await toggleRoomLock(room);
    } catch (error) {
      console.error("设置房间锁定状态失败:", error);
      alert(error.response?.data?.detail || "设置失败，请重试");
    }
  };

  const resetForm = () => {
    setRoomName("");
  };

  const handleCopyShare = async (event, roomId) => {
    event.stopPropagation()
    try {
      await copyText(buildRoomShareUrl({ ...window.location, pathname: `${isMusicRoom ? '/rooms/music' : '/rooms/watch'}/${roomId}`, search: '', hash: '' }))
      setCopiedRoomId(roomId)
      window.setTimeout(() => setCopiedRoomId((value) => value === roomId ? null : value), 1800)
    } catch {
      alert('复制失败，请手动复制当前地址')
    }
  }

  return (
    <div className={`pt-24 sm:pt-28 md:pt-32 pb-16 md:pb-20 min-h-screen ${styles.bgSecondary} transition-colors duration-1000 animate-fade-in`}>
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
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
            {!isAdmin && myRooms.length > 0 && (
              <div className="mb-8 md:mb-12">
                <h3 className={`text-lg sm:text-xl font-bold ${styles.text} mb-4 flex items-center gap-2`}>
                  <User size={20} />
                  我创建的房间
                </h3>
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 md:gap-6">
                  {myRooms.map((room) => (
                    <SyncRoomCard
                      key={room.id}
                      room={room}
                      showDelete
                      styles={styles}
                      isDark={isDark}
                      isMusicRoom={isMusicRoom}
                      isAdmin={isAdmin}
                      now={now}
                      copied={copiedRoomId === room.id}
                      onDelete={handleDeleteRoom}
                      onToggleLock={handleToggleRoomLock}
                      onCopyShare={handleCopyShare}
                      onJoin={handleJoinRoom}
                    />
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
                    <SyncRoomCard
                      key={room.id}
                      room={room}
                      showDelete={isAdmin}
                      styles={styles}
                      isDark={isDark}
                      isMusicRoom={isMusicRoom}
                      isAdmin={isAdmin}
                      now={now}
                      copied={copiedRoomId === room.id}
                      onDelete={handleDeleteRoom}
                      onToggleLock={handleToggleRoomLock}
                      onCopyShare={handleCopyShare}
                      onJoin={handleJoinRoom}
                    />
                  ))}
                </div>
              )}
            </div>
          </>
        )}
      </div>

      <SyncRoomCreateModal
        open={showCreateModal}
        styles={styles}
        isDark={isDark}
        isMusicRoom={isMusicRoom}
        title={modalTitle}
        roomName={roomName}
        onRoomNameChange={setRoomName}
        onSubmit={handleCreateRoom}
        onClose={() => {
          setShowCreateModal(false);
          resetForm();
        }}
      />
    </div>
  );
};

export default SyncRoomList;
