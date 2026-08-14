import React, { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  ArrowLeft,
  Download,
  Edit3,
  ExternalLink,
  Folder,
  Link as LinkIcon,
  Plus,
  Search,
  Trash2,
  Upload,
} from "lucide-react";
import apiClient from "../utils/request";
import { API_ENDPOINTS } from "../config";

const splitTags = (value) =>
  value
    .split(/[,，\n]/)
    .map((tag) => tag.trim())
    .filter(Boolean);

const LinkDashboard = ({ styles, isDark, embedded = false }) => {
  const navigate = useNavigate();
  const [folders, setFolders] = useState([]);
  const [bookmarks, setBookmarks] = useState([]);
  const [selectedFolder, setSelectedFolder] = useState(null);
  const [selectedBookmark, setSelectedBookmark] = useState(null);
  const [selectedIds, setSelectedIds] = useState([]);
  const [searchText, setSearchText] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const [showFolderModal, setShowFolderModal] = useState(false);
  const [showBookmarkModal, setShowBookmarkModal] = useState(false);
  const [editingFolder, setEditingFolder] = useState(null);
  const [editingBookmark, setEditingBookmark] = useState(null);

  const [folderName, setFolderName] = useState("");
  const [folderParentId, setFolderParentId] = useState("");

  const [bookmarkTitle, setBookmarkTitle] = useState("");
  const [bookmarkUrl, setBookmarkUrl] = useState("");
  const [bookmarkDesc, setBookmarkDesc] = useState("");
  const [bookmarkFolderId, setBookmarkFolderId] = useState("");
  const [bookmarkTags, setBookmarkTags] = useState("");
  const [showNewFolderInBookmark, setShowNewFolderInBookmark] = useState(false);
  const [newFolderInBookmark, setNewFolderInBookmark] = useState("");

  const selectedFolderInfo = useMemo(
    () => folders.find((folder) => folder.id === selectedFolder),
    [folders, selectedFolder],
  );

  const bookmarkFolderName = (folderId) =>
    folders.find((folder) => folder.id === folderId)?.name || "未分类";

  const fetchFolders = async () => {
    const response = await apiClient.get(API_ENDPOINTS.BOOKMARK_FOLDERS);
    setFolders(response.data || []);
  };

  const fetchBookmarks = async () => {
    const params = {};
    if (searchText.trim()) params.q = searchText.trim();
    if (selectedFolder) params.folder_id = selectedFolder;

    const response = await apiClient.get(API_ENDPOINTS.BOOKMARKS, { params });
    const nextBookmarks = response.data || [];
    setBookmarks(nextBookmarks);
    setSelectedIds((ids) =>
      ids.filter((id) => nextBookmarks.some((bookmark) => bookmark.id === id)),
    );
    setSelectedBookmark((current) => {
      if (!current) return nextBookmarks[0] || null;
      return nextBookmarks.find((bookmark) => bookmark.id === current.id) || nextBookmarks[0] || null;
    });
  };

  useEffect(() => {
    const loadInitial = async () => {
      setLoading(true);
      setError("");
      try {
        await Promise.all([fetchFolders(), fetchBookmarks()]);
      } catch (fetchError) {
        console.error("获取书签失败:", fetchError);
        setError("书签数据加载失败，请稍后重试");
      } finally {
        setLoading(false);
      }
    };

    loadInitial();
  }, []);

  useEffect(() => {
    const timer = window.setTimeout(async () => {
      try {
        setError("");
        await fetchBookmarks();
      } catch (fetchError) {
        console.error("筛选书签失败:", fetchError);
        setError("筛选失败，请稍后重试");
      }
    }, 200);

    return () => window.clearTimeout(timer);
  }, [searchText, selectedFolder]);

  const refreshAll = async () => {
    await Promise.all([fetchFolders(), fetchBookmarks()]);
  };

  const resetFolderForm = () => {
    setEditingFolder(null);
    setFolderName("");
    setFolderParentId("");
  };

  const resetBookmarkForm = () => {
    setEditingBookmark(null);
    setBookmarkTitle("");
    setBookmarkUrl("");
    setBookmarkDesc("");
    setBookmarkFolderId("");
    setBookmarkTags("");
    setShowNewFolderInBookmark(false);
    setNewFolderInBookmark("");
  };

  const openFolderModal = (folder = null) => {
    if (folder) {
      setEditingFolder(folder);
      setFolderName(folder.name);
      setFolderParentId(folder.parent_id ? String(folder.parent_id) : "");
    } else {
      resetFolderForm();
    }
    setShowFolderModal(true);
  };

  const openBookmarkModal = (bookmark = null) => {
    if (bookmark) {
      setEditingBookmark(bookmark);
      setBookmarkTitle(bookmark.title);
      setBookmarkUrl(bookmark.url);
      setBookmarkDesc(bookmark.description || "");
      setBookmarkFolderId(bookmark.folder_id ? String(bookmark.folder_id) : "");
      setBookmarkTags((bookmark.tags || []).join(", "));
    } else {
      resetBookmarkForm();
      if (selectedFolder) {
        setBookmarkFolderId(String(selectedFolder));
      }
    }
    setShowBookmarkModal(true);
  };

  const handleSaveFolder = async (event) => {
    event.preventDefault();
    try {
      const folderData = {
        name: folderName.trim(),
        parent_id: folderParentId ? Number(folderParentId) : null,
      };
      if (editingFolder) {
        await apiClient.put(API_ENDPOINTS.BOOKMARK_FOLDER_DETAIL(editingFolder.id), folderData);
      } else {
        await apiClient.post(API_ENDPOINTS.BOOKMARK_FOLDERS, folderData);
      }
      setShowFolderModal(false);
      resetFolderForm();
      await refreshAll();
    } catch (saveError) {
      console.error("保存文件夹失败:", saveError);
      alert("文件夹保存失败，请重试");
    }
  };

  const handleSaveBookmark = async (event) => {
    event.preventDefault();
    try {
      let finalFolderId = bookmarkFolderId ? Number(bookmarkFolderId) : null;

      if (showNewFolderInBookmark && newFolderInBookmark.trim()) {
        const folderResponse = await apiClient.post(API_ENDPOINTS.BOOKMARK_FOLDERS, {
          name: newFolderInBookmark.trim(),
          parent_id: null,
        });
        finalFolderId = folderResponse.data.id;
      }

      const bookmarkData = {
        title: bookmarkTitle.trim(),
        url: bookmarkUrl.trim(),
        description: bookmarkDesc.trim() || null,
        folder_id: finalFolderId,
        tags: splitTags(bookmarkTags),
      };

      if (editingBookmark) {
        await apiClient.put(API_ENDPOINTS.BOOKMARK_DETAIL(editingBookmark.id), bookmarkData);
      } else {
        await apiClient.post(API_ENDPOINTS.BOOKMARKS, bookmarkData);
      }

      setShowBookmarkModal(false);
      resetBookmarkForm();
      await refreshAll();
    } catch (saveError) {
      console.error("保存书签失败:", saveError);
      alert("书签保存失败，请重试");
    }
  };

  const handleDeleteFolder = async (folderId) => {
    if (!window.confirm("删除文件夹后，里面的书签会移到未分类。确定继续吗？")) return;

    try {
      await apiClient.delete(API_ENDPOINTS.BOOKMARK_FOLDER_DETAIL(folderId));
      if (selectedFolder === folderId) setSelectedFolder(null);
      await refreshAll();
    } catch (deleteError) {
      console.error("删除文件夹失败:", deleteError);
      alert("文件夹删除失败，请重试");
    }
  };

  const handleDeleteBookmark = async (bookmarkId) => {
    if (!window.confirm("确定要删除这个书签吗？")) return;

    try {
      await apiClient.delete(API_ENDPOINTS.BOOKMARK_DETAIL(bookmarkId));
      setSelectedBookmark((current) => (current?.id === bookmarkId ? null : current));
      await fetchBookmarks();
    } catch (deleteError) {
      console.error("删除书签失败:", deleteError);
      alert("书签删除失败，请重试");
    }
  };

  const handleBulkDelete = async () => {
    if (selectedIds.length === 0) return;
    if (!window.confirm(`确定要删除选中的 ${selectedIds.length} 个书签吗？`)) return;

    try {
      await apiClient.post(API_ENDPOINTS.BOOKMARK_BULK, {
        action: "delete",
        ids: selectedIds,
      });
      setSelectedIds([]);
      await fetchBookmarks();
    } catch (bulkError) {
      console.error("批量删除失败:", bulkError);
      alert("批量删除失败，请重试");
    }
  };

  const handleExportJson = async () => {
    try {
      const response = await apiClient.get(API_ENDPOINTS.BOOKMARK_EXPORT_JSON);
      const blob = new Blob([JSON.stringify(response.data, null, 2)], {
        type: "application/json",
      });
      const url = window.URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `blue-album-bookmarks-${Date.now()}.json`;
      anchor.click();
      window.URL.revokeObjectURL(url);
    } catch (exportError) {
      console.error("导出书签失败:", exportError);
      alert("导出失败，请重试");
    }
  };

  const handleImportJson = async (event) => {
    const file = event.target.files?.[0];
    if (!file) return;

    try {
      const text = await file.text();
      const payload = JSON.parse(text);
      await apiClient.post(API_ENDPOINTS.BOOKMARK_IMPORT_JSON, payload);
      await refreshAll();
    } catch (importError) {
      console.error("导入书签失败:", importError);
      alert("导入失败，请确认文件是 Blue Album 导出的 JSON");
    } finally {
      event.target.value = "";
    }
  };

  const handleExportHtml = async () => {
    try {
      const response = await apiClient.get(API_ENDPOINTS.BOOKMARK_EXPORT_HTML, { responseType: "blob" });
      const url = window.URL.createObjectURL(response.data);
      const anchor = document.createElement("a"); anchor.href = url; anchor.download = `blue-album-bookmarks-${Date.now()}.html`; anchor.click();
      window.URL.revokeObjectURL(url);
    } catch { alert("HTML 导出失败，请重试"); }
  };

  const handleImportHtml = async (event) => {
    const file = event.target.files?.[0]; if (!file) return;
    try { await apiClient.post(API_ENDPOINTS.BOOKMARK_IMPORT_HTML, await file.text(), { headers: { "Content-Type": "text/html" } }); await refreshAll(); }
    catch { alert("HTML 导入失败，请确认文件是浏览器导出的书签文件"); }
    finally { event.target.value = ""; }
  };

  const toggleSelected = (bookmarkId) => {
    setSelectedIds((ids) =>
      ids.includes(bookmarkId)
        ? ids.filter((id) => id !== bookmarkId)
        : [...ids, bookmarkId],
    );
  };

  return (
    <div
      className={`${embedded ? "pt-6" : "pt-32"} pb-24 min-h-screen ${styles.bgSecondary} transition-colors duration-1000 animate-fade-in`}
    >
      <div className="max-w-7xl mx-auto px-4 sm:px-6">
        {!embedded && (
          <button
            onClick={() => navigate("/tools")}
            className={`flex items-center gap-2 ${styles.textMuted} hover:opacity-80 mb-8 transition-colors`}
          >
            <ArrowLeft size={16} />
            返回工具页
          </button>
        )}

        <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between mb-6">
          <div>
            <p className={`text-sm ${styles.textMuted}`}>个人书签管理</p>
            <h2 className={`text-2xl font-bold ${styles.text}`}>收藏夹</h2>
          </div>
          <div className="flex flex-wrap gap-2">
            <button
              onClick={() => openFolderModal()}
              className={`flex items-center gap-2 px-4 py-2 rounded-lg border ${styles.border} ${styles.bg} ${styles.text}`}
            >
              <Folder size={16} />
              新建文件夹
            </button>
            <button
              onClick={() => openBookmarkModal()}
              className={`flex items-center gap-2 px-4 py-2 rounded-lg text-white ${
                isDark ? "bg-orange-600 hover:bg-orange-500" : "bg-[#189BCC] hover:bg-[#1589b5]"
              }`}
            >
              <Plus size={16} />
              新建书签
            </button>
            <button
              onClick={handleExportJson}
              className={`flex items-center gap-2 px-4 py-2 rounded-lg border ${styles.border} ${styles.bg} ${styles.text}`}
            >
              <Download size={16} />
              导出
            </button>
            <button onClick={handleExportHtml} className={`flex items-center gap-2 px-4 py-2 rounded-lg border ${styles.border} ${styles.bg} ${styles.text}`}><Download size={16}/>导出 HTML</button>
            <label
              className={`flex cursor-pointer items-center gap-2 px-4 py-2 rounded-lg border ${styles.border} ${styles.bg} ${styles.text}`}
            >
              <Upload size={16} />
              导入
              <input
                type="file"
                accept=".json,application/json"
                className="hidden"
                onChange={handleImportJson}
              />
            </label>
            <label className={`flex cursor-pointer items-center gap-2 px-4 py-2 rounded-lg border ${styles.border} ${styles.bg} ${styles.text}`}><Upload size={16}/>导入 HTML<input type="file" accept=".html,.htm,text/html" className="hidden" onChange={handleImportHtml}/></label>
          </div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-[240px_minmax(0,1fr)_300px] gap-6">
          <aside className={`${styles.bg} rounded-xl shadow-sm border ${styles.border} p-4 h-fit`}>
            <div className="flex items-center justify-between mb-4">
              <h3 className={`font-bold ${styles.text}`}>文件夹</h3>
              <button
                onClick={() => openFolderModal()}
                className={`p-1 ${styles.accentClass} hover:opacity-70`}
                title="新建文件夹"
              >
                <Plus size={18} />
              </button>
            </div>

            <div className="space-y-2">
              <button
                onClick={() => setSelectedFolder(null)}
                className={`w-full text-left px-3 py-2 rounded-lg transition-colors ${
                  !selectedFolder
                    ? isDark
                      ? "bg-orange-600 text-white"
                      : "bg-[#189BCC] text-white"
                    : `${styles.bgSecondary} ${styles.textMuted}`
                }`}
              >
                全部书签 ({bookmarks.length})
              </button>

              {folders.map((folder) => (
                <div key={folder.id} className="group relative">
                  <button
                    onClick={() => setSelectedFolder(folder.id)}
                    className={`w-full text-left px-3 py-2 pr-16 rounded-lg transition-colors ${
                      selectedFolder === folder.id
                        ? isDark
                          ? "bg-orange-600 text-white"
                          : "bg-[#189BCC] text-white"
                        : `${styles.bgSecondary} ${styles.textMuted}`
                    }`}
                  >
                    <Folder size={14} className="inline mr-2" />
                    {folder.name}
                  </button>
                  <div className="absolute right-2 top-1/2 -translate-y-1/2 opacity-100 sm:opacity-0 sm:group-hover:opacity-100 flex gap-1">
                    <button
                      onClick={(event) => {
                        event.stopPropagation();
                        openFolderModal(folder);
                      }}
                      className="p-1 hover:bg-gray-200 dark:hover:bg-gray-700 rounded"
                      title="编辑文件夹"
                    >
                      <Edit3 size={12} />
                    </button>
                    <button
                      onClick={(event) => {
                        event.stopPropagation();
                        handleDeleteFolder(folder.id);
                      }}
                      className="p-1 hover:bg-red-100 text-red-500 rounded"
                      title="删除文件夹"
                    >
                      <Trash2 size={12} />
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </aside>

          <main className={`${styles.bg} rounded-xl shadow-sm border ${styles.border} p-4 sm:p-6`}>
            <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between mb-5">
              <div>
                <h3 className={`text-xl font-bold ${styles.text}`}>
                  {selectedFolderInfo ? selectedFolderInfo.name : "所有书签"}
                </h3>
                <p className={`text-sm ${styles.textMuted}`}>共 {bookmarks.length} 条</p>
              </div>
              <div className="relative w-full sm:max-w-xs">
                <Search size={16} className={`absolute left-3 top-1/2 -translate-y-1/2 ${styles.textMuted}`} />
                <input
                  type="search"
                  value={searchText}
                  onChange={(event) => setSearchText(event.target.value)}
                  placeholder="搜索标题、网址、描述或标签"
                  className={`w-full pl-9 pr-3 py-2 border ${styles.border} rounded-lg ${styles.bgSecondary} ${styles.text}`}
                />
              </div>
            </div>

            {selectedIds.length > 0 && (
              <div className={`mb-4 flex items-center justify-between rounded-lg border ${styles.border} ${styles.bgSecondary} px-3 py-2`}>
                <span className={`text-sm ${styles.text}`}>已选 {selectedIds.length} 个</span>
                <button
                  onClick={handleBulkDelete}
                  className="flex items-center gap-1 text-sm text-red-500 hover:opacity-80"
                >
                  <Trash2 size={14} />
                  批量删除
                </button>
              </div>
            )}

            {error && (
              <div className="mb-4 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
                {error}
              </div>
            )}

            {loading ? (
              <div className="flex justify-center py-12">
                <div className="animate-spin w-12 h-12 border-4 border-gray-300 border-t-blue-500 rounded-full" />
              </div>
            ) : bookmarks.length === 0 ? (
              <div className="text-center py-12">
                <LinkIcon size={48} className={`${styles.textMuted} mx-auto mb-4`} />
                <p className={`${styles.textMuted}`}>暂无书签</p>
              </div>
            ) : (
              <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
                {bookmarks.map((bookmark) => (
                  <article
                    key={bookmark.id}
                    onClick={() => setSelectedBookmark(bookmark)}
                    className={`${styles.bgSecondary} p-4 rounded-lg border ${
                      selectedBookmark?.id === bookmark.id ? "border-sky-400" : styles.border
                    } group hover:shadow-md transition-all cursor-pointer`}
                  >
                    <div className="flex items-start gap-3">
                      <input
                        type="checkbox"
                        checked={selectedIds.includes(bookmark.id)}
                        onChange={() => toggleSelected(bookmark.id)}
                        onClick={(event) => event.stopPropagation()}
                        className="mt-1"
                        aria-label="选择书签"
                      />
                      <div className="min-w-0 flex-1">
                        <div className="flex items-start justify-between gap-3">
                          <h4 className={`font-bold ${styles.text} truncate`}>
                            {bookmark.title}
                          </h4>
                          <div className="flex gap-1 opacity-100 sm:opacity-0 sm:group-hover:opacity-100 transition-opacity">
                            <button
                              onClick={(event) => {
                                event.stopPropagation();
                                openBookmarkModal(bookmark);
                              }}
                              className={`p-1.5 ${styles.textMuted} hover:opacity-80 rounded`}
                              title="编辑书签"
                            >
                              <Edit3 size={14} />
                            </button>
                            <button
                              onClick={(event) => {
                                event.stopPropagation();
                                handleDeleteBookmark(bookmark.id);
                              }}
                              className="p-1.5 text-red-500 hover:bg-red-50 rounded"
                              title="删除书签"
                            >
                              <Trash2 size={14} />
                            </button>
                          </div>
                        </div>
                        <p className={`text-xs ${styles.textMuted} mt-1 truncate`}>
                          {bookmarkFolderName(bookmark.folder_id)}
                        </p>
                        {bookmark.description && (
                          <p className={`text-sm ${styles.textMuted} mt-3 line-clamp-2`}>
                            {bookmark.description}
                          </p>
                        )}
                        {bookmark.tags?.length > 0 && (
                          <div className="mt-3 flex flex-wrap gap-2">
                            {bookmark.tags.map((tag) => (
                              <span
                                key={tag}
                                className={`rounded-full px-2 py-0.5 text-xs ${styles.bg} ${styles.textMuted}`}
                              >
                                {tag}
                              </span>
                            ))}
                          </div>
                        )}
                        <a
                          href={bookmark.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          onClick={(event) => event.stopPropagation()}
                          className={`mt-3 inline-flex max-w-full items-center gap-1 text-sm ${styles.accentClass} hover:underline`}
                        >
                          <ExternalLink size={12} />
                          <span className="truncate">{bookmark.url}</span>
                        </a>
                      </div>
                    </div>
                  </article>
                ))}
              </div>
            )}
          </main>

          <aside className={`${styles.bg} rounded-xl shadow-sm border ${styles.border} p-4 h-fit`}>
            <h3 className={`font-bold ${styles.text} mb-4`}>详情</h3>
            {selectedBookmark ? (
              <div className="space-y-4">
                <div>
                  <p className={`text-xs ${styles.textMuted}`}>标题</p>
                  <p className={`font-semibold ${styles.text}`}>{selectedBookmark.title}</p>
                </div>
                <div>
                  <p className={`text-xs ${styles.textMuted}`}>文件夹</p>
                  <p className={`${styles.text}`}>{bookmarkFolderName(selectedBookmark.folder_id)}</p>
                </div>
                <div>
                  <p className={`text-xs ${styles.textMuted}`}>网址</p>
                  <a
                    href={selectedBookmark.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className={`${styles.accentClass} break-all`}
                  >
                    {selectedBookmark.url}
                  </a>
                </div>
                {selectedBookmark.description && (
                  <div>
                    <p className={`text-xs ${styles.textMuted}`}>描述</p>
                    <p className={`${styles.text}`}>{selectedBookmark.description}</p>
                  </div>
                )}
                {selectedBookmark.tags?.length > 0 && (
                  <div>
                    <p className={`text-xs ${styles.textMuted} mb-2`}>标签</p>
                    <div className="flex flex-wrap gap-2">
                      {selectedBookmark.tags.map((tag) => (
                        <span
                          key={tag}
                          className={`rounded-full px-2 py-1 text-xs ${styles.bgSecondary} ${styles.textMuted}`}
                        >
                          {tag}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
                <div className="flex gap-2 pt-2">
                  <button
                    onClick={() => openBookmarkModal(selectedBookmark)}
                    className={`flex-1 py-2 rounded-lg border ${styles.border} ${styles.text}`}
                  >
                    编辑
                  </button>
                  <button
                    onClick={() => handleDeleteBookmark(selectedBookmark.id)}
                    className="flex-1 py-2 rounded-lg bg-red-500 text-white"
                  >
                    删除
                  </button>
                </div>
              </div>
            ) : (
              <p className={`text-sm ${styles.textMuted}`}>选择一个书签查看详情</p>
            )}
          </aside>
        </div>
      </div>

      <div className={`fixed bottom-0 left-0 right-0 z-40 border-t ${styles.border} ${styles.bg} p-3 md:hidden`}>
        <div className="mx-auto flex max-w-md gap-2">
          <button
            onClick={() => openBookmarkModal()}
            className={`flex-1 rounded-lg py-2 text-white ${
              isDark ? "bg-orange-600" : "bg-[#189BCC]"
            }`}
          >
            新建书签
          </button>
          <button
            onClick={() => openFolderModal()}
            className={`flex-1 rounded-lg border ${styles.border} ${styles.text}`}
          >
            新建文件夹
          </button>
        </div>
      </div>

      {showFolderModal && (
        <div className="fixed inset-0 bg-black/50 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className={`${styles.bg} rounded-xl p-6 max-w-md w-full`}>
            <h3 className={`text-xl font-bold ${styles.text} mb-4`}>
              {editingFolder ? "编辑文件夹" : "新建文件夹"}
            </h3>
            <form onSubmit={handleSaveFolder} className="space-y-4">
              <div>
                <label className={`block text-sm ${styles.text} mb-2`}>名称</label>
                <input
                  type="text"
                  value={folderName}
                  onChange={(event) => setFolderName(event.target.value)}
                  className={`w-full px-4 py-2 border ${styles.border} rounded ${styles.bgSecondary} ${styles.text}`}
                  required
                />
              </div>
              <div>
                <label className={`block text-sm ${styles.text} mb-2`}>上级文件夹</label>
                <select
                  value={folderParentId}
                  onChange={(event) => setFolderParentId(event.target.value)}
                  className={`w-full px-4 py-2 border ${styles.border} rounded ${styles.bgSecondary} ${styles.text}`}
                >
                  <option value="">无</option>
                  {folders
                    .filter((folder) => folder.id !== editingFolder?.id)
                    .map((folder) => (
                      <option key={folder.id} value={folder.id}>
                        {folder.name}
                      </option>
                    ))}
                </select>
              </div>
              <div className="flex gap-3">
                <button
                  type="submit"
                  className={`flex-1 py-2 text-white rounded ${
                    isDark ? "bg-orange-600 hover:bg-orange-500" : "bg-[#189BCC] hover:bg-[#1589b5]"
                  }`}
                >
                  保存
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setShowFolderModal(false);
                    resetFolderForm();
                  }}
                  className={`flex-1 py-2 border ${styles.border} rounded ${styles.textMuted}`}
                >
                  取消
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {showBookmarkModal && (
        <div className="fixed inset-0 bg-black/50 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className={`${styles.bg} rounded-xl p-6 max-w-md w-full max-h-[90vh] overflow-y-auto`}>
            <h3 className={`text-xl font-bold ${styles.text} mb-4`}>
              {editingBookmark ? "编辑书签" : "新建书签"}
            </h3>
            <form onSubmit={handleSaveBookmark} className="space-y-4">
              <div>
                <label className={`block text-sm ${styles.text} mb-2`}>标题</label>
                <input
                  type="text"
                  value={bookmarkTitle}
                  onChange={(event) => setBookmarkTitle(event.target.value)}
                  className={`w-full px-4 py-2 border ${styles.border} rounded ${styles.bgSecondary} ${styles.text}`}
                  required
                />
              </div>
              <div>
                <label className={`block text-sm ${styles.text} mb-2`}>网址</label>
                <input
                  type="url"
                  value={bookmarkUrl}
                  onChange={(event) => setBookmarkUrl(event.target.value)}
                  className={`w-full px-4 py-2 border ${styles.border} rounded ${styles.bgSecondary} ${styles.text}`}
                  required
                />
              </div>
              <div>
                <label className={`block text-sm ${styles.text} mb-2`}>文件夹</label>
                {!showNewFolderInBookmark ? (
                  <select
                    value={bookmarkFolderId}
                    onChange={(event) => {
                      if (event.target.value === "__new__") {
                        setShowNewFolderInBookmark(true);
                        setBookmarkFolderId("");
                      } else {
                        setBookmarkFolderId(event.target.value);
                      }
                    }}
                    className={`w-full px-4 py-2 border ${styles.border} rounded ${styles.bgSecondary} ${styles.text}`}
                  >
                    <option value="">未分类</option>
                    {folders.map((folder) => (
                      <option key={folder.id} value={folder.id}>
                        {folder.name}
                      </option>
                    ))}
                    <option value="__new__">新建文件夹...</option>
                  </select>
                ) : (
                  <div className="space-y-2">
                    <input
                      type="text"
                      value={newFolderInBookmark}
                      onChange={(event) => setNewFolderInBookmark(event.target.value)}
                      className={`w-full px-4 py-2 border ${styles.border} rounded ${styles.bgSecondary} ${styles.text}`}
                      placeholder="输入新文件夹名称"
                      required
                      autoFocus
                    />
                    <button
                      type="button"
                      onClick={() => {
                        setShowNewFolderInBookmark(false);
                        setNewFolderInBookmark("");
                      }}
                      className={`text-sm ${styles.textMuted} hover:opacity-80`}
                    >
                      返回选择现有文件夹
                    </button>
                  </div>
                )}
              </div>
              <div>
                <label className={`block text-sm ${styles.text} mb-2`}>标签</label>
                <input
                  type="text"
                  value={bookmarkTags}
                  onChange={(event) => setBookmarkTags(event.target.value)}
                  placeholder="用逗号分隔，例如：资料, 常用"
                  className={`w-full px-4 py-2 border ${styles.border} rounded ${styles.bgSecondary} ${styles.text}`}
                />
              </div>
              <div>
                <label className={`block text-sm ${styles.text} mb-2`}>描述</label>
                <textarea
                  value={bookmarkDesc}
                  onChange={(event) => setBookmarkDesc(event.target.value)}
                  rows={3}
                  className={`w-full px-4 py-2 border ${styles.border} rounded ${styles.bgSecondary} ${styles.text}`}
                />
              </div>
              <div className="flex gap-3">
                <button
                  type="submit"
                  className={`flex-1 py-2 text-white rounded ${
                    isDark ? "bg-orange-600 hover:bg-orange-500" : "bg-[#189BCC] hover:bg-[#1589b5]"
                  }`}
                >
                  保存
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setShowBookmarkModal(false);
                    resetBookmarkForm();
                  }}
                  className={`flex-1 py-2 border ${styles.border} rounded ${styles.textMuted}`}
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

export default LinkDashboard;
