/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        gold:    '#ffd166',
        magenta: '#c66dd6',
        teal:    '#6fd0c5',
        ink: {
          950: '#0a0a0f',
          900: '#12121a',
          800: '#1a1a26',
        },
        hairline: 'rgba(255,240,220,0.08)',
      },
      fontFamily: {
        sans:    ['"Inter Tight"', 'system-ui', 'sans-serif'],
        mono:    ['"JetBrains Mono"', 'ui-monospace', 'monospace'],
        display: ['"Fraunces"', 'serif'],
      },
      keyframes: {
        aeriaReveal: {
          from: { opacity: '0', transform: 'translateY(10px)' },
          to:   { opacity: '1', transform: 'translateY(0)' },
        },
        statusCycle: {
          '0%':   { opacity: '0' },
          '5%':   { opacity: '1' },
          '33%':  { opacity: '1' },
          '38%':  { opacity: '0' },
          '100%': { opacity: '0' },
        },
      },
      animation: {
        'aeria-reveal': 'aeriaReveal 700ms ease-out backwards',
        'status-cycle': 'statusCycle 4200ms ease-in-out infinite backwards',
      },
    },
  },
  plugins: [],
};
