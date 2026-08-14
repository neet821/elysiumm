/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  darkMode: 'class', // 启用 class 模式的暗黑主题
  theme: {
    extend: {
      colors: {
        weezer: "#189BCC",
        sunset: "#F97316",
        // New Design System Colors
        primary: {
          DEFAULT: "#2A5C8D", // Classic Blue
          hover: "#1e456b",
          dark: "#60A5FA", // Moonlight Blue for Dark Mode
        },
        bg: {
          light: "#FAFAF9", // Warm Off-white
          dark: "#0B0E14", // Midnight Blue Black
          card: "#FFFFFF",
          cardDark: "#1B1F27", // Gunmetal Grey
        },
        text: {
          main: "#1A1A1A", // Dark Grey
          mainDark: "#E2E8F0", // Silver White
          muted: "#666666",
          mutedDark: "#64748B", // Dark Silver
        },
        // 暗黑模式专用颜色
        'dark-bg': {
          DEFAULT: '#0B0E14',
          secondary: '#1B1F27',
          tertiary: '#2a2a2a',
        },
        'dark-text': {
          DEFAULT: '#E2E8F0',
          muted: '#64748B',
        }
      },
      fontFamily: {
        serif: ['"Playfair Display"', 'serif'],
        sans: ['Inter', 'sans-serif'],
      },
      backgroundImage: {
        'dark-gradient': 'linear-gradient(180deg, #0a0a0a 0%, #121212 50%, #1a1a1a 100%)',
      },
      animation: {
        'fade-in': 'fadeIn 0.5s ease-in-out',
      },
      keyframes: {
        fadeIn: {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
      },
    },
  },
  plugins: [
    require('@tailwindcss/typography'),
  ],
};
