import type { Config } from 'tailwindcss';

const config: Config = {
  content: [
    './src/**/*.{js,ts,jsx,tsx,mdx}',
    '../../packages/ui/src/**/*.{js,ts,jsx,tsx}',
  ],
  theme: {
    extend: {
      fontFamily: {
        pixelFont: ['"Press Start 2P"', 'monospace'],
      },
      fontSize: {
        'retro-xs': ['7px', { lineHeight: '12px' }],
        'retro-sm': ['8px', { lineHeight: '14px' }],
        'retro-base': ['10px', { lineHeight: '16px' }],
        'retro-lg': ['12px', { lineHeight: '18px' }],
      },
      colors: {
        semantic: {
          success: '#10b981',
          'success-light': '#34d399',
          'success-dark': '#047857',
          error: '#ef4444',
          'error-light': '#f87171',
          'error-dark': '#991b1b',
          warning: '#f59e0b',
          info: '#22d3ee',
        },
        // Pixelact-compatible CSS variable references (scoped under .pixelact)
        pixelact: {
          bg: 'var(--pixelact-bg, #1e293b)',
          fg: 'var(--pixelact-fg, #f8fafc)',
          border: 'var(--pixelact-border, #475569)',
          primary: 'var(--pixelact-primary, #6366f1)',
          'primary-fg': 'var(--pixelact-primary-fg, #ffffff)',
          muted: 'var(--pixelact-muted, #334155)',
          'muted-fg': 'var(--pixelact-muted-fg, #94a3b8)',
          accent: 'var(--pixelact-accent, #818cf8)',
        },
      },
      zIndex: {
        hud: '20',
        video: '30',
        backdrop: '40',
        modal: '50',
        toast: '60',
      },
      boxShadow: {
        pixel:
          '0 0 0 2px #000, 0 0 0 4px #475569, inset 0 0 0 1px rgba(255,255,255,0.08)',
        'pixel-accent':
          '0 0 0 2px #000, 0 0 0 4px #6366f1, inset 0 0 0 1px rgba(255,255,255,0.1)',
        // Pixelact 3D press effects
        'pixelact-raised':
          '2px 2px 0px 0px #000, inset -1px -1px 0px 0px rgba(0,0,0,0.3), inset 1px 1px 0px 0px rgba(255,255,255,0.15)',
        'pixelact-pressed':
          'inset 2px 2px 0px 0px rgba(0,0,0,0.3), inset -1px -1px 0px 0px rgba(255,255,255,0.1)',
      },
    },
  },
  plugins: [],
};

export default config;
