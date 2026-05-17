/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    './app/**/*.{js,ts,jsx,tsx,mdx}',
    './components/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      colors: {
        // Aligned with concept SVGs in /public/figures/.
        // 50/100 are pulled directly from the figures' soft teal washes
        // (#eef8f6 / #bdded8) so figure surfaces and UI chips read as
        // one palette. 200+ keep the original tailwind teal scale.
        primary: {
          50: '#eef8f6',
          100: '#bdded8',
          200: '#99f6e4',
          300: '#5eead4',
          400: '#2dd4bf',
          500: '#14b8a6',
          600: '#0d9488',
          700: '#0f766e',
          800: '#115e59',
          900: '#134e4a',
        },
        // Single hairline that matches every <rect stroke> in the SVGs.
        hairline: '#dbe5e8',
        surface: {
          DEFAULT: '#ffffff',
          soft: '#f7faf9',
          wash: '#eef8f6',
        },
        ink: {
          DEFAULT: '#0f172a',
          body: '#334155',
          muted: '#64748b',
          faint: '#94a3b8',
        },
        accent: {
          DEFAULT: '#b7791f',
          soft: '#fdf6e7',
        },
        // Categorical hues used by the concept SVGs. Defined here so
        // future UI chips / badges can reference the same swatches.
        mode: {
          promoter: '#0f766e',
          'promoter-soft': '#bdded8',
          intervals: '#1f6feb',
          'intervals-soft': '#d4e3fc',
          elements: '#8a4cbe',
          'elements-soft': '#e0d4f0',
          pair: '#64748b',
          'pair-soft': '#e2e8f0',
        },
        motif: {
          a: '#b7791f',
          'a-soft': '#fde9c6',
          'a-ink': '#7a4d10',
          b: '#0f766e',
          'b-soft': '#bdded8',
          'b-ink': '#134e4a',
          c: '#8a4cbe',
          'c-soft': '#e0d4f0',
          'c-ink': '#5e2d8c',
          d: '#64748b',
          'd-soft': '#e2e8f0',
          'd-ink': '#334155',
        },
      },
      fontFamily: {
        mono: [
          'ui-monospace',
          'SF Mono',
          'SFMono-Regular',
          'Menlo',
          'Consolas',
          'JetBrains Mono',
          'monospace',
        ],
      },
      borderRadius: {
        DEFAULT: '8px',
      },
      boxShadow: {
        // Single soft drop matching the SVG cardShadow filter
        // (dy=8, stdDeviation=13, #0f172a @ 7%).
        card: '0 8px 26px -8px rgba(15, 23, 42, 0.08), 0 1px 2px rgba(15, 23, 42, 0.04)',
        'card-hover': '0 14px 38px -10px rgba(15, 23, 42, 0.12), 0 1px 2px rgba(15, 23, 42, 0.05)',
      },
      transitionTimingFunction: {
        'out-expo': 'cubic-bezier(0.16, 1, 0.3, 1)',
      },
    },
  },
  plugins: [],
}
