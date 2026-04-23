export default function Logo({ size = 28, showText = true, white = false }) {
  const colorPrimary = white ? '#ffffff' : '#185FA5';
  const colorAccent = white ? 'rgba(255,255,255,0.55)' : '#378ADD';
  return (
    <div className="inline-flex items-center gap-2" data-testid="routiq-logo">
      <svg width={size} height={size} viewBox="0 0 64 64" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
        <defs>
          <linearGradient id={`lg-${white ? 'w' : 'd'}`} x1="0" y1="0" x2="1" y2="1">
            <stop offset="0" stopColor={colorAccent} />
            <stop offset="1" stopColor={colorPrimary} />
          </linearGradient>
        </defs>
        <rect rx="14" width="64" height="64" fill={`url(#lg-${white ? 'w' : 'd'})`} />
        <path d="M18 46 V20 h12 a8 8 0 0 1 0 16 h-6" stroke="#fff" strokeWidth="5" strokeLinecap="round" strokeLinejoin="round" fill="none"/>
        <path d="M30 36 L44 46" stroke="#fff" strokeWidth="5" strokeLinecap="round" fill="none"/>
      </svg>
      {showText && (
        <span className={`font-display font-bold tracking-tight ${white ? 'text-white' : 'text-ink-900'}`} style={{ fontSize: size * 0.82 }}>
          Routiq
        </span>
      )}
    </div>
  );
}
