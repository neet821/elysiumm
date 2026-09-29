export function formatDate(value) {
  if (!value) return "";
  const date = new Date(value);
  return Number.isNaN(date.valueOf())
    ? String(value)
    : new Intl.DateTimeFormat("zh-CN", {
        year: "numeric",
        month: "2-digit",
        day: "2-digit",
      }).format(date);
}

export function coverUrl(item) {
  if (!item.cover) return "";
  if (/^(?:https?:|data:|\/)/i.test(item.cover)) return item.cover;
  return `/media/${encodeURIComponent(item.slug)}/${encodeURIComponent(item.cover)}`;
}

export function contentTextLength(value) {
  return String(value || "")
    .replace(/<[^>]*>/g, "")
    .replace(/[`*_#>\-[\]|]/g, "")
    .replace(/\s+/g, "").length;
}
