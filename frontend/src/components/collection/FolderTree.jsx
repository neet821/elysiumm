import { Eye, EyeOff, Folder, Lock, Pencil, Trash2 } from 'lucide-react'

function folderChildren(folders, parentId) {
  return folders
    .filter((folder) => folder.parent_id === parentId)
    .sort((left, right) => left.sort_order - right.sort_order || left.id - right.id)
}

function FolderBranch({ folders, level, onDelete, onEdit, onSelect, parentId, selectedId }) {
  return folderChildren(folders, parentId).map((folder) => {
    const children = folderChildren(folders, folder.id)
    return (
      <li
        key={folder.id}
        className="collection-folder-tree__item"
        role="treeitem"
        aria-label={folder.name}
        aria-level={level}
        aria-selected={selectedId === folder.id}
      >
        <div className="collection-folder-tree__row" style={{ '--folder-depth': level - 1 }}>
          <button
            type="button"
            className={selectedId === folder.id ? 'is-active' : undefined}
            onClick={() => onSelect(folder.id)}
          >
            <span
              className="collection-folder-tree__icon"
              style={folder.color ? { color: folder.color } : undefined}
            >
              <Folder size={16} aria-hidden="true" />
            </span>
            <span>{folder.name}</span>
            {folder.is_sensitive && <Lock size={13} aria-label="敏感文件夹" />}
            {folder.is_public
              ? <Eye size={13} aria-label="公开" />
              : <EyeOff size={13} aria-label="私密" />}
          </button>
          <span className="collection-folder-tree__actions">
            <button type="button" aria-label={`编辑文件夹 ${folder.name}`} onClick={() => onEdit(folder)}>
              <Pencil size={13} aria-hidden="true" />
            </button>
            <button type="button" aria-label={`删除文件夹 ${folder.name}`} onClick={() => onDelete(folder)}>
              <Trash2 size={13} aria-hidden="true" />
            </button>
          </span>
        </div>
        {children.length > 0 && (
          <ul role="group">
            <FolderBranch
              folders={folders}
              level={level + 1}
              onDelete={onDelete}
              onEdit={onEdit}
              onSelect={onSelect}
              parentId={folder.id}
              selectedId={selectedId}
            />
          </ul>
        )}
      </li>
    )
  })
}

export default function FolderTree({ folders, onDelete, onEdit, onSelect, selectedId }) {
  const knownIds = new Set(folders.map((folder) => folder.id))
  const normalizedFolders = folders.map((folder) => (
    folder.parent_id && !knownIds.has(folder.parent_id)
      ? { ...folder, parent_id: null }
      : folder
  ))

  return (
    <ul className="collection-folder-tree" role="tree" aria-label="收藏文件夹">
      <FolderBranch
        folders={normalizedFolders}
        level={1}
        onDelete={onDelete}
        onEdit={onEdit}
        onSelect={onSelect}
        parentId={null}
        selectedId={selectedId}
      />
    </ul>
  )
}
