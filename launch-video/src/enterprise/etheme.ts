// SMRITI Enterprise film — BRIGHT theme.
// The launch film was midnight-navy and contemplative. This one is a product
// demo: white studio, saturated accents, fast cuts, everything on the beat.

export const E = {
  paper: '#FFFFFF',
  paper2: '#F5F7FB',
  paper3: '#EDF1F8',
  ink: '#0B0F1C',
  ink2: '#2A3350',
  mute: '#6B7694',
  faint: '#9AA4BC',
  line: '#DFE5F0',
  amber: '#F4A43C',
  amberDeep: '#E08B18',
  teal: '#12BFB0',
  violet: '#8B5CF6',
  rose: '#F0658E',
  green: '#12B76A',
  red: '#F04438',
  blue: '#3B82F6',
} as const;

export const F = {
  display: "'Space Grotesk', 'Noto Sans Devanagari', sans-serif",
  body: "'Inter', 'Noto Sans Devanagari', system-ui, sans-serif",
  mono: "'JetBrains Mono', 'Noto Sans Devanagari', monospace",
  deva: "'Noto Sans Devanagari', sans-serif",
} as const;

export const FPS = 30;

// ——— beat grid: 90 BPM -> 20 frames/beat, 80 frames/bar. Every cut lands
// on a beat, matching scripts/make-enterprise-audio.py exactly.
export const BEAT = 20;
export const BAR = 80;
export const bars = (n: number) => n * BAR;
export const beats = (n: number) => n * BEAT;

// Act structure. The score in scripts/make-enterprise-audio.py uses the same
// bar numbers: PAIN_START=2, TURN=8, DROP=13, DROP_END=17, BREAKDOWN=28.
export const SCENES = {
  open: {from: bars(0), dur: bars(2)},        // 0–5.3s    logo snap
  // ── ACT I · the pain (music is minor and lowpass-filtered here) ──
  pain: {from: bars(2), dur: bars(4)},        // 5.3–16    kinetic type: the audit
  cost: {from: bars(6), dur: bars(2)},        // 16–21.3   the three demands
  solve: {from: bars(8), dur: bars(1)},       // 21.3–24   THE TURN (filter opens)
  // ── ACT II · the solve ──
  temporal: {from: bars(9), dur: bars(4)},    // 24–34.7   world vs knowledge time
  core: {from: bars(13), dur: bars(4)},       // 34.7–45.3 3D hero (the drop)
  receipts: {from: bars(17), dur: bars(4)},   // 45.3–56   evidence receipts
  hold: {from: bars(21), dur: bars(3)},       // 56–64     hold beats erase
  packs: {from: bars(24), dur: bars(4)},      // 64–74.7   packs + federation
  stats: {from: bars(28), dur: bars(2)},      // 74.7–80   spec sheet
  end: {from: bars(30), dur: bars(2)},        // 80–85.3   end card
} as const;

export const TOTAL_FRAMES = bars(32); // 2560 = 85.33s

// Deterministic PRNG so every render is identical.
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
