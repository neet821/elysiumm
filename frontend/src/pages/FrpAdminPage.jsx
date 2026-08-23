import { useEffect, useState } from "react";
import { FileText, Globe2, Play, RefreshCw, RotateCw, Save, Square, Undo2 } from "lucide-react";
import apiClient from "../utils/request";
import { API_ENDPOINTS } from "../config";

const FrpAdminPage = ({ styles, isDark }) => {
  const [status, setStatus] = useState(null);
  const [config, setConfig] = useState("");
  const [logs, setLogs] = useState("");
  const [backups, setBackups] = useState([]);
  const [operations, setOperations] = useState([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const fetchAll = async () => {
    setLoading(true);
    setError("");
    try {
      const [statusRes, configRes, logsRes, backupsRes, operationsRes] = await Promise.all([
        apiClient.get(API_ENDPOINTS.ADMIN_FRP_STATUS),
        apiClient.get(API_ENDPOINTS.ADMIN_FRP_CONFIG),
        apiClient.get(API_ENDPOINTS.ADMIN_FRP_LOGS, { params: { lines: 120 } }),
        apiClient.get(API_ENDPOINTS.ADMIN_FRP_BACKUPS),
        apiClient.get(API_ENDPOINTS.ADMIN_FRP_OPERATIONS),
      ]);
      setStatus(statusRes.data);
      setConfig(configRes.data.content || "");
      setLogs(logsRes.data.content || "");
      setBackups(backupsRes.data || []);
      setOperations(operationsRes.data || []);
    } catch (fetchError) {
      console.error("加载 frp 管理信息失败:", fetchError);
      setError("frp 管理信息加载失败");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchAll();
  }, []);

  const runAction = async (label, endpoint) => {
    if (!window.confirm(`确定要${label} frp 服务吗？`)) return;
    setBusy(true);
    try {
      await apiClient.post(endpoint);
      await fetchAll();
    } catch (actionError) {
      console.error(`${label} frp 失败:`, actionError);
      alert(`${label}失败，请查看日志`);
    } finally {
      setBusy(false);
    }
  };

  const saveConfig = async () => {
    setBusy(true);
    try {
      await apiClient.post(API_ENDPOINTS.ADMIN_FRP_CONFIG, { content: config });
      await fetchAll();
    } catch (saveError) {
      console.error("保存 frp 配置失败:", saveError);
      alert("保存失败，配置未覆盖；请检查 TOML 格式");
    } finally {
      setBusy(false);
    }
  };

  const createBackup = async () => {
    setBusy(true);
    try {
      await apiClient.post(API_ENDPOINTS.ADMIN_FRP_BACKUPS);
      await fetchAll();
    } catch (backupError) {
      console.error("备份 frp 配置失败:", backupError);
      alert("备份失败");
    } finally {
      setBusy(false);
    }
  };

  const restoreBackup = async (backup) => {
    if (!window.confirm(`确定恢复配置 ${backup.name} 吗？当前配置会先自动备份。`)) return;
    setBusy(true);
    try {
      await apiClient.post(API_ENDPOINTS.ADMIN_FRP_RESTORE, {
        backup_name: backup.name,
      });
      await fetchAll();
    } catch (restoreError) {
      console.error("恢复 frp 配置失败:", restoreError);
      alert("恢复失败");
    } finally {
      setBusy(false);
    }
  };

  const activeState = status?.service?.active || "unknown";
  const summary = status?.config_summary || {};
  const dashboardProxies = status?.dashboard_proxies?.proxies || [];
  const recentProxies = status?.recent_proxies || [];

  return (
    <div className={`admin-legacy-panel ${styles.bgSecondary} transition-colors duration-700`}>
      <div className="max-w-7xl mx-auto">
        <div className="flex flex-col md:flex-row md:items-end justify-between gap-5 mb-8">
          <div>
            <div className="flex items-center gap-3 mb-2">
              <Globe2 size={24} className={styles.accentClass} />
              <h1 className={`text-3xl font-serif font-semibold ${styles.text}`}>frp 穿透管理</h1>
            </div>
            <p className={`text-sm ${styles.textMuted}`}>管理 frps 服务、配置、日志和配置备份。</p>
          </div>
          <div className="flex flex-wrap gap-2">
            <button
              onClick={fetchAll}
              disabled={busy || loading}
              className={`h-10 w-10 inline-flex items-center justify-center rounded-lg border ${styles.border} disabled:opacity-50`}
              title="刷新"
            >
              <RefreshCw size={18} className={`${styles.textMuted} ${loading ? "animate-spin" : ""}`} />
            </button>
            <button
              onClick={() => runAction("启动", API_ENDPOINTS.ADMIN_FRP_START)}
              disabled={busy}
              className={`inline-flex items-center gap-2 px-3 py-2 rounded-lg border ${styles.border} ${styles.text} disabled:opacity-50`}
            >
              <Play size={16} />
              启动
            </button>
            <button
              onClick={() => runAction("停止", API_ENDPOINTS.ADMIN_FRP_STOP)}
              disabled={busy}
              className={`inline-flex items-center gap-2 px-3 py-2 rounded-lg border ${styles.border} ${styles.text} disabled:opacity-50`}
            >
              <Square size={16} />
              停止
            </button>
            <button
              onClick={() => runAction("重启", API_ENDPOINTS.ADMIN_FRP_RESTART)}
              disabled={busy}
              className={`inline-flex items-center gap-2 px-3 py-2 rounded-lg text-white disabled:opacity-50 ${
                isDark ? "bg-blue-500 hover:bg-blue-400" : "bg-[#2A5C8D] hover:bg-[#1f4d78]"
              }`}
            >
              <RotateCw size={16} />
              重启
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

        <div className="grid grid-cols-1 xl:grid-cols-[1fr_420px] gap-6">
          <div className="space-y-6">
            <section className={`${styles.bg} rounded-xl border ${styles.border} p-5 shadow-sm`}>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
                <div>
                  <p className={`text-xs ${styles.textMuted}`}>服务状态</p>
                  <p className={`text-lg font-semibold ${styles.text}`}>{activeState}</p>
                </div>
                <div>
                  <p className={`text-xs ${styles.textMuted}`}>控制端口</p>
                  <p className={`text-lg font-semibold ${styles.text}`}>{summary.bind_port || "-"}</p>
                </div>
                <div>
                  <p className={`text-xs ${styles.textMuted}`}>控制面板</p>
                  <p className={`text-lg font-semibold ${styles.text}`}>{summary.dashboard_port || "-"}</p>
                </div>
                <div>
                  <p className={`text-xs ${styles.textMuted}`}>近期代理</p>
                  <p className={`text-lg font-semibold ${styles.text}`}>
                    {dashboardProxies.length || recentProxies.length}
                  </p>
                </div>
              </div>
              <div className={`mt-4 text-xs ${styles.textMuted}`}>配置：已通过受控接口加载</div>
            </section>

            <section className={`${styles.bg} rounded-xl border ${styles.border} p-5 shadow-sm`}>
              <div className="flex items-center justify-between gap-3 mb-4">
                <div className="flex items-center gap-2">
                  <FileText size={18} className={styles.accentClass} />
                  <h2 className={`font-semibold ${styles.text}`}>frps.toml</h2>
                </div>
                <div className="flex gap-2">
                  <button
                    onClick={createBackup}
                    disabled={busy}
                    className={`inline-flex items-center gap-2 px-3 py-2 rounded-lg border ${styles.border} ${styles.text} disabled:opacity-50`}
                  >
                    <FileText size={15} />
                    备份配置
                  </button>
                  <button
                    onClick={saveConfig}
                    disabled={busy}
                    className={`inline-flex items-center gap-2 px-3 py-2 rounded-lg text-white disabled:opacity-50 ${
                      isDark ? "bg-blue-500 hover:bg-blue-400" : "bg-[#2A5C8D] hover:bg-[#1f4d78]"
                    }`}
                  >
                    <Save size={15} />
                    保存
                  </button>
                </div>
              </div>
              <textarea
                value={config}
                onChange={(event) => setConfig(event.target.value)}
                spellCheck={false}
                className={`w-full min-h-[420px] font-mono text-sm rounded-lg border ${styles.border} ${styles.bgSecondary} ${styles.text} p-4 outline-none`}
              />
            </section>
          </div>

          <div className="space-y-6">
            <section className={`${styles.bg} rounded-xl border ${styles.border} p-5 shadow-sm`}>
              <h2 className={`font-semibold ${styles.text} mb-3`}>代理列表</h2>
              {dashboardProxies.length > 0 ? (
                <div className="space-y-2 mb-6">
                  {dashboardProxies.slice(0, 10).map((proxy, index) => (
                    <div key={`${proxy.name}-${index}`} className={`rounded-lg border ${styles.border} ${styles.bgSecondary} p-3`}>
                      <p className={`text-sm font-medium ${styles.text}`}>{proxy.name || proxy.proxy_name}</p>
                      <p className={`text-xs ${styles.textMuted}`}>{proxy.type} · {proxy.status || proxy.cur_conns || "active"}</p>
                    </div>
                  ))}
                </div>
              ) : recentProxies.length > 0 ? (
                <div className="space-y-2 mb-6">
                  {recentProxies.slice(0, 10).map((proxy) => (
                    <div key={proxy} className={`rounded-lg border ${styles.border} ${styles.bgSecondary} p-3`}>
                      <p className={`text-sm font-medium ${styles.text}`}>{proxy}</p>
                      <p className={`text-xs ${styles.textMuted}`}>从日志识别</p>
                    </div>
                  ))}
                </div>
              ) : (
                <p className={`text-sm ${styles.textMuted} mb-6`}>暂无代理信息</p>
              )}

              <h2 className={`font-semibold ${styles.text} mb-3`}>配置备份</h2>
              {backups.length === 0 ? (
                <p className={`text-sm ${styles.textMuted}`}>暂无配置备份</p>
              ) : (
                <div className="space-y-2">
                  {backups.map((backup) => (
                    <div key={backup.name} className={`rounded-lg border ${styles.border} ${styles.bgSecondary} p-3`}>
                      <p className={`text-sm font-medium ${styles.text} truncate`}>{backup.name}</p>
                      <p className={`text-xs ${styles.textMuted}`}>{backup.file_size} B</p>
                      <button
                        onClick={() => restoreBackup(backup)}
                        disabled={busy}
                        className={`mt-2 inline-flex items-center gap-1 text-sm ${styles.accentClass} disabled:opacity-50`}
                      >
                        <Undo2 size={14} />
                        恢复
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </section>

            <section className={`${styles.bg} rounded-xl border ${styles.border} p-5 shadow-sm`}>
              <h2 className={`font-semibold ${styles.text} mb-3`}>最近日志</h2>
              <pre className={`max-h-[320px] overflow-auto whitespace-pre-wrap rounded-lg ${styles.bgSecondary} ${styles.textMuted} p-3 text-xs`}>
                {logs || "暂无日志"}
              </pre>
            </section>

            <section className={`${styles.bg} rounded-xl border ${styles.border} p-5 shadow-sm`}>
              <h2 className={`font-semibold ${styles.text} mb-3`}>操作记录</h2>
              {operations.length === 0 ? (
                <p className={`text-sm ${styles.textMuted}`}>暂无操作记录</p>
              ) : (
                <div className="space-y-2">
                  {operations.slice(0, 8).map((operation) => (
                    <div key={operation.id} className={`text-sm border-b ${styles.border} pb-2`}>
                      <p className={styles.text}>{operation.action} · {operation.status}</p>
                      {operation.message && (
                        <p className={`text-xs ${styles.textMuted} truncate`}>{operation.message}</p>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </section>
          </div>
        </div>
      </div>
    </div>
  );
};

export default FrpAdminPage;
