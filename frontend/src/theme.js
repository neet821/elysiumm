// 全站主题配置：尽量让页面、后台和工具区共用同一套底色与强调色。
export const THEME = {
  light: {
    bg: 'bg-[var(--bg-color)]',
    bgSecondary: 'bg-[var(--surface-color)]',
    text: 'text-[var(--text-dark)]',
    textMuted: 'text-[var(--text-grey)]',
    border: 'border-[var(--border-color)]',
    accent: '#2A5C8D',
    accentClass: 'text-[#2A5C8D]',
    accentBg: 'bg-[#2A5C8D]',
    accentBorder: 'border-[#2A5C8D]',
    shadow: 'shadow-stone-200/50'
  },
  dark: {
    bg: 'bg-[var(--bg-color)]',
    bgSecondary: 'bg-[var(--surface-color)]',
    text: 'text-[var(--text-dark)]',
    textMuted: 'text-[var(--text-grey)]',
    border: 'border-[var(--border-color)]',
    accent: '#60A5FA',
    accentClass: 'text-blue-400',
    accentBg: 'bg-blue-400',
    accentBorder: 'border-blue-400',
    shadow: 'shadow-black/50'
  }
};
