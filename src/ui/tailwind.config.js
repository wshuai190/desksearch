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
        fadeInUp: {
          '0%': { opacity: '0', transform: 'translateY(8px)' },
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
        shimmer: {
          '0%': { backgroundPosition: '-200% 0' },
          '100%': { backgroundPosition: '200% 0' },
        },
        scaleIn: {
          '0%': { opacity: '0', transform: 'scale(0.97)' },
          '100%': { opacity: '1', transform: 'scale(1)' },
        },
        glow: {
          '0%, 100%': { boxShadow: '0 0 0 1px rgba(99,102,241,0.1), 0 0 15px -3px rgba(99,102,241,0.1)' },
          '50%': { boxShadow: '0 0 0 1px rgba(99,102,241,0.2), 0 0 25px -3px rgba(99,102,241,0.2)' },
        },
        slideUp: {
          '0%': { opacity: '0', transform: 'translateY(12px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        float: {
          '0%, 100%': { transform: 'translateY(0)' },
          '50%': { transform: 'translateY(-4px)' },
        },
      },
      animation: {
        fadeIn: 'fadeIn 0.2s ease-out forwards',
        fadeInUp: 'fadeInUp 0.3s ease-out forwards',
        slideDown: 'slideDown 0.15s ease-out forwards',
        slideInRight: 'slideInRight 0.22s cubic-bezier(0.16, 1, 0.3, 1) forwards',
        shimmer: 'shimmer 1.5s ease-in-out infinite',
        scaleIn: 'scaleIn 0.15s ease-out forwards',
        glow: 'glow 2s ease-in-out infinite',
        slideUp: 'slideUp 0.35s cubic-bezier(0.16, 1, 0.3, 1) forwards',
        float: 'float 3s ease-in-out infinite',
      },
      colors: {
        dark: {
          bg: '#0f0f1a',
          surface: '#1a1a2e',
          card: '#1e1e32',
          border: '#2a2a40',
          hover: '#252540',
        },
        accent: {
          blue: '#6366f1',
          'blue-hover': '#4f46e5',
          cyan: '#22d3ee',
        },
      },
      boxShadow: {
        'search': '0 2px 12px -2px rgba(0,0,0,0.06), 0 1px 3px -1px rgba(0,0,0,0.04)',
        'search-focus': '0 0 0 1px rgba(99,102,241,0.4), 0 4px 20px -4px rgba(99,102,241,0.15), 0 2px 8px -2px rgba(0,0,0,0.06)',
        'search-dark': '0 2px 12px -2px rgba(0,0,0,0.4), 0 1px 3px -1px rgba(0,0,0,0.3)',
        'search-focus-dark': '0 0 0 1px rgba(99,102,241,0.5), 0 4px 24px -4px rgba(99,102,241,0.25)',
        'card-hover': '0 8px 24px -4px rgba(0,0,0,0.08), 0 2px 6px -1px rgba(0,0,0,0.04)',
        'card-hover-dark': '0 8px 24px -4px rgba(0,0,0,0.4), 0 2px 6px -1px rgba(0,0,0,0.3)',
        'elevated': '0 12px 40px -12px rgba(0,0,0,0.12), 0 4px 12px -2px rgba(0,0,0,0.05)',
      },
    },
  },
  plugins: [],
};
