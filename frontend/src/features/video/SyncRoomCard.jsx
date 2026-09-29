import {
  Clock,
  Copy,
  ExternalLink,
  Film,
  Lock,
  Pause,
  Play,
  Trash2,
  Unlock,
  User,
  Users,
} from "lucide-react";
import {
  formatEmptyRoomCountdown,
  getOnlineMemberCount,
} from "./syncRoomListUtils.js";

export default function SyncRoomCard({
  room,
  showDelete = false,
  styles,
  isDark,
  isMusicRoom,
  isAdmin,
  now,
  copied,
  onDelete,
  onToggleLock,
  onCopyShare,
  onJoin,
}) {
  const onlineMemberCount = getOnlineMemberCount(room);
  const isEmpty = onlineMemberCount === 0;
  const canDelete = isAdmin || (showDelete && !room.is_locked);

  return (
    <div
      className={`${styles.bg} p-4 sm:p-6 rounded-xl border ${styles.border} shadow-sm transition-all duration-300 group relative overflow-hidden ${
        isDark ? "hover:border-orange-500" : "hover:border-[#189BCC] hover:shadow-lg"
      }`}
    >
      <div className="flex justify-between items-start mb-4">
        <div className="flex-1">
          <div className="flex items-center gap-2 mb-2">
            <div
              className={`w-2 h-2 rounded-full ${
                room.is_playing ? "bg-green-500 animate-pulse" : "bg-gray-400"
              }`}
            />
            <h4
              className={`font-bold text-base sm:text-lg ${styles.text} group-hover:${styles.accentClass} transition-colors`}
            >
              {room.room_name}
            </h4>
            {room.control_mode === "host_only" && (
              <Lock size={14} className={styles.textMuted} />
            )}
            {room.is_locked ? (
              <Lock size={14} className="text-amber-500" title="已锁定，不自动删除" />
            ) : (
              <Unlock size={14} className={styles.textMuted} title="空房间会自动删除" />
            )}
          </div>

          <div className="flex items-center gap-2 text-xs sm:text-sm mb-2">
            <span className={`${styles.textMuted} flex items-center gap-1`}>
              <User size={12} />
              房主：{room.host?.username || "未知"}
            </span>
          </div>
        </div>

        {canDelete && (
          <button
            onClick={(event) => {
              event.stopPropagation();
              onDelete(room.id);
            }}
            className="relative z-10 text-red-500 hover:text-red-600 p-2"
            title="删除房间"
          >
            <Trash2 size={16} />
          </button>
        )}
        {isAdmin && (
          <button
            onClick={(event) => {
              event.stopPropagation();
              onToggleLock(room);
            }}
            className={`relative z-10 p-2 rounded ${room.is_locked ? "text-amber-500 hover:text-amber-600" : `${styles.textMuted} hover:${styles.text}`} transition-colors`}
            title={room.is_locked ? "解除锁定" : "锁定房间，不自动删除"}
            aria-label={room.is_locked ? `解除 ${room.room_name} 的锁定` : `锁定 ${room.room_name}，不自动删除`}
            aria-pressed={room.is_locked}
          >
            {room.is_locked ? <Lock size={16} /> : <Unlock size={16} />}
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
            <Film size={12} />
            {isMusicRoom
              ? "听歌房"
              : room.mode === "url" || room.mode === "link"
                ? "网络地址"
                : room.mode === "upload"
                  ? "上传视频"
                  : "本地同步"}
          </span>
          <button
            type="button"
            onClick={(event) => onCopyShare(event, room.id)}
            className="room-share-button"
            aria-label="复制分享链接"
          >
            <Copy size={12} /> {copied ? "已复制" : "复制分享链接"}
          </button>
        </div>

        <div className={`text-xs ${styles.textMuted} flex items-center justify-between gap-2`} role="status">
          <span className="flex items-center gap-1">
            {room.is_locked ? <Lock size={12} className="text-amber-500" /> : <Unlock size={12} />}
            {room.is_locked ? "已锁定 · 不自动删除" : "未锁定 · 空房间会自动删除"}
          </span>
          {isEmpty && !room.is_locked && (
            <span className="flex items-center gap-1">
              <Clock size={12} />
              {formatEmptyRoomCountdown(room.last_activity_at, now)}
            </span>
          )}
        </div>
      </div>

      <button
        onClick={() => onJoin(room.id)}
        className={`w-full py-2 rounded-lg text-white text-sm font-medium transition-colors ${
          isDark ? "bg-orange-600 hover:bg-orange-500" : "bg-[#189BCC] hover:bg-[#1589b5]"
        }`}
      >
        <span className="flex items-center justify-center gap-2">
          进入房间
          <ExternalLink size={14} />
        </span>
      </button>
    </div>
  );
}
