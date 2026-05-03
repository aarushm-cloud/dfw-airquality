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
    },
  },
  plugins: [],
};
