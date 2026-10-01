import { Pause, Play, RefreshCw, RotateCcw, X } from 'lucide-react'

const STATUS_LABELS = {
  queued: '等待上传',
  uploading: '上传中',
  paused: '已暂停',
  failed: '上传失败',
  result_error: '已上传，等待同步结果',
  complete: '已完成',
}

export default function AdminTusUploadQueue({ files, manager }) {
  if (!files.length) return null

  return <section className="admin-tus-queue" aria-label="上传队列">
    <h4>上传队列</h4>
    {files.map((file) => <article className="admin-tus-queue__item" key={file.id}>
      <div className="admin-tus-queue__summary">
        <strong>{file.name}</strong>
        <span>{file.purpose === 'admin_file' ? '管理员文件' : '文件中转'} · {STATUS_LABELS[file.status] || '处理中'}</span>
        {file.error && <small role="alert">{file.error}</small>}
      </div>
      <progress aria-label={`${file.name} 上传进度`} max="100" value={file.progress} />
      <span className="admin-tus-queue__percent">{file.progress}%</span>
      <div className="admin-tus-queue__actions">
        {file.status === 'result_error'
          ? <button type="button" aria-label={`重试同步 ${file.name}`} onClick={() => manager.retryResult(file.id)}><RefreshCw size={14} /></button>
          : file.status === 'failed'
            ? <button type="button" aria-label={`重试 ${file.name}`} onClick={() => manager.retryUpload(file.id)}><RotateCcw size={14} /></button>
            : !['complete'].includes(file.status)
              ? <button type="button" aria-label={`${file.status === 'paused' ? '继续' : '暂停'} ${file.name}`} onClick={() => manager.pauseResume(file.id)}>{file.status === 'paused' ? <Play size={14} /> : <Pause size={14} />}</button>
              : null}
        {file.status !== 'complete' && file.status !== 'result_error' && <button type="button" aria-label={`取消 ${file.name}`} onClick={() => manager.removeFile(file.id)}><X size={14} /></button>}
      </div>
    </article>)}
  </section>
}
