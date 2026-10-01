// Inline SVG icons. Stroke uses currentColor so they follow the theme.
const S = { width: 22, height: 22, viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", strokeWidth: 1.8, strokeLinecap: "round" as const, strokeLinejoin: "round" as const, "aria-hidden": true };

export const Sun = () => (
  <svg {...S}>
    <circle cx="12" cy="12" r="4.2" fill="currentColor" stroke="none" />
    {[0, 45, 90, 135, 180, 225, 270, 315].map((a) => (
      <line key={a} x1="12" y1="2.6" x2="12" y2="4.6" transform={`rotate(${a} 12 12)`} />
    ))}
  </svg>
);
export const Moon = () => (
  <svg {...S}>
    <path d="M20 14.5A8.5 8.5 0 0 1 9.5 4a8.5 8.5 0 1 0 10.5 10.5Z" fill="currentColor" stroke="none" />
  </svg>
);
export const Menu = () => (
  <svg {...S} width={26}>
    <line x1="3" y1="7" x2="21" y2="7" />
    <line x1="5" y1="12" x2="21" y2="12" />
    <line x1="8" y1="17" x2="21" y2="17" />
  </svg>
);
export const Close = () => (
  <svg {...S}>
    <line x1="5" y1="5" x2="19" y2="19" />
    <line x1="19" y1="5" x2="5" y2="19" />
  </svg>
);
export const Copy = () => (
  <svg {...S} width={20} height={20}>
    <rect x="8" y="8" width="12" height="12" rx="3" />
    <path d="M16 8V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h2" />
  </svg>
);
export const Pin = () => (
  <svg {...S} width={18} height={18}>
    <path d="M9 4h6l-1 6 3 3H7l3-3-1-6Z" />
    <line x1="12" y1="13" x2="12" y2="20" />
  </svg>
);
export const Vault = () => (
  <svg {...S} width={18} height={18}>
    <rect x="4" y="5" width="16" height="14" rx="3" />
    <circle cx="12" cy="12" r="2.5" />
  </svg>
);
export const Key = () => (
  <svg {...S} width={18} height={18}>
    <circle cx="8" cy="12" r="3.5" />
    <path d="M11.5 12H20M17 12v3M20 12v2" />
  </svg>
);
export const Eye = () => (
  <svg {...S} width={18} height={18}>
    <path d="M2 12s3.5-6.5 10-6.5S22 12 22 12s-3.5 6.5-10 6.5S2 12 2 12Z" />
    <circle cx="12" cy="12" r="2.8" />
  </svg>
);

/** Remit mark: the agent (cyan dot) inside its remit (white boundary), on navy.
 *  Three primitives, so it stays legible down to a 16px favicon. Source files
 *  live in public/brand/. */
export const Mark = ({ size = 34 }: { size?: number }) => (
  <svg width={size} height={size} viewBox="0 0 48 48" aria-hidden="true">
    <rect width="48" height="48" rx="12" fill="#03222e" />
    <rect x="12.5" y="12.5" width="23" height="23" rx="6" fill="none" stroke="#ffffff" strokeWidth="3.5" />
    <circle cx="24" cy="24" r="4.6" fill="#0bbcd4" />
  </svg>
);
