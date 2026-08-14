import React, { useState, useEffect } from "react";
import { X, Send, Check, AlertCircle, Clock, Upload, Link as LinkIcon, Trash2, Star, User, Lock, EyeOff, MessageSquare } from "lucide-react";
import apiClient from "../utils/request";
import { API_ENDPOINTS } from "../config";
import { useAuth } from "../contexts/AuthContext";

const WishlistModal = ({ isOpen, onClose, isDark }) => {
  const { user } = useAuth();

  // Wishlist State
  const [requests, setRequests] = useState([]);
  const [newRequest, setNewRequest] = useState({
    title: "",
    content: "",
    is_anonymous: false,
    is_private: false
  });
  const [loading, setLoading] = useState(false);
  const [replyingTo, setReplyingTo] = useState(null);
  const [replyContent, setReplyContent] = useState("");

  // Admin State
  const [editingId, setEditingId] = useState(null);
  const [editForm, setEditForm] = useState({ status: "", reply_content: "", external_link: "" });

  useEffect(() => {
    if (isOpen) {
      fetchRequests();
    }
  }, [isOpen]);

  const fetchRequests = async () => {
    try {
      setLoading(true);
      const res = await apiClient.get(API_ENDPOINTS.RESOURCE_REQUESTS);
      setRequests(res.data);
    } catch (error) {
      console.error("Failed to fetch requests", error);
    } finally {
      setLoading(false);
    }
  };

  const handleCreateRequest = async (e) => {
    e.preventDefault();
    if (!newRequest.title.trim() || !newRequest.content.trim()) return;
    try {
      await apiClient.post(API_ENDPOINTS.RESOURCE_REQUESTS, newRequest);
      setNewRequest({ title: "", content: "", is_anonymous: false, is_private: false });
      fetchRequests();
    } catch (error) {
      console.error("Failed to create request", error);
      alert("提交失败");
    }
  };

  const handleDeleteRequest = async (id) => {
      if (!window.confirm("确定要删除这个请求吗？")) return;
      try {
          await apiClient.delete(API_ENDPOINTS.RESOURCE_REQUEST_DETAIL(id));
          fetchRequests();
      } catch (error) {
          console.error("Failed to delete request", error);
      }
  };

  const handleReply = async (requestId) => {
      if (!replyContent.trim()) return;
      try {
          await apiClient.post(`${API_ENDPOINTS.RESOURCE_REQUESTS}/${requestId}/replies`, {
              content: replyContent
          });
          setReplyContent("");
          setReplyingTo(null);
          fetchRequests();
      } catch (error) {
          console.error("Failed to reply", error);
          alert("回复失败");
      }
  };

  const handleAdminUpdate = async (id) => {
      try {
          await apiClient.put(API_ENDPOINTS.RESOURCE_REQUEST_DETAIL(id), editForm);
          setEditingId(null);
          fetchRequests();
      } catch (error) {
          console.error("Failed to update request", error);
          alert("更新失败");
      }
  };

  const startEdit = (req) => {
      setEditingId(req.id);
      setEditForm({
          status: req.status,
          reply_content: req.reply_content || "",
          external_link: req.external_link || ""
      });
  };

  if (!isOpen) return null;

  const styles = isDark
    ? {
        bg: "bg-[#1a1a1a]",
        text: "text-gray-200",
        border: "border-gray-700",
        input: "bg-[#2a2a2a] border-gray-600 text-white",
        secondary: "bg-[#2a2a2a]",
        subtle: "text-gray-400"
      }
    : {
        bg: "bg-white",
        text: "text-gray-800",
        border: "border-gray-200",
        input: "bg-gray-50 border-gray-200 text-gray-900",
        secondary: "bg-gray-50",
        subtle: "text-gray-500"
      };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm animate-fade-in">
      <div
        className={`${styles.bg} ${styles.text} w-full max-w-3xl rounded-xl shadow-2xl overflow-hidden flex flex-col max-h-[85vh] animate-scale-in`}
      >
        {/* Header */}
        <div className={`p-4 border-b ${styles.border} flex justify-between items-center`}>
          <div className="flex items-center gap-2">
            <Star className={`w-5 h-5 ${isDark ? "text-yellow-500" : "text-yellow-600"}`} />
            <h3 className="font-serif text-xl">许愿池</h3>
          </div>
          <button
            onClick={onClose}
            className={`p-1 rounded-full hover:bg-gray-200 dark:hover:bg-gray-700 transition-colors`}
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-4 space-y-6">
            {/* Input Area */}
            <div className={`p-4 rounded-lg ${styles.secondary}`}>
                <h4 className="text-sm font-medium mb-1 flex items-center gap-2">
                    <Send className="w-4 h-4" />
                    许个愿吧
                </h4>
                <p className={`text-xs mb-3 opacity-70 ${styles.subtle}`}>
                    想要什么资源？告诉站长，我会尽力帮你寻找并上传。
                </p>
                <form onSubmit={handleCreateRequest} className="space-y-3">
                    <input
                        type="text"
                        placeholder="标题 (例如: 想看某部电影)"
                        value={newRequest.title}
                        onChange={(e) => setNewRequest({ ...newRequest, title: e.target.value })}
                        className={`w-full px-3 py-2 rounded-md border ${styles.input} focus:outline-none focus:ring-2 focus:ring-blue-500`}
                    />
                    <textarea
                        placeholder="详细描述..."
                        value={newRequest.content}
                        onChange={(e) => setNewRequest({ ...newRequest, content: e.target.value })}
                        className={`w-full px-3 py-2 rounded-md border ${styles.input} focus:outline-none focus:ring-2 focus:ring-blue-500 min-h-[80px]`}
                    />

                    <div className="flex items-center justify-between">
                        <div className="flex gap-4">
                            <label className="flex items-center gap-2 text-sm cursor-pointer select-none">
                                <input
                                    type="checkbox"
                                    checked={newRequest.is_anonymous}
                                    onChange={(e) => setNewRequest({...newRequest, is_anonymous: e.target.checked})}
                                    className="rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                                />
                                <span className="flex items-center gap-1">
                                    <EyeOff size={14} /> 匿名
                                </span>
                            </label>
                            <label className="flex items-center gap-2 text-sm cursor-pointer select-none">
                                <input
                                    type="checkbox"
                                    checked={newRequest.is_private}
                                    onChange={(e) => setNewRequest({...newRequest, is_private: e.target.checked})}
                                    className="rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                                />
                                <span className="flex items-center gap-1">
                                    <Lock size={14} /> 仅站长可见
                                </span>
                            </label>
                        </div>
                        <button
                            type="submit"
                            disabled={!newRequest.title.trim() || !newRequest.content.trim()}
                            className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 disabled:opacity-50 disabled:cursor-not-allowed transition-colors text-sm"
                        >
                            提交愿望
                        </button>
                    </div>
                </form>
            </div>

            {/* List Area */}
            <div className="space-y-4">
                <h4 className={`text-sm font-medium opacity-70 ${styles.subtle}`}>愿望清单</h4>
                {loading ? (
                    <div className="text-center py-8 opacity-50">加载中...</div>
                ) : requests.length === 0 ? (
                    <div className="text-center py-8 opacity-50">还没有愿望，快来许愿吧！</div>
                ) : (
                    requests.map((req) => (
                        <div key={req.id} className={`p-4 rounded-lg border ${styles.border} hover:shadow-md transition-shadow`}>
                            <div className="flex justify-between items-start mb-2">
                                <div className="flex items-center gap-2">
                                    <h5 className="font-medium">{req.title}</h5>
                                    {req.is_private && <Lock size={14} className="text-yellow-500" title="私密" />}
                                </div>
                                <span className={`text-xs px-2 py-1 rounded-full border ${
                                    req.status === 'completed' ? 'bg-green-100 text-green-700 border-green-200' :
                                    req.status === 'pending' ? 'bg-yellow-100 text-yellow-700 border-yellow-200' :
                                    'bg-gray-100 text-gray-700 border-gray-200'
                                }`}>
                                    {req.status === 'completed' ? '已实现' :
                                     req.status === 'pending' ? '进行中' :
                                     req.status === 'abandoned' ? '已放弃' : '已失效'}
                                </span>
                            </div>

                            <div className="flex items-center gap-2 text-xs opacity-60 mb-2">
                                <span className="flex items-center gap-1">
                                    <User size={12} />
                                    {req.is_anonymous ? "匿名用户" : (req.user?.username || "未知用户")}
                                </span>
                                <span>•</span>
                                <span>{new Date(req.created_at).toLocaleDateString()}</span>
                            </div>

                            <p className={`text-sm ${styles.subtle} mb-3 whitespace-pre-wrap`}>{req.content}</p>

                            {/* Admin Reply / Fulfillment Display */}
                            {(req.reply_content || req.external_link) && (
                                <div className={`mt-3 p-3 rounded bg-opacity-50 ${isDark ? "bg-green-900/20" : "bg-green-50"} text-sm`}>
                                    {req.reply_content && <p className="mb-2"><strong>站长回复:</strong> {req.reply_content}</p>}
                                    {req.external_link && (
                                        <a href={req.external_link} target="_blank" rel="noopener noreferrer" className="flex items-center gap-1 text-blue-500 hover:underline">
                                            <LinkIcon className="w-3 h-3" /> 资源链接
                                        </a>
                                    )}
                                </div>
                            )}

                            {/* User Replies */}
                            {req.replies && req.replies.length > 0 && (
                                <div className={`mt-3 pl-3 border-l-2 ${isDark ? 'border-gray-700' : 'border-gray-200'}`}>
                                    {req.replies.map(reply => (
                                        <div key={reply.id} className="mb-2 text-sm">
                                            <div className="flex items-center gap-2 text-xs opacity-60">
                                                <span className="font-medium">{reply.user?.username}</span>
                                                <span>{new Date(reply.created_at).toLocaleString()}</span>
                                            </div>
                                            <p className={`mt-0.5 ${styles.subtle}`}>{reply.content}</p>
                                        </div>
                                    ))}
                                </div>
                            )}

                            {/* Actions */}
                            <div className="flex items-center gap-3 mt-3 pt-3 border-t border-dashed border-gray-200 dark:border-gray-700">
                                <button
                                    onClick={() => setReplyingTo(replyingTo === req.id ? null : req.id)}
                                    className={`text-xs flex items-center gap-1 hover:text-blue-500 transition-colors ${styles.subtle}`}
                                >
                                    <MessageSquare size={12} /> 回复
                                </button>

                                {(user?.role === 'admin' || user?.id === req.user_id) && (
                                    <button
                                        onClick={() => handleDeleteRequest(req.id)}
                                        className="text-xs text-red-500 hover:text-red-600 flex items-center gap-1"
                                    >
                                        <Trash2 size={12} /> 删除
                                    </button>
                                )}

                                {user?.role === 'admin' && (
                                    <button
                                        onClick={() => startEdit(req)}
                                        className="text-xs text-blue-500 hover:text-blue-600 flex items-center gap-1 ml-auto"
                                    >
                                        管理
                                    </button>
                                )}
                            </div>

                            {/* Reply Input */}
                            {replyingTo === req.id && (
                                <div className="mt-3 flex gap-2">
                                    <input
                                        type="text"
                                        value={replyContent}
                                        onChange={(e) => setReplyContent(e.target.value)}
                                        placeholder="回复此愿望..."
                                        className={`flex-1 px-3 py-1.5 rounded text-sm outline-none border ${styles.input}`}
                                    />
                                    <button
                                        onClick={() => handleReply(req.id)}
                                        disabled={!replyContent.trim()}
                                        className="px-3 py-1.5 bg-blue-500 text-white text-xs rounded hover:bg-blue-600"
                                    >
                                        发送
                                    </button>
                                </div>
                            )}

                            {/* Admin Edit Form */}
                            {editingId === req.id && (
                                <div className={`mt-3 p-3 rounded border ${styles.border} ${styles.secondary}`}>
                                    <h6 className="text-xs font-bold mb-2">管理愿望</h6>
                                    <div className="space-y-2">
                                        <select
                                            value={editForm.status}
                                            onChange={(e) => setEditForm({...editForm, status: e.target.value})}
                                            className={`w-full px-2 py-1 rounded text-sm border ${styles.input}`}
                                        >
                                            <option value="pending">进行中</option>
                                            <option value="completed">已实现</option>
                                            <option value="abandoned">已放弃</option>
                                        </select>
                                        <input
                                            type="text"
                                            placeholder="资源链接"
                                            value={editForm.external_link}
                                            onChange={(e) => setEditForm({...editForm, external_link: e.target.value})}
                                            className={`w-full px-2 py-1 rounded text-sm border ${styles.input}`}
                                        />
                                        <textarea
                                            placeholder="回复内容..."
                                            value={editForm.reply_content}
                                            onChange={(e) => setEditForm({...editForm, reply_content: e.target.value})}
                                            className={`w-full px-2 py-1 rounded text-sm border ${styles.input}`}
                                        />
                                        <div className="flex justify-end gap-2">
                                            <button
                                                onClick={() => setEditingId(null)}
                                                className="px-3 py-1 text-xs border rounded hover:bg-gray-100 dark:hover:bg-gray-700"
                                            >
                                                取消
                                            </button>
                                            <button
                                                onClick={() => handleAdminUpdate(req.id)}
                                                className="px-3 py-1 text-xs bg-blue-500 text-white rounded hover:bg-blue-600"
                                            >
                                                保存
                                            </button>
                                        </div>
                                    </div>
                                </div>
                            )}
                        </div>
                    ))
                )}
            </div>
        </div>
      </div>
    </div>
  );
};

export default WishlistModal;
