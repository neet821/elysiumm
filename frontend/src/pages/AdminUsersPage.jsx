import { useState, useEffect } from "react";
import { Search, Shield, Ban, Check, Trash2 } from "lucide-react";
import apiClient from "../utils/request";
import { API_ENDPOINTS } from "../config";

const AdminUsersPage = ({ styles, isDark }) => {
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState("");

  useEffect(() => {
    fetchUsers();
  }, []);

  const fetchUsers = async () => {
    try {
      const response = await apiClient.get(API_ENDPOINTS.ADMIN_USERS);
      setUsers(response.data || []);
    } catch (error) {
      console.error("获取用户列表失败:", error);
    } finally {
      setLoading(false);
    }
  };

  const handleToggleStatus = async (userId, currentStatus) => {
    try {
      await apiClient.put(API_ENDPOINTS.ADMIN_USER_DETAIL(userId), {
        is_active: !currentStatus,
      });
      fetchUsers();
    } catch (error) {
      console.error("更新用户状态失败:", error);
      alert("操作失败，请重试");
    }
  };

  const handleToggleRole = async (userId, currentRole) => {
    if (!window.confirm("确定要修改该用户的角色吗？")) return;

    try {
      await apiClient.put(API_ENDPOINTS.ADMIN_USER_DETAIL(userId), {
        role: currentRole === "admin" ? "user" : "admin",
      });
      fetchUsers();
    } catch (error) {
      console.error("更新用户角色失败:", error);
      alert("操作失败，请重试");
    }
  };

  const handleDeleteUser = async (userId) => {
    if (!window.confirm("确定要删除该用户吗？此操作不可恢复！")) return;

    try {
      await apiClient.delete(API_ENDPOINTS.ADMIN_USER_DETAIL(userId));
      fetchUsers();
    } catch (error) {
      console.error("删除用户失败:", error);
      alert(error.response?.data?.detail || "删除失败，请重试");
    }
  };

  const filteredUsers = users.filter(
    (user) =>
      user.username.toLowerCase().includes(searchTerm.toLowerCase()) ||
      user.email.toLowerCase().includes(searchTerm.toLowerCase())
  );

  return (
    <div className={`admin-legacy-panel ${styles.bgSecondary} transition-colors duration-1000 animate-fade-in`}>
      <div className="max-w-6xl mx-auto">
        <div
          className={`${styles.bg} rounded-xl shadow-sm border ${styles.border} p-8`}
        >
          <h1
            className={`text-3xl font-serif font-bold ${styles.text} mb-8 flex items-center gap-3`}
          >
            <Shield size={28} className={styles.accentClass} />
            用户管理
          </h1>

          <div className="mb-6">
            <div className="relative">
              <Search
                size={20}
                className={`absolute left-4 top-1/2 -translate-y-1/2 ${styles.textMuted}`}
              />
              <input
                type="text"
                placeholder="搜索用户..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                className={`w-full pl-12 pr-4 py-3 border ${
                  styles.border
                } rounded-lg ${styles.bgSecondary} ${
                  styles.text
                } focus:outline-none focus:ring-2 ${
                  isDark ? "focus:ring-orange-500" : "focus:ring-[#189BCC]"
                }`}
              />
            </div>
          </div>

          {loading ? (
            <div className="flex justify-center py-12">
              <div className="animate-spin w-12 h-12 border-4 border-gray-300 border-t-blue-500 rounded-full"></div>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className={`border-b ${styles.border}`}>
                    <th
                      className={`text-left py-4 px-4 text-sm font-bold ${styles.text}`}
                    >
                      用户名
                    </th>
                    <th
                      className={`text-left py-4 px-4 text-sm font-bold ${styles.text}`}
                    >
                      邮箱
                    </th>
                    <th
                      className={`text-left py-4 px-4 text-sm font-bold ${styles.text}`}
                    >
                      角色
                    </th>
                    <th
                      className={`text-left py-4 px-4 text-sm font-bold ${styles.text}`}
                    >
                      状态
                    </th>
                    <th
                      className={`text-left py-4 px-4 text-sm font-bold ${styles.text}`}
                    >
                      注册时间
                    </th>
                    <th
                      className={`text-right py-4 px-4 text-sm font-bold ${styles.text}`}
                    >
                      操作
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {filteredUsers.map((user) => (
                    <tr
                      key={user.id}
                      className={`border-b ${styles.border} hover:${styles.bgSecondary} transition-colors`}
                    >
                      <td className={`py-4 px-4 ${styles.text}`}>
                        {user.username}
                      </td>
                      <td className={`py-4 px-4 ${styles.textMuted} text-sm`}>
                        {user.email}
                      </td>
                      <td className="py-4 px-4">
                        <button
                          onClick={() => handleToggleRole(user.id, user.role)}
                          className={`px-3 py-1 rounded-full text-xs font-bold border transition-colors ${
                            user.role === "admin"
                              ? isDark
                                ? "border-orange-500 text-orange-500 hover:bg-orange-500 hover:text-white"
                                : "border-[#189BCC] text-[#189BCC] hover:bg-[#189BCC] hover:text-white"
                              : "border-gray-300 text-gray-500 hover:bg-gray-300 hover:text-white"
                          }`}
                        >
                          {user.role === "admin" ? "ADMIN" : "USER"}
                        </button>
                      </td>
                      <td className="py-4 px-4">
                        <button
                          onClick={() =>
                            handleToggleStatus(user.id, user.is_active)
                          }
                          className={`flex items-center gap-1 px-3 py-1 rounded-full text-xs font-medium ${
                            user.is_active
                              ? "bg-green-100 text-green-700 hover:bg-green-200"
                              : "bg-red-100 text-red-700 hover:bg-red-200"
                          }`}
                        >
                          {user.is_active ? (
                            <Check size={12} />
                          ) : (
                            <Ban size={12} />
                          )}
                          {user.is_active ? "正常" : "禁用"}
                        </button>
                      </td>
                      <td className={`py-4 px-4 ${styles.textMuted} text-sm`}>
                        {new Date(user.created_at).toLocaleDateString("zh-CN")}
                      </td>
                      <td className="py-4 px-4 text-right">
                        <button
                          onClick={() => handleDeleteUser(user.id)}
                          className="p-2 text-red-500 hover:bg-red-50 rounded transition-colors"
                          title="删除用户"
                        >
                          <Trash2 size={16} />
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {!loading && filteredUsers.length === 0 && (
            <div className="text-center py-12">
              <p className={`${styles.textMuted}`}>没有找到用户</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default AdminUsersPage;
