/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  darkMode: 'class',
  theme: {
    extend: {
      keyframes: {
        fadeIn: {
          '0%': { opacity: '0', transform: 'translateY(4px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        slideDown: {
          '0%': { opacity: '0', transform: 'translateY(-8px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        slideInRight: {
          '0%': { opacity: '0', transform: 'translateX(100%)' },
          '100%': { opacity: '1', transform: 'translateX(0)' },
        },
      },
      animation: {
        fadeIn: 'fadeIn 0.2s ease-out forwards',
        slideDown: 'slideDown 0.15s ease-out forwards',
        slideInRight: 'slideInRight 0.22s cubic-bezier(0.16, 1, 0.3, 1) forwards',
      },
      colors: {
        dark: {
          bg: '#0a0a0a',
          surface: '#141414',
          card: '#1a1a1a',
          border: '#262626',
          hover: '#1a1a1a',
        },
        accent: {
          blue: '#3b82f6',
          'blue-hover': '#2563eb',
        },
      },
    },
  },
  plugins: [],
};
