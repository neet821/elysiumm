import { Download, Pencil, Play, Trash2 } from 'lucide-react'


const formatBytes = (bytes = 0) => {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 ** 2) return `${(bytes / 1024).toFixed(1)} KB`
  if (bytes < 1024 ** 3) return `${(bytes / 1024 ** 2).toFixed(1)} MB`
  return `${(bytes / 1024 ** 3).toFixed(1)} GB`
}


export default function AdminLiveRecordings({
  onDelete,
  onDownload,
  onPreview,
  onRename,
  recordings,
}) {
  if (!recordings.length) {
    return <p className="admin-live__empty">开播后的录像会自动出现在这里。</p>
  }
  return (
    <ul className="admin-live__recordings">
      {recordings.map((recording) => (
        <li key={recording.id}>
          <div>
            <strong>{recording.display_name}</strong>
            <span>
              {formatBytes(recording.file_size)} · {Math.round(recording.duration_seconds || 0)} 秒 · {recording.status === 'ready' ? '可用' : recording.status}
            </span>
          </div>
          <div>
            {recording.status === 'ready' && (
              <>
                <button
                  aria-label={`播放录像 ${recording.display_name}`}
                  type="button"
                  onClick={() => onPreview(recording)}
                >
                  <Play aria-hidden="true" />
                </button>
                <button
                  aria-label={`下载录像 ${recording.display_name}`}
                  type="button"
                  onClick={() => onDownload(recording)}
                >
                  <Download aria-hidden="true" />
                </button>
              </>
            )}
            <button
              aria-label={`改名录像 ${recording.display_name}`}
              type="button"
              onClick={() => onRename(recording)}
            >
              <Pencil aria-hidden="true" />
            </button>
            <button
              aria-label={`删除录像 ${recording.display_name}`}
              type="button"
              onClick={() => onDelete(recording)}
            >
              <Trash2 aria-hidden="true" />
            </button>
          </div>
        </li>
      ))}
    </ul>
  )
}
