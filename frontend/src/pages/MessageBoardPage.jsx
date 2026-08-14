import React, { useState, useEffect } from 'react';
import { Send, MessageSquare, User, ThumbsUp, Reply, Trash2 } from 'lucide-react';
import apiClient from '../utils/request';
import { API_ENDPOINTS } from '../config';
import { useAuth } from '../contexts/AuthContext';

const MessageBoardPage = ({ isDark }) => {
  const { user } = useAuth();
  const [messages, setMessages] = useState([]);
  const [newMessage, setNewMessage] = useState('');
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [replyTo, setReplyTo] = useState(null); // ID of the message being replied to
  const [replyContent, setReplyContent] = useState('');

  useEffect(() => {
    fetchMessages();
  }, []);

  const fetchMessages = async () => {
    try {
      const response = await apiClient.get(API_ENDPOINTS.MESSAGE_BOARD);
      const data = response.data;
      setMessages(Array.isArray(data) ? data : (data?.data ?? []));
    } catch (error) {
      console.error('Failed to fetch messages:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!newMessage.trim()) return;

    setSubmitting(true);
    try {
      await apiClient.post(API_ENDPOINTS.MESSAGE_BOARD, { content: newMessage });
      setNewMessage('');
      fetchMessages();
    } catch (error) {
      console.error('Failed to post message:', error);
      alert('发布失败，请重试');
    } finally {
      setSubmitting(false);
    }
  };

  const handleReply = async (parentId) => {
      if (!replyContent.trim()) return;
      try {
          await apiClient.post(API_ENDPOINTS.MESSAGE_BOARD, { content: replyContent, parent_id: parentId });
          setReplyContent('');
          setReplyTo(null);
          fetchMessages();
      } catch (error) {
          console.error('Failed to reply:', error);
          alert('回复失败');
      }
  };

  const handleLike = async (messageId) => {
      try {
          await apiClient.post(`${API_ENDPOINTS.MESSAGE_BOARD}/${messageId}/like`);
          fetchMessages(); // Refresh to show new like count
      } catch (error) {
          console.error('Failed to like:', error);
      }
  };

  const handleDelete = async (messageId) => {
      if (!window.confirm('确定要删除这条留言吗？')) return;
      try {
          await apiClient.delete(`${API_ENDPOINTS.MESSAGE_BOARD}/${messageId}`);
          fetchMessages();
      } catch (error) {
          console.error('Failed to delete:', error);
          alert('删除失败');
      }
  };

  const formatDate = (dateString) => {
    return new Date(dateString).toLocaleString('zh-CN', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit'
    });
  };

  const renderMessage = (msg, isReply = false) => {
      const isAuthor = msg.user?.role === 'admin';

      return (
        <div key={msg.id} className={`flex gap-4 ${isReply ? 'ml-12 mt-4' : 'mb-6'}`}>
            <div className="flex-shrink-0">
                {msg.user?.avatar ? (
                    <img src={msg.user.avatar} alt={msg.user.username} className="w-10 h-10 rounded-full object-cover" />
                ) : (
                    <div className={`w-10 h-10 rounded-full flex items-center justify-center ${isDark ? 'bg-gray-700' : 'bg-gray-200'}`}>
                        <User className={`w-6 h-6 ${isDark ? 'text-gray-400' : 'text-gray-500'}`} />
                    </div>
                )}
            </div>
            <div className="flex-1">
                <div className={`p-4 rounded-2xl ${isDark ? 'bg-gray-800' : 'bg-white'} shadow-sm`}>
                    <div className="flex items-center justify-between mb-2">
                        <div className="flex items-center gap-2">
                            <span className={`font-medium ${isDark ? 'text-gray-200' : 'text-gray-900'}`}>
                                {msg.user?.username || '未知用户'}
                            </span>
                            {isAuthor && (
                                <span className="px-2 py-0.5 text-xs font-bold bg-blue-500 text-white rounded-full">
                                    站长
                                </span>
                            )}
                            <span className={`text-xs ${isDark ? 'text-gray-500' : 'text-gray-400'}`}>
                                {formatDate(msg.created_at)}
                            </span>
                        </div>
                    </div>
                    <p className={`whitespace-pre-wrap ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>
                        {msg.content}
                    </p>

                    {/* Actions */}
                    <div className="flex items-center gap-4 mt-3">
                        <button
                            onClick={() => handleLike(msg.id)}
                            className={`flex items-center gap-1 text-sm ${isDark ? 'text-gray-500 hover:text-blue-400' : 'text-gray-500 hover:text-blue-600'} transition-colors`}
                        >
                            <ThumbsUp size={14} />
                            <span>{msg.likes || 0}</span>
                        </button>

                        {!isReply && user && (
                            <button
                                onClick={() => setReplyTo(replyTo === msg.id ? null : msg.id)}
                                className={`flex items-center gap-1 text-sm ${isDark ? 'text-gray-500 hover:text-blue-400' : 'text-gray-500 hover:text-blue-600'} transition-colors`}
                            >
                                <Reply size={14} />
                                <span>回复</span>
                            </button>
                        )}

                        {(user?.role === 'admin' || user?.id === msg.user_id) && (
                            <button
                                onClick={() => handleDelete(msg.id)}
                                className={`flex items-center gap-1 text-sm text-red-500 hover:text-red-600 transition-colors ml-auto`}
                            >
                                <Trash2 size={14} />
                                <span>删除</span>
                            </button>
                        )}
                    </div>

                    {/* Reply Input */}
                    {replyTo === msg.id && (
                        <div className="mt-4 flex gap-2">
                            <input
                                type="text"
                                value={replyContent}
                                onChange={(e) => setReplyContent(e.target.value)}
                                placeholder="回复..."
                                className={`flex-1 px-3 py-2 rounded-lg text-sm outline-none border ${
                                    isDark
                                    ? 'bg-gray-700 border-gray-600 text-white placeholder-gray-400'
                                    : 'bg-gray-50 border-gray-200 text-gray-900'
                                }`}
                            />
                            <button
                                onClick={() => handleReply(msg.id)}
                                disabled={!replyContent.trim()}
                                className="px-4 py-2 bg-blue-600 text-white text-sm rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
                            >
                                发送
                            </button>
                        </div>
                    )}
                </div>

                {/* Render Replies */}
                {msg.replies && msg.replies.length > 0 && (
                    <div className="mt-2">
                        {msg.replies.map(reply => renderMessage(reply, true))}
                    </div>
                )}
            </div>
        </div>
      );
  };

  return (
    <div className={`min-h-screen pt-20 pb-12 px-4 sm:px-6 lg:px-8 transition-colors duration-300 ${isDark ? 'bg-gray-900 text-white' : 'bg-gray-50 text-gray-900'}`}>
      <div className="max-w-4xl mx-auto">
        <div className="text-center mb-12">
          <h1 className="text-4xl font-bold mb-4 flex items-center justify-center gap-3">
            <MessageSquare className="w-10 h-10 text-blue-500" />
            留言板
          </h1>
          <p className={`text-lg ${isDark ? 'text-gray-400' : 'text-gray-600'}`}>
            欢迎留下你的想法和建议...
          </p>
        </div>

        {/* Input Form */}
        <div className={`mb-12 p-6 rounded-2xl shadow-lg ${isDark ? 'bg-gray-800' : 'bg-white'}`}>
          {user ? (
            <form onSubmit={handleSubmit}>
              <div className="mb-4">
                <textarea
                  value={newMessage}
                  onChange={(e) => setNewMessage(e.target.value)}
                  placeholder="写下你想说的话..."
                  className={`w-full p-4 rounded-xl border focus:ring-2 focus:ring-blue-500 outline-none transition-all resize-none h-32 ${
                    isDark
                      ? 'bg-gray-700 border-gray-600 text-white placeholder-gray-400'
                      : 'bg-gray-50 border-gray-200 text-gray-900 placeholder-gray-400'
                  }`}
                  required
                />
              </div>
              <div className="flex justify-end">
                <button
                  type="submit"
                  disabled={submitting || !newMessage.trim()}
                  className={`flex items-center gap-2 px-6 py-2.5 rounded-xl font-medium transition-all transform active:scale-95 ${
                    submitting || !newMessage.trim()
                      ? 'bg-gray-400 cursor-not-allowed'
                      : 'bg-blue-600 hover:bg-blue-700 text-white shadow-lg hover:shadow-blue-500/30'
                  }`}
                >
                  <Send className="w-4 h-4" />
                  {submitting ? '发布中...' : '发布留言'}
                </button>

              </div>
            </form>
          ) : (
            <div className="text-center py-8">
              <p className={isDark ? 'text-gray-400' : 'text-gray-600'}>
                请先 <a href="/login" className="text-blue-500 hover:underline">登录</a> 后发表留言
              </p>
            </div>
          )}
        </div>

        {/* Message List */}
        <div className="space-y-6">
          {loading ? (
            <div className="text-center py-12">
              <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-500 mx-auto"></div>
            </div>
          ) : !Array.isArray(messages) ? (
            <div className={`text-center py-12 rounded-2xl ${isDark ? 'bg-gray-800' : 'bg-white'}`}>
              <p className={isDark ? 'text-gray-400' : 'text-gray-600'}>数据格式错误: messages 类型为 {typeof messages}. 请查看控制台日志。</p>
            </div>
          ) : messages.length === 0 ? (
            <div className={`text-center py-12 rounded-2xl ${isDark ? 'bg-gray-800' : 'bg-white'}`}>
              <p className={isDark ? 'text-gray-400' : 'text-gray-600'}>还没有留言，来抢沙发吧！</p>
            </div>
          ) : (
            messages.map((msg) => renderMessage(msg))
          )}
        </div>
      </div>
    </div>
  );
};

export default MessageBoardPage;
