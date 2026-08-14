import { useEffect, useMemo, useRef, useState } from 'react'
import { Dialog } from './Dialog.jsx'
import { Input } from './Input.jsx'

export function CommandPalette({ items, onOpenChange, onSelect, open }) {
  const [query, setQuery] = useState('')
  const [activeIndex, setActiveIndex] = useState(0)
  const searchRef = useRef(null)

  const filteredItems = useMemo(() => {
    const needle = query.trim().toLocaleLowerCase()
    if (!needle) return items
    return items.filter((item) => {
      const haystack = [item.label, item.description, ...(item.keywords || [])]
        .filter(Boolean)
        .join(' ')
        .toLocaleLowerCase()
      return haystack.includes(needle)
    })
  }, [items, query])

  useEffect(() => {
    setActiveIndex(0)
    if (!open) setQuery('')
  }, [open, query])

  const selectItem = (item) => {
    if (!item) return
    onSelect(item)
    onOpenChange(false)
  }

  const handleKeyDown = (event) => {
    if (event.key === 'ArrowDown') {
      event.preventDefault()
      setActiveIndex((index) => (index + 1) % Math.max(filteredItems.length, 1))
    } else if (event.key === 'ArrowUp') {
      event.preventDefault()
      setActiveIndex((index) => (index - 1 + Math.max(filteredItems.length, 1)) % Math.max(filteredItems.length, 1))
    } else if (event.key === 'Enter') {
      event.preventDefault()
      selectItem(filteredItems[activeIndex])
    }
  }

  return (
    <Dialog
      className="ui-command-palette"
      description="搜索当前账户可以打开的页面。"
      initialFocusRef={searchRef}
      onOpenChange={onOpenChange}
      open={open}
      title="快捷导航"
    >
      <Input
        ref={searchRef}
        label="搜索页面"
        placeholder="输入页面名称…"
        value={query}
        onChange={(event) => setQuery(event.target.value)}
        onKeyDown={handleKeyDown}
        autoComplete="off"
      />
      <div className="ui-command-palette__results" role="listbox" aria-label="页面列表">
        {filteredItems.map((item, index) => (
          <button
            key={item.id || item.label}
            className="ui-command-palette__item"
            type="button"
            role="option"
            aria-selected={index === activeIndex}
            onClick={() => selectItem(item)}
            onMouseMove={() => setActiveIndex(index)}
          >
            {item.icon && <span className="ui-command-palette__icon" aria-hidden="true">{item.icon}</span>}
            <span>
              <strong>{item.label}</strong>
              {item.description && <small>{item.description}</small>}
            </span>
          </button>
        ))}
        {filteredItems.length === 0 && <p className="ui-command-palette__empty">没有匹配的页面。</p>}
      </div>
    </Dialog>
  )
}
