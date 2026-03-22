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
      },
      animation: {
        fadeIn: 'fadeIn 0.2s ease-out forwards',
      },
      colors: {
        dark: {
          bg: '#0a0a0a',
          surface: '#141414',
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
