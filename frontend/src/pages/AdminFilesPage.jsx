import { Check, Copy, Download, FileDown, FolderSync, Link2, LogOut, RefreshCw, Trash2, Upload } from 'lucide-react'

import '../features/admin-files/adminFiles.css'
import { isTransferHost } from '../config.js'
import AdminTusUploadQueue from '../features/admin-files/AdminTusUploadQueue.jsx'
import { formatSize } from '../features/admin-files/adminFilesUtils.js'
import { useAdminFilesWorkspace } from '../features/admin-files/useAdminFilesWorkspace.js'
import { useAuth } from '../contexts/AuthContext.jsx'


export default function AdminFilesPage() {
  const { logout } = useAuth()
  const {
    addSelectedFiles,
    adminFiles,
    adminNote,
    copyAdminNote,
    copyShareLink,
    copied,
    deleteAdminFile,
    deleteTransferFile,
    downloadAdminFile,
    downloadSync,
    downloadTransfer,
    editAdminNote,
    error,
    loadSync,
    noteCopied,
    noteSaved,
    noteSaving,
    refresh,
    sync,
    transfer,
    transferFiles,
    tusUploads,
  } = useAdminFilesWorkspace()
  const fixedTransferHost = isTransferHost()
  const syncOnline = sync.status === 'online'
  const syncRoot = `/home/neet821/Public${sync.path ? `/${sync.path}` : ''}`

  return <section className="admin-files-page">
    <header className="admin-page-heading admin-page-heading--actions-only">
      <div className="admin-page-heading__actions">
        <button className="admin-icon-button" type="button" onClick={refresh} aria-label="刷新文件"><RefreshCw size={16} /></button>
        {fixedTransferHost && <button className="admin-icon-button" type="button" onClick={() => logout()}><LogOut size={16} /><span>退出登录</span></button>}
      </div>
    </header>
    {(tusUploads.error || error) && <p className="admin-inline-error" role="alert">{tusUploads.error || error}</p>}
    <div className="admin-file-cards">
      <article className={`admin-file-card${syncOnline ? '' : ' admin-file-card--disabled'}`}>
        <div className="admin-file-card__icon"><FolderSync size={21} /></div>
        <h3>文件同步</h3>
        <div className={`admin-file-status admin-file-status--${sync.status}`}>{sync.status === 'online' ? '在线' : sync.status === 'loading' ? '连接中' : sync.status === 'auth_failed' ? '鉴权失败' : '电脑未连接'}</div>
        <div className="admin-file-browser" aria-disabled={!syncOnline}>
          <div className="admin-file-browser__bar"><span>{syncRoot}</span>{sync.path && <button type="button" disabled={!syncOnline} onClick={() => loadSync(sync.path.split('/').slice(0, -1).join('/'))}>上一级</button>}</div>
          {syncOnline && sync.items.map((item) => <button className="admin-file-browser__item" type="button" disabled={!syncOnline} key={item.path} onClick={() => downloadSync(item)}><FileDown size={15} /><span>{item.name}</span><Download size={14} /></button>)}
          {sync.status === 'online' && !sync.items.length && <p className="admin-empty">暂无文件。</p>}
          {sync.status !== 'online' && sync.status !== 'loading' && <p className="admin-empty">电脑未连接，文件同步暂不可用。</p>}
        </div>
      </article>
      <article className="admin-file-card">
        <div className="admin-file-card__icon"><FileDown size={21} /></div>
        <h3>管理员文件</h3>
        <label className="admin-transfer-upload"><Upload size={15} />{tusUploads.error ? '可续传上传不可用' : tusUploads.ready ? '上传管理员文件' : '上传组件准备中…'}<input aria-label="选择管理员文件上传" type="file" multiple disabled={!tusUploads.ready} onChange={(event) => addSelectedFiles(event, 'admin_file')} /></label>
        <div className="admin-transfer-list">
          {adminFiles.map((item) => <div className="admin-transfer-file" key={item.id}>
            <button className="admin-transfer-file__download" type="button" onClick={() => downloadAdminFile(item)} aria-label={`下载 ${item.name}`}>
              <Download size={15} /><span><strong>{item.name}</strong><small>{formatSize(item.size)}</small></span>
            </button>
            <button className="admin-transfer-file__delete" type="button" onClick={() => deleteAdminFile(item)} aria-label={`删除 ${item.name}`}><Trash2 size={15} /></button>
          </div>)}
          {!adminFiles.length && <p className="admin-empty">暂无文件。</p>}
        </div>
      </article>
      <article className="admin-file-card">
        <div className="admin-file-card__icon admin-file-card__icon--violet"><Link2 size={21} /></div>
        <h3>文件中转</h3>
        <label className="admin-transfer-upload"><Upload size={15} />{tusUploads.error ? '可续传上传不可用' : tusUploads.ready ? transfer?.ready ? '继续上传文件' : '准备中…' : '上传组件准备中…'}<input aria-label="选择文件上传" type="file" multiple disabled={!tusUploads.ready || !transfer?.id} onChange={(event) => addSelectedFiles(event, 'transfer_file')} /></label>
        {transfer?.ready && <div className="admin-transfer-created"><span>中转链接</span><div className="transfer-share-row"><input aria-label="中转链接" readOnly value={transfer.url} onFocus={(event) => event.target.select()} /><button type="button" onClick={copyShareLink}>{copied ? <Check size={15} /> : <Copy size={15} />}<span>{copied ? '已复制' : '复制分享链接'}</span></button></div></div>}
        <div className="admin-transfer-list">
          {transferFiles.map((item) => <div className="admin-transfer-file" key={item.id}><button className="admin-transfer-file__download" type="button" onClick={() => downloadTransfer(item)} aria-label={`下载 ${item.name}`}><Download size={15} /><span><strong>{item.name}</strong><small>{formatSize(item.size)}</small></span></button><button className="admin-transfer-file__delete" type="button" onClick={() => deleteTransferFile(item)} aria-label={`删除 ${item.name}`}><Trash2 size={15} /></button></div>)}
          {!transferFiles.length && <p className="admin-empty">暂无文件。</p>}
        </div>
      </article>
      <article className="admin-file-card admin-transfer-note-card">
        <div className="admin-file-card__icon admin-file-card__icon--note"><FileDown size={21} /></div>
        <h3>纯文本</h3>
        <label className="admin-transfer-note__label" htmlFor="admin-transfer-note">管理员纯文本</label>
        <textarea id="admin-transfer-note" aria-label="管理员纯文本" value={adminNote} onChange={editAdminNote} rows="8" placeholder="只在管理员页面保存的文本" />
        <div className="admin-transfer-note__actions"><button type="button" onClick={copyAdminNote} aria-label={noteCopied ? '已复制文本' : '复制文本'}>{noteCopied ? <Check size={15} /> : <Copy size={15} />}<span>{noteCopied ? '已复制' : '复制文本'}</span></button><div className="admin-transfer-note__status">{noteSaving ? '保存中…' : noteSaved ? '已保存' : '自动保存'}</div></div>
      </article>
    </div>
    <AdminTusUploadQueue files={tusUploads.files} manager={tusUploads.manager} />
  </section>
}
