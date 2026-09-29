export default function SyncRoomCreateModal({
  open,
  styles,
  isDark,
  isMusicRoom,
  title,
  roomName,
  onRoomNameChange,
  onSubmit,
  onClose,
}) {
  if (!open) return null;

  return (
    <div className="fixed inset-0 bg-black/50 backdrop-blur-sm z-50 flex items-center justify-center p-4">
      <div className={`${styles.bg} rounded-xl p-6 max-w-lg w-full max-h-[90vh] overflow-y-auto`}>
        <h3 className={`text-xl font-bold ${styles.text} mb-6`}>{title}</h3>

        <form onSubmit={onSubmit} className="space-y-4">
          <div>
            <label htmlFor="sync-room-name" className={`block text-sm ${styles.text} mb-2`}>
              房间名称
            </label>
            <input
              id="sync-room-name"
              type="text"
              value={roomName}
              onChange={(event) => onRoomNameChange(event.target.value)}
              className={`w-full px-4 py-2 border ${styles.border} rounded ${styles.bgSecondary} ${styles.text} focus:outline-none focus:ring-2 ${
                isDark ? "focus:ring-orange-500" : "focus:ring-[#189BCC]"
              }`}
              placeholder="输入房间名称"
              required
            />
          </div>

          <p className={`text-sm ${styles.textMuted}`}>
            {isMusicRoom
              ? "播放曲目和控制权限将在进入房间后设置。"
              : "视频来源和控制权限将在进入房间后设置。"}
          </p>

          <div className="flex gap-3 mt-6">
            <button
              type="submit"
              className={`flex-1 py-2 text-white rounded transition-colors ${
                isDark ? "bg-orange-600 hover:bg-orange-500" : "bg-[#189BCC] hover:bg-[#1589b5]"
              }`}
            >
              创建房间
            </button>
            <button
              type="button"
              onClick={onClose}
              className={`flex-1 py-2 border ${styles.border} rounded ${styles.text} hover:${styles.bgSecondary} transition-colors`}
            >
              取消
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
