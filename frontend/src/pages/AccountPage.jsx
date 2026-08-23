import { useState, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../contexts/AuthContext";
import {
  User,
  Shield,
  Camera,
  LogOut,
  Lock,
  Trash2,
} from "lucide-react";
import apiClient from "../utils/request";
import { API_ENDPOINTS } from "../config";

const AccountPage = ({ styles, isDark }) => {
  const { user, isAdmin, logout, refreshUser } = useAuth();
  const navigate = useNavigate();
  const fileInputRef = useRef(null);

  const [showPasswordModal, setShowPasswordModal] = useState(false);
  const [oldPassword, setOldPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  // 用户名修改
  const [newUsername, setNewUsername] = useState(user?.username || "");
  const [isUpdatingUsername, setIsUpdatingUsername] = useState(false);

  // 头像上传状态
  const [isUploadingAvatar, setIsUploadingAvatar] = useState(false);
  const [avatarError, setAvatarError] = useState("");

  if (!user) {
    navigate("/login");
    return null;
  }

  // 获取头像URL
  const getAvatarUrl = () => {
    if (user.avatar) {
      const apiBase = import.meta.env.VITE_API_BASE_URL || window.location.origin;
      return `${apiBase}${user.avatar}`;
    }
    return null;
  };

  const handleLogout = () => {
    logout();
    navigate("/login");
  };

  const handleChangePassword = async (e) => {
    e.preventDefault();
    setError("");
    setSuccess("");

    if (newPassword !== confirmPassword) {
      setError("两次输入的新密码不一致");
      return;
    }

    if (newPassword.length < 6) {
      setError("新密码长度至少为6个字符");
      return;
    }

    try {
      await apiClient.put(API_ENDPOINTS.UPDATE_PASSWORD, {
        old_password: oldPassword,
        new_password: newPassword,
      });
      setSuccess("密码修改成功");
      setOldPassword("");
      setNewPassword("");
      setConfirmPassword("");
      setTimeout(() => {
        setShowPasswordModal(false);
        setSuccess("");
      }, 2000);
    } catch (error) {
      setError(error.response?.data?.detail || "修改密码失败");
    }
  };

  // 🆕 头像上传
  const handleAvatarChange = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;

    // 验证文件类型
    const allowedTypes = ['image/jpeg', 'image/jpg', 'image/png', 'image/gif', 'image/webp'];
    if (!allowedTypes.includes(file.type)) {
      setAvatarError('仅支持 JPG、PNG、GIF、WebP 格式');
      return;
    }

    // 验证文件大小 (5MB)
    if (file.size > 5 * 1024 * 1024) {
      setAvatarError('文件大小不能超过 5MB');
      return;
    }

    setIsUploadingAvatar(true);
    setAvatarError("");

    try {
      const formData = new FormData();
      formData.append('file', file);

      await apiClient.post('/api/users/me/avatar', formData);

      // 刷新用户信息
      await refreshUser();
      setSuccess('头像上传成功！');
      setTimeout(() => setSuccess(''), 2000);
    } catch (error) {
      setAvatarError(error.response?.data?.detail || '头像上传失败');
    } finally {
      setIsUploadingAvatar(false);
    }
  };

  // 🆕 删除头像
  const handleDeleteAvatar = async () => {
    if (!confirm('确定要删除头像吗？')) return;

    try {
      await apiClient.delete('/api/users/me/avatar');
      await refreshUser();
      setSuccess('头像已删除');
      setTimeout(() => setSuccess(''), 2000);
    } catch (error) {
      setAvatarError(error.response?.data?.detail || '删除头像失败');
    }
  };

  return (
    <div className={`pt-32 pb-20 min-h-screen ${styles.bg} transition-colors duration-1000 animate-fade-in`}>
      <div className="max-w-5xl mx-auto px-6">
        <div className="grid grid-cols-1 md:grid-cols-12 gap-8">
          {/* 左侧：用户信息卡片 */}
          <div className="md:col-span-4 lg:col-span-3">
            <div
              className={`${styles.bg} border ${styles.border} rounded-2xl p-6 shadow-sm text-center sticky top-32`}
            >
              {/* 🆕 头像区域 */}
              <div className="relative inline-block group">
                <div
                  className={`w-24 h-24 mx-auto rounded-full overflow-hidden border-4 ${
                    styles.bg
                  } shadow-md ${
                    getAvatarUrl()
                      ? ''
                      : `bg-gradient-to-br ${
                          isDark
                            ? "from-orange-600 to-orange-400"
                            : "from-blue-600 to-blue-400"
                        }`
                  }`}
                >
                  {getAvatarUrl() ? (
                    <img
                      src={getAvatarUrl()}
                      alt="Avatar"
                      className="w-full h-full object-cover"
                    />
                  ) : (
                    <div className="w-full h-full flex items-center justify-center text-white text-3xl font-bold">
                      {user.username.charAt(0).toUpperCase()}
                    </div>
                  )}
                </div>

                {/* 🆕 头像操作按钮 */}
                <div className="absolute inset-0 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity">
                  <div className="flex gap-2">
                    <button
                      onClick={() => fileInputRef.current?.click()}
                      disabled={isUploadingAvatar}
                      className={`p-2 rounded-full ${
                        isDark
                          ? 'bg-orange-600 hover:bg-orange-500'
                          : 'bg-[#189BCC] hover:bg-[#1589b5]'
                      } text-white shadow-lg transition-colors disabled:opacity-50`}
                      title="上传头像"
                    >
                      {isUploadingAvatar ? (
                        <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                      ) : (
                        <Camera size={16} />
                      )}
                    </button>
                    {user.avatar && (
                      <button
                        onClick={handleDeleteAvatar}
                        className="p-2 rounded-full bg-red-600 hover:bg-red-500 text-white shadow-lg transition-colors"
                        title="删除头像"
                      >
                        <Trash2 size={16} />
                      </button>
                    )}
                  </div>
                </div>

                <input
                  ref={fileInputRef}
                  type="file"
                  accept="image/jpeg,image/jpg,image/png,image/gif,image/webp"
                  onChange={handleAvatarChange}
                  className="hidden"
                />
              </div>

              {/* 头像错误提示 */}
              {avatarError && (
                <p className="text-red-500 text-xs mt-2">{avatarError}</p>
              )}

              <h2 className={`text-xl font-bold ${styles.text} mt-4`}>
                {user.username}
              </h2>
              <p className={`text-sm ${styles.textMuted} mt-1`}>{user.email}</p>

              <div
                className={`inline-block px-3 py-1 rounded-full text-xs font-bold mt-3 border ${
                  isAdmin
                    ? isDark
                      ? "border-orange-500 text-orange-500"
                      : "border-[#189BCC] text-[#189BCC]"
                    : "border-gray-300 text-gray-400"
                }`}
              >
                {isAdmin ? "ADMIN" : "USER"}
              </div>

              <button
                onClick={handleLogout}
                className={`mt-6 w-full flex items-center justify-center gap-2 px-4 py-2 rounded-lg text-sm transition-colors ${
                  isDark
                    ? "bg-gray-800 hover:bg-gray-700 text-gray-300"
                    : "bg-gray-100 hover:bg-gray-200 text-gray-700"
                }`}
              >
                <LogOut size={16} />
                退出登录
              </button>
            </div>
          </div>

          {/* 右侧：功能区域 */}
          <div className="md:col-span-8 lg:col-span-9 space-y-8">
            {/* 基础信息 */}
            <div
              className={`${styles.bg} border ${styles.border} rounded-xl p-8`}
            >
              <h3
                className={`text-lg font-bold ${styles.text} mb-6 flex items-center gap-2`}
              >
                <User size={18} className={styles.accentClass} /> 个人信息
              </h3>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div>
                  <label className={`block text-xs font-bold ${styles.textMuted} uppercase mb-2`}>
                    用户名
                  </label>
                  <div className="flex gap-2">
                    <input
                      type="text"
                      value={newUsername}
                      onChange={(e) => setNewUsername(e.target.value)}
                      className={`flex-1 ${styles.bgSecondary} border-none rounded p-3 text-sm ${styles.text}`}
                    />
                    <button
                      onClick={async () => {
                        setError("");
                        setSuccess("");
                        const name = newUsername.trim();
                        if (name.length < 3) { setError("用户名长度至少为3个字符"); return; }
                        if (name === user.username) { setSuccess("用户名未变化"); return; }
                        setIsUpdatingUsername(true);
                        try {
                          const res = await apiClient.put('/api/users/me/username', { new_username: name });

                          // 🆕 如果返回了新 token，更新它
                          if (res.data.access_token) {
                            localStorage.setItem("token", res.data.access_token);
                          }

                          await refreshUser();
                          setSuccess(res.data?.message || '用户名修改成功');
                        } catch (err) {
                          setError(err.response?.data?.detail || '修改用户名失败');
                        } finally {
                          setIsUpdatingUsername(false);
                        }
                      }}
                      disabled={isUpdatingUsername}
                      className={`px-3 py-2 rounded text-sm ${isDark ? 'bg-orange-600 hover:bg-orange-500 text-white' : 'bg-[#189BCC] hover:bg-[#1589b5] text-white'} disabled:opacity-50`}
                    >
                      {isUpdatingUsername ? '更新中…' : '保存'}
                    </button>
                  </div>
                </div>
                <div>
                  <label
                    className={`block text-xs font-bold ${styles.textMuted} uppercase mb-2`}
                  >
                    邮箱
                  </label>
                  <input
                    type="email"
                    value={user.email}
                    disabled
                    className={`w-full ${styles.bgSecondary} border-none rounded p-3 text-sm ${styles.text} opacity-50 cursor-not-allowed`}
                  />
                </div>
              </div>

              <div className="mt-8 pt-8 border-t border-gray-100 dark:border-gray-800">
                <h4 className={`text-sm font-bold ${styles.text} mb-4`}>
                  安全设置
                </h4>
                <button
                  onClick={() => setShowPasswordModal(true)}
                  className={`flex items-center gap-2 px-4 py-2 rounded border ${styles.border} ${styles.textMuted} text-sm hover:${styles.text}`}
                >
                  <Lock size={16} />
                  修改密码
                </button>
              </div>
            </div>

            {/* 管理员功能 */}
            {isAdmin && (
              <div
                className={`animate-fade-in ${styles.bg} border ${
                  isDark ? "border-orange-900/50" : "border-blue-100"
                } rounded-xl p-8 relative overflow-hidden`}
              >
                <div
                  className={`absolute top-0 right-0 w-32 h-32 rounded-bl-full opacity-10 ${
                    isDark ? "bg-orange-500" : "bg-[#189BCC]"
                  }`}
                ></div>

                <h3
                  className={`text-lg font-bold ${styles.text} mb-6 flex items-center gap-2 relative z-10`}
                >
                  <Shield size={18} className={styles.accentClass} />{" "}
                  管理员控制台
                </h3>

                <p className={`${styles.textMuted} mb-5 relative z-10`}>
                  用户、内容、房间、文件、服务、备份和安全证据统一在一个受保护的工作区中。
                </p>
                <button
                  onClick={() => navigate("/account/admin")}
                  className={`flex items-center justify-center gap-2 px-5 py-3 rounded ${styles.bgSecondary} ${styles.text} text-sm transition-all hover:-translate-y-1 relative z-10`}
                >
                  <Shield size={16} /> 打开统一管理员控制台
                </button>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* 修改密码模态框 */}
      {showPasswordModal && (
        <div className="fixed inset-0 bg-black/50 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div
            className={`${styles.bg} rounded-xl p-8 max-w-md w-full shadow-2xl`}
          >
            <h3 className={`text-xl font-bold ${styles.text} mb-6`}>
              修改密码
            </h3>

            {error && (
              <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-lg">
                <p className="text-red-600 text-sm">{error}</p>
              </div>
            )}

            {success && (
              <div className="mb-4 p-3 bg-green-50 border border-green-200 rounded-lg">
                <p className="text-green-600 text-sm">{success}</p>
              </div>
            )}

            <form onSubmit={handleChangePassword} className="space-y-4">
              <div>
                <label
                  className={`block text-sm font-medium ${styles.text} mb-2`}
                >
                  旧密码
                </label>
                <input
                  type="password"
                  value={oldPassword}
                  onChange={(e) => setOldPassword(e.target.value)}
                  className={`w-full px-4 py-2 border ${styles.border} rounded ${styles.bgSecondary} ${styles.text}`}
                  required
                />
              </div>
              <div>
                <label
                  className={`block text-sm font-medium ${styles.text} mb-2`}
                >
                  新密码
                </label>
                <input
                  type="password"
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                  className={`w-full px-4 py-2 border ${styles.border} rounded ${styles.bgSecondary} ${styles.text}`}
                  required
                />
              </div>
              <div>
                <label
                  className={`block text-sm font-medium ${styles.text} mb-2`}
                >
                  确认新密码
                </label>
                <input
                  type="password"
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  className={`w-full px-4 py-2 border ${styles.border} rounded ${styles.bgSecondary} ${styles.text}`}
                  required
                />
              </div>
              <div className="flex gap-3 mt-6">
                <button
                  type="submit"
                  className={`flex-1 py-2 text-white rounded transition-colors ${
                    isDark
                      ? "bg-orange-600 hover:bg-orange-500"
                      : "bg-[#189BCC] hover:bg-[#1589b5]"
                  }`}
                >
                  确认修改
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setShowPasswordModal(false);
                    setError("");
                    setSuccess("");
                  }}
                  className={`flex-1 py-2 border ${styles.border} rounded ${styles.textMuted} hover:${styles.text}`}
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

export default AccountPage;
