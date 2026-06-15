// Runtime theming: applies a brand palette (10 shades) derived from a single
// primary color to CSS variables consumed by Tailwind (`--brand-50..900`).
// Used by both the public landing and the authenticated app panel for full
// visual coherence. Configured by the Master admin (site-settings.theme).

export const THEME_PRESETS = {
  corporate: { label: 'Corporativo', primary: '#185FA5' },
  warm: { label: 'Cálido', primary: '#C2410C' },
  dark: { label: 'Oscuro', primary: '#111827' },
};

const DEFAULT_PRIMARY = '#185FA5';

function hexToRgb(hex) {
  let h = (hex || '').replace('#', '').trim();
  if (h.length === 3) h = h.split('').map((c) => c + c).join('');
  const n = parseInt(h, 16);
  if (Number.isNaN(n) || h.length !== 6) return [24, 95, 165];
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}

function mix([r, g, b], [r2, g2, b2], t) {
  return [
    Math.round(r + (r2 - r) * t),
    Math.round(g + (g2 - g) * t),
    Math.round(b + (b2 - b) * t),
  ];
}

// Generate a 50..900 palette from a primary color (mapped to the 500 shade).
function buildPalette(primaryHex) {
  const base = hexToRgb(primaryHex);
  const white = [255, 255, 255];
  const black = [10, 14, 22];
  return {
    50: mix(base, white, 0.92),
    100: mix(base, white, 0.84),
    200: mix(base, white, 0.66),
    300: mix(base, white, 0.46),
    400: mix(base, white, 0.22),
    500: base,
    600: mix(base, black, 0.18),
    700: mix(base, black, 0.36),
    800: mix(base, black, 0.54),
    900: mix(base, black, 0.7),
  };
}

export function resolvePrimary(theme) {
  if (!theme) return DEFAULT_PRIMARY;
  if (theme.primary) return theme.primary;
  const preset = THEME_PRESETS[theme.preset];
  return preset ? preset.primary : DEFAULT_PRIMARY;
}

export function applyTheme(theme) {
  const primary = resolvePrimary(theme);
  const palette = buildPalette(primary);
  const root = document.documentElement;
  Object.entries(palette).forEach(([shade, [r, g, b]]) => {
    root.style.setProperty(`--brand-${shade}`, `${r} ${g} ${b}`);
  });
}
