import { useId, useRef } from 'react'

function safeId(value) {
  return String(value).replace(/[^a-zA-Z0-9_-]/g, '-')
}

export function Tabs({ items, label, onChange, value }) {
  const generatedId = useId().replace(/:/g, '')
  const tabRefs = useRef(new Map())
  const enabledItems = items.filter((item) => !item.disabled)
  const selectedItem = items.find((item) => item.value === value) || enabledItems[0]

  const selectAndFocus = (item) => {
    if (!item) return
    onChange(item.value)
    tabRefs.current.get(item.value)?.focus()
  }

  const handleKeyDown = (event, currentValue) => {
    const currentIndex = enabledItems.findIndex((item) => item.value === currentValue)
    let nextItem = null

    if (event.key === 'ArrowRight' || event.key === 'ArrowDown') {
      nextItem = enabledItems[(currentIndex + 1) % enabledItems.length]
    } else if (event.key === 'ArrowLeft' || event.key === 'ArrowUp') {
      nextItem = enabledItems[(currentIndex - 1 + enabledItems.length) % enabledItems.length]
    } else if (event.key === 'Home') {
      nextItem = enabledItems[0]
    } else if (event.key === 'End') {
      nextItem = enabledItems.at(-1)
    }

    if (nextItem) {
      event.preventDefault()
      selectAndFocus(nextItem)
    }
  }

  if (!selectedItem) return null

  const selectedId = safeId(selectedItem.value)
  return (
    <div className="ui-tabs">
      <div className="ui-tabs__list" role="tablist" aria-label={label}>
        {items.map((item) => {
          const itemId = safeId(item.value)
          const selected = item.value === selectedItem.value
          return (
            <button
              key={item.value}
              ref={(node) => {
                if (node) tabRefs.current.set(item.value, node)
                else tabRefs.current.delete(item.value)
              }}
              id={`${generatedId}-tab-${itemId}`}
              className="ui-tabs__tab"
              type="button"
              role="tab"
              aria-controls={`${generatedId}-panel-${itemId}`}
              aria-selected={selected}
              disabled={item.disabled}
              tabIndex={selected ? 0 : -1}
              onClick={() => onChange(item.value)}
              onKeyDown={(event) => handleKeyDown(event, item.value)}
            >
              {item.label}
            </button>
          )
        })}
      </div>
      <div
        id={`${generatedId}-panel-${selectedId}`}
        className="ui-tabs__panel"
        role="tabpanel"
        aria-labelledby={`${generatedId}-tab-${selectedId}`}
        tabIndex={0}
      >
        {selectedItem.content}
      </div>
    </div>
  )
}
