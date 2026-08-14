import { useEffect, useState } from "react";
import {
  Activity,
  CheckCircle2,
  Database,
  HardDrive,
  RefreshCw,
  Server,
  ShieldCheck,
  XCircle,
} from "lucide-react";
import apiClient from "../utils/request";
import { API_ENDPOINTS } from "../config";

const formatMemory = (memory) => {
  if (!memory?.available) return "无法读取";
  return `${memory.available_mb} MB 可用 / ${memory.total_mb} MB`;
};

const formatDate = (value) => {
  if (!value) return "未知";
  return new Date(value).toLocaleString("zh-CN");
};

const AgentConsolePage = ({ styles, isDark }) => {
  const [status, setStatus] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const fetchStatus = async () => {
    try {
      setError("");
      const response = await apiClient.get(API_ENDPOINTS.AGENT_CONSOLE_STATUS);
      setStatus(response.data);
    } catch (err) {
      setError(err.response?.data?.detail || err.message || "状态加载失败");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchStatus();
  }, []);

  const healthyBackend = status?.backend?.online && status?.backend?.database === "connected";
  const loadAverage = status?.server?.load_average || [];

  return (
    <div className={`admin-legacy-panel ${styles.bgSecondary} transition-colors duration-1000`}>
      <div className="max-w-6xl mx-auto">
        <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between mb-8">
          <div>
            <h1 className={`text-3xl font-bold ${styles.text} flex items-center gap-3`}>
              <ShieldCheck size={28} className={isDark ? "text-orange-500" : "text-[#189BCC]"} />
              服务器状态
            </h1>
            <p className={`${styles.textMuted} mt-2`}>只读控制台，不包含 Codex、Codespace 或 GitHub 操作。</p>
          </div>
          <button
            onClick={fetchStatus}
            className={`h-11 px-4 flex items-center gap-2 rounded-lg border ${styles.border} ${styles.bg} ${styles.text} hover:shadow-sm transition`}
          >
            <RefreshCw size={18} />
            刷新
          </button>
        </div>

        {error && (
          <div className="mb-6 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-red-700">
            {error}
          </div>
        )}

        {loading ? (
          <div className="flex justify-center py-20">
            <div className="animate-spin w-12 h-12 border-4 border-gray-300 border-t-blue-500 rounded-full"></div>
          </div>
        ) : (
          <div className="space-y-6">
            <section className={`${styles.bg} border ${styles.border} rounded-lg p-6`}>
              <h2 className={`text-xl font-bold ${styles.text} mb-5 flex items-center gap-2`}>
                <Activity size={21} />
                当前状态
              </h2>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <StatusTile
                  icon={<Server size={20} />}
                  label="后端"
                  value={healthyBackend ? "正常" : "异常"}
                  detail={healthyBackend ? "数据库已连接" : status?.backend?.message || "数据库未连接"}
                  online={healthyBackend}
                  styles={styles}
                />
                <StatusTile
                  icon={<HardDrive size={20} />}
                  label="内存"
                  value={formatMemory(status?.server?.memory)}
                  detail={`已用 ${status?.server?.memory?.used_percent ?? 0}%`}
                  online={Boolean(status?.server?.memory?.available)}
                  styles={styles}
                />
                <StatusTile
                  icon={<Database size={20} />}
                  label="磁盘"
                  value={`${status?.server?.disk?.free_mb || 0} MB 可用`}
                  detail={`已用 ${status?.server?.disk?.used_percent ?? 0}%`}
                  online={Boolean(status?.server?.disk)}
                  styles={styles}
                />
              </div>
            </section>

            <section className={`${styles.bg} border ${styles.border} rounded-lg p-6`}>
              <h2 className={`text-xl font-bold ${styles.text} mb-5`}>运行信息</h2>
              <div className={`grid grid-cols-1 md:grid-cols-3 gap-4 text-sm ${styles.text}`}>
                <InfoBlock label="负载 1 分钟" value={loadAverage[0] ?? "未知"} styles={styles} />
                <InfoBlock label="负载 5 分钟" value={loadAverage[1] ?? "未知"} styles={styles} />
                <InfoBlock label="负载 15 分钟" value={loadAverage[2] ?? "未知"} styles={styles} />
              </div>
              <p className={`${styles.textMuted} mt-5 text-sm`}>
                检查时间：{formatDate(status?.server?.checked_at)}
              </p>
            </section>
          </div>
        )}
      </div>
    </div>
  );
};

const StatusTile = ({ icon, label, value, detail, online, styles }) => (
  <div className={`border ${styles.border} rounded-lg p-4`}>
    <div className="flex items-center justify-between gap-3 mb-4">
      <div className={`flex items-center gap-2 ${styles.text}`}>
        {icon}
        <span className="font-semibold">{label}</span>
      </div>
      {online ? <CheckCircle2 size={18} className="text-emerald-500" /> : <XCircle size={18} className="text-red-500" />}
    </div>
    <p className={`text-lg font-bold ${styles.text}`}>{value}</p>
    <p className={`text-sm ${styles.textMuted} mt-1`}>{detail}</p>
  </div>
);

const InfoBlock = ({ label, value, styles }) => (
  <div className={`border ${styles.border} rounded-lg p-4`}>
    <p className={styles.textMuted}>{label}</p>
    <p className={`text-2xl font-bold ${styles.text} mt-2`}>{value}</p>
  </div>
);

export default AgentConsolePage;
