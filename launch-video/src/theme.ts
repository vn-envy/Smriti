// SMRITI brand system — lifted from smriti-teaser.html / smriti-landing.html
export const C = {
  ink: '#0B0F1C',
  ink2: '#121829',
  ink3: '#1A2238',
  line: '#26304A',
  line2: '#33405F',
  paper: '#E9EDF6',
  mute: '#8B94AC',
  faint: '#5D6780',
  amber: '#F4A43C',
  teal: '#52C7BE',
  violet: '#B794E0',
  rose: '#E08AA0',
  merged: '#FFD9A0',
  slate: '#4A5570',
} as const;

export const F = {
  display: "'Space Grotesk', 'Noto Sans Devanagari', sans-serif",
  body: "'Inter', 'Noto Sans Devanagari', system-ui, sans-serif",
  mono: "'JetBrains Mono', 'Noto Sans Devanagari', monospace",
  deva: "'Noto Sans Devanagari', sans-serif",
} as const;

export const FPS = 30;

// Scene boundaries (frames @30fps) — keep in sync with scripts/make-audio.py
export const SCENES = {
  coldOpen: {from: 0, dur: 240},
  infraTax: {from: 240, dur: 360},
  reveal: {from: 600, dur: 420},
  writePath: {from: 1020, dur: 420},
  badha: {from: 1440, dur: 480},
  sangama: {from: 1920, dur: 540},
  receipts: {from: 2460, dur: 360},
  honesty: {from: 2820, dur: 270},
  endCard: {from: 3090, dur: 210},
} as const;

export const TOTAL_FRAMES = 3300;

// Deterministic PRNG (mulberry32) — all "randomness" in the film is seeded.
export const mulberry32 = (seed: number) => {
  let a = seed >>> 0;
  return () => {
    a |= 0;
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
};
