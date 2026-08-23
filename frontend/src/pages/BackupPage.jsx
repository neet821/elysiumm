import { useEffect, useMemo, useState } from "react";
import { DatabaseBackup, Download, RefreshCw, RotateCcw, Trash2 } from "lucide-react";
import apiClient from "../utils/request";
import { API_ENDPOINTS } from "../config";

const formatSize = (bytes = 0) => {
  if (!bytes) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  const index = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
  return `${(bytes / 1024 ** index).toFixed(index === 0 ? 0 : 2)} ${units[index]}`;
};

const formatDate = (value) => {
  if (!value) return "-";
  return new Date(value).toLocaleString();
};

const backupStatusLabel = (status) => ({
  completed: "已完成",
  failed: "失败",
  pending: "等待中",
  running: "进行中",
}[status] || "状态未知");
const backupTypeLabel = (type) => ({ database: "数据库" }[type] || "备份文件");

const BackupPage = ({ styles, isDark }) => {
  const [jobs, setJobs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const files = useMemo(
    () =>
      jobs.flatMap((job) =>
        (job.files || []).map((file) => ({
          ...file,
          job,
        })),
      ),
    [jobs],
  );

  const fetchBackups = async () => {
    setLoading(true);
    setError("");
    try {
      const response = await apiClient.get(API_ENDPOINTS.ADMIN_BACKUPS);
      setJobs(response.data || []);
    } catch (fetchError) {
      console.error("获取备份列表失败:", fetchError);
      setError("备份列表加载失败");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchBackups();
  }, []);

  const createBackup = async () => {
    setBusy(true);
    setError("");
    try {
      await apiClient.post(API_ENDPOINTS.ADMIN_BACKUP_DATABASE);
      await fetchBackups();
    } catch (createError) {
      console.error("创建备份失败:", createError);
      setError("创建备份失败");
    } finally {
      setBusy(false);
    }
  };

  const downloadBackup = async (file) => {
    try {
      const response = await apiClient.get(API_ENDPOINTS.ADMIN_BACKUP_DOWNLOAD(file.id), {
        responseType: "blob",
      });
      const blobUrl = window.URL.createObjectURL(response.data);
      const anchor = document.createElement("a");
      anchor.href = blobUrl;
      anchor.download = file.filename || `backup-${file.id}`;
      anchor.click();
      window.URL.revokeObjectURL(blobUrl);
    } catch (downloadError) {
      console.error("下载备份失败:", downloadError);
      alert("下载失败，请重试");
    }
  };

  const deleteBackup = async (file) => {
    if (!window.confirm("确定删除这份备份文件吗？")) return;

    setBusy(true);
    try {
      await apiClient.delete(API_ENDPOINTS.ADMIN_BACKUP_FILE(file.id));
      await fetchBackups();
    } catch (deleteError) {
      console.error("删除备份失败:", deleteError);
      alert("删除失败，请重试");
    } finally {
      setBusy(false);
    }
  };

  const restoreBackup = async (file) => {
    if (!window.confirm("恢复数据库会先自动备份当前状态，然后用所选备份覆盖当前数据库。确定继续吗？")) return;

    setBusy(true);
    try {
      await apiClient.post(API_ENDPOINTS.ADMIN_BACKUP_RESTORE(file.id));
      await fetchBackups();
      alert("恢复完成");
    } catch (restoreError) {
      console.error("恢复备份失败:", restoreError);
      alert("恢复失败，请检查备份文件是否存在且校验通过");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className={`admin-legacy-panel ${styles.bgSecondary} transition-colors duration-700`}>
      <div className="max-w-6xl mx-auto">
        <div className="flex flex-col md:flex-row md:items-end justify-between gap-5 mb-8">
          <div>
            <div className="flex items-center gap-3 mb-2">
              <DatabaseBackup size={24} className={styles.accentClass} />
              <h1 className={`text-3xl font-serif font-semibold ${styles.text}`}>数据备份</h1>
            </div>
            <p className={`text-sm ${styles.textMuted}`}>创建、下载、删除和恢复数据库备份。恢复前会自动备份当前状态。</p>
          </div>
          <div className="flex gap-3">
            <button
              onClick={fetchBackups}
              disabled={busy || loading}
              className={`h-10 w-10 inline-flex items-center justify-center rounded-lg border ${styles.border} transition-colors disabled:opacity-50 ${
                isDark ? "hover:bg-white/5" : "hover:bg-stone-100"
              }`}
              title="刷新"
            >
              <RefreshCw size={18} className={`${styles.textMuted} ${loading ? "animate-spin" : ""}`} />
            </button>
            <button
              onClick={createBackup}
              disabled={busy}
              className={`flex items-center gap-2 px-4 py-2 text-white rounded-lg transition-colors disabled:opacity-50 ${
                isDark ? "bg-blue-500 hover:bg-blue-400" : "bg-[#2A5C8D] hover:bg-[#1f4d78]"
              }`}
            >
              <DatabaseBackup size={18} />
              {busy ? "处理中..." : "创建备份"}
            </button>
          </div>
        </div>

        {error && (
          <div className={`mb-6 p-4 rounded-lg border ${
            isDark ? "bg-red-500/10 border-red-500/30 text-red-200" : "bg-red-50 border-red-200 text-red-700"
          }`}>
            {error}
          </div>
        )}

        <div className={`${styles.bg} rounded-xl border ${styles.border} shadow-sm overflow-hidden`}>
          <div className={`hidden md:grid grid-cols-[1.2fr_120px_160px_1fr_220px] gap-4 px-5 py-3 text-xs font-semibold ${styles.textMuted} border-b ${styles.border}`}>
            <span>类型</span>
            <span>大小</span>
            <span>状态</span>
            <span>时间</span>
            <span className="text-right">操作</span>
          </div>

          {loading ? (
            <div className={`text-center py-12 ${styles.textMuted}`}>
              <RefreshCw className="animate-spin mx-auto mb-4" size={28} />
              加载中...
            </div>
          ) : files.length === 0 ? (
            <div className={`text-center py-12 ${styles.textMuted}`}>暂无备份</div>
          ) : (
            <div className="divide-y divide-black/5 dark:divide-white/10">
              {files.map((file) => (
                <div
                  key={file.id}
                  className="grid grid-cols-1 md:grid-cols-[1.2fr_120px_160px_1fr_220px] gap-3 md:gap-4 px-5 py-4 md:items-center"
                >
                  <div className="min-w-0">
                    <p className={`font-medium ${styles.text}`}>{backupTypeLabel(file.type)}</p>
                    <p className={`text-xs ${styles.textMuted} truncate`} title={file.filename}>
                      {file.filename}
                    </p>
                    <p className={`text-xs ${styles.textMuted} truncate md:hidden`}>{file.sha256}</p>
                  </div>
                  <span className={`text-sm ${styles.textMuted}`}>{formatSize(file.file_size)}</span>
                  <span className={`w-fit rounded-full px-2 py-1 text-xs ${
                    file.job.status === "completed"
                      ? isDark ? "bg-green-400/10 text-green-200" : "bg-green-50 text-green-700"
                      : isDark ? "bg-yellow-400/10 text-yellow-200" : "bg-yellow-50 text-yellow-700"
                  }`}>
                    {backupStatusLabel(file.job.status)}
                  </span>
                  <span className={`text-sm ${styles.textMuted}`}>{formatDate(file.created_at)}</span>
                  <div className="flex justify-start md:justify-end gap-2">
                    <button
                      onClick={() => downloadBackup(file)}
                      className={`h-9 w-9 inline-flex items-center justify-center rounded-lg border ${styles.border}`}
                      title="下载"
                    >
                      <Download size={16} className={styles.textMuted} />
                    </button>
                    <button
                      onClick={() => restoreBackup(file)}
                      disabled={busy}
                      className={`h-9 w-9 inline-flex items-center justify-center rounded-lg border ${styles.border} disabled:opacity-50`}
                      title="恢复"
                    >
                      <RotateCcw size={16} className={styles.textMuted} />
                    </button>
                    <button
                      onClick={() => deleteBackup(file)}
                      disabled={busy}
                      className="h-9 w-9 inline-flex items-center justify-center rounded-lg border border-red-200 text-red-500 disabled:opacity-50"
                      title="删除"
                    >
                      <Trash2 size={16} />
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default BackupPage;
