import React from 'react';
import {AbsoluteFill, Easing, interpolate, spring, useCurrentFrame, useVideoConfig} from 'remotion';
import {BEAT, E, F, FPS} from './etheme';

export const clamp01 = (v: number) => Math.min(1, Math.max(0, v));
export const easeOut = Easing.bezier(0.16, 1, 0.3, 1);      // Apple-ish settle
export const easeSnap = Easing.bezier(0.34, 1.56, 0.64, 1); // slight overshoot

export const ramp = (
  frame: number, from: number, to: number, a = 0, b = 1, easing = easeOut,
) => interpolate(frame, [from, to], [a, b], {
  extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing,
});

/** Spring keyed to the beat grid — the whole film breathes at 90 BPM. */
export const useBeatSpring = (delay = 0, damping = 14) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  return spring({frame: frame - delay, fps, config: {damping, mass: 0.7, stiffness: 180}});
};

/** 0→1 pulse that fires on every beat (subtle scale/glow accents). */
export const beatPulse = (frame: number, strength = 1) => {
  const p = (frame % BEAT) / BEAT;
  return Math.exp(-p * 7) * strength;
};

export const Studio: React.FC<{children: React.ReactNode; tint?: string}> = ({
  children, tint = E.paper,
}) => {
  const frame = useCurrentFrame();
  const drift = Math.sin(frame / 90) * 8;
  return (
    <AbsoluteFill style={{background: tint, overflow: 'hidden'}}>
      {/* soft studio gradient + faint grid, Apple product-page energy */}
      <AbsoluteFill style={{
        background:
          `radial-gradient(1200px 700px at ${50 + drift / 3}% -8%, #FFFFFF 0%, ${E.paper2} 55%, ${E.paper3} 100%)`,
      }} />
      <AbsoluteFill style={{
        backgroundImage:
          `linear-gradient(${E.line} 1px, transparent 1px), linear-gradient(90deg, ${E.line} 1px, transparent 1px)`,
        backgroundSize: '80px 80px',
        opacity: 0.5,
        transform: `translate(${drift}px, ${-drift / 2}px)`,
        maskImage: 'radial-gradient(closest-side at 50% 45%, #000 55%, transparent 100%)',
        WebkitMaskImage: 'radial-gradient(closest-side at 50% 45%, #000 55%, transparent 100%)',
      }} />
      {children}
    </AbsoluteFill>
  );
};

/** Word-by-word rise, snapped to beats. */
export const Words: React.FC<{
  text: string; size: number; weight?: number; color?: string;
  start?: number; step?: number; style?: React.CSSProperties;
}> = ({text, size, weight = 700, color = E.ink, start = 0, step = 4, style}) => {
  const frame = useCurrentFrame();
  return (
    <div style={{display: 'flex', flexWrap: 'wrap', gap: `0 ${size * 0.28}px`,
      justifyContent: 'center', ...style}}>
      {text.split(' ').map((w, i) => {
        const d = start + i * step;
        const p = ramp(frame, d, d + 14, 0, 1, easeSnap);
        return (
          <span key={`${w}-${i}`} style={{
            fontFamily: F.display, fontSize: size, fontWeight: weight, color,
            lineHeight: 1.04, letterSpacing: '-0.03em',
            opacity: p, transform: `translateY(${(1 - p) * 34}px) scale(${0.94 + p * 0.06})`,
            display: 'inline-block',
          }}>{w}</span>
        );
      })}
    </div>
  );
};

export const Kicker: React.FC<{children: React.ReactNode; color?: string; delay?: number}> = ({
  children, color = E.amberDeep, delay = 0,
}) => {
  const frame = useCurrentFrame();
  const p = ramp(frame, delay, delay + 12);
  return (
    <div style={{
      fontFamily: F.mono, fontSize: 20, letterSpacing: '0.42em', textTransform: 'uppercase',
      color, opacity: p, transform: `translateY(${(1 - p) * 12}px)`, marginBottom: 22,
    }}>{children}</div>
  );
};

/** Frosted product card — the workhorse of the film. */
export const Card: React.FC<{
  children: React.ReactNode; delay?: number; w?: number | string; accent?: string;
  style?: React.CSSProperties; lift?: number;
}> = ({children, delay = 0, w, accent = E.line, style, lift = 1}) => {
  const s = useBeatSpring(delay);
  return (
    <div style={{
      width: w, background: 'rgba(255,255,255,0.86)', backdropFilter: 'blur(18px)',
      border: `1.5px solid ${accent}`, borderRadius: 26, padding: '26px 30px',
      boxShadow: `0 ${18 * lift}px ${54 * lift}px rgba(20,30,60,${0.10 * lift}), 0 2px 6px rgba(20,30,60,0.05)`,
      opacity: s, transform: `translateY(${(1 - s) * 40}px) scale(${0.95 + s * 0.05})`,
      ...style,
    }}>{children}</div>
  );
};

export const Chip: React.FC<{
  label: string; color?: string; delay?: number; icon?: string; big?: boolean;
}> = ({label, color = E.ink2, delay = 0, icon, big}) => {
  const s = useBeatSpring(delay, 12);
  return (
    <div style={{
      display: 'inline-flex', alignItems: 'center', gap: 10,
      fontFamily: F.mono, fontSize: big ? 26 : 20, color,
      background: '#fff', border: `1.5px solid ${color}33`, borderRadius: 999,
      padding: big ? '14px 26px' : '10px 20px',
      boxShadow: '0 6px 18px rgba(20,30,60,0.07)',
      opacity: s, transform: `scale(${0.86 + s * 0.14})`,
    }}>
      {icon ? <span style={{fontSize: big ? 22 : 17}}>{icon}</span> : null}
      {label}
    </div>
  );
};

/** Big number that counts up and lands on a beat. */
export const StatBig: React.FC<{
  value: number; suffix?: string; label: string; color?: string; delay?: number;
  decimals?: number;
}> = ({value, suffix = '', label, color = E.ink, delay = 0, decimals = 0}) => {
  const frame = useCurrentFrame();
  const p = ramp(frame, delay, delay + 26, 0, 1, easeOut);
  const s = useBeatSpring(delay, 13);
  const shown = (value * p).toFixed(decimals);
  return (
    <div style={{textAlign: 'center', opacity: s, transform: `translateY(${(1 - s) * 22}px)`}}>
      <div style={{
        fontFamily: F.display, fontWeight: 700, fontSize: 92, color,
        letterSpacing: '-0.045em', lineHeight: 1,
      }}>{shown}{suffix}</div>
      <div style={{
        fontFamily: F.body, fontSize: 21, color: E.mute, marginTop: 10, fontWeight: 500,
      }}>{label}</div>
    </div>
  );
};

export const Mono: React.FC<{
  children: React.ReactNode; size?: number; color?: string; style?: React.CSSProperties;
}> = ({children, size = 22, color = E.ink2, style}) => (
  <div style={{fontFamily: F.mono, fontSize: size, color, ...style}}>{children}</div>
);

export const Deva: React.FC<{children: React.ReactNode; color?: string; size?: number}> = ({
  children, color = E.amber, size = 40,
}) => (
  <span style={{fontFamily: F.deva, color, fontSize: size, fontWeight: 600}}>{children}</span>
);

/** Whip-pan / flash transition between scenes, fired on bar boundaries. */
export const CutFlash: React.FC<{at: number; color?: string}> = ({at, color = '#fff'}) => {
  const frame = useCurrentFrame();
  const o = interpolate(frame, [at - 2, at, at + 7], [0, 0.9, 0], {
    extrapolateLeft: 'clamp', extrapolateRight: 'clamp',
  });
  if (o <= 0.001) return null;
  return <AbsoluteFill style={{background: color, opacity: o, mixBlendMode: 'screen'}} />;
};

/** Apple-style progress dots showing where we are in the demo. */
export const Progress: React.FC<{index: number; total: number}> = ({index, total}) => (
  <div style={{
    position: 'absolute', bottom: 46, left: 0, right: 0,
    display: 'flex', justifyContent: 'center', gap: 10,
  }}>
    {Array.from({length: total}).map((_, i) => (
      <div key={i} style={{
        width: i === index ? 30 : 8, height: 8, borderRadius: 999,
        background: i === index ? E.amber : E.line,
        transition: 'all 0.3s',
      }} />
    ))}
  </div>
);

/* ───────────────── typographic kit (the pain section) ───────────────── */

/** Huge kinetic word — slams in with a slight overshoot and settle. */
export const BigType: React.FC<{
  children: React.ReactNode; size?: number; delay?: number; color?: string;
  weight?: number; track?: string; style?: React.CSSProperties;
}> = ({children, size = 150, delay = 0, color = E.ink, weight = 700, track = '-0.055em', style}) => {
  const f = useCurrentFrame();
  const p = ramp(f, delay, delay + 12, 0, 1, easeSnap);
  const settle = ramp(f, delay, delay + 26, 1.14, 1, easeOut);
  return (
    <div style={{
      fontFamily: F.display, fontSize: size, fontWeight: weight, color,
      letterSpacing: track, lineHeight: 0.98, opacity: p,
      transform: `scale(${settle}) translateY(${(1 - p) * 20}px)`,
      ...style,
    }}>{children}</div>
  );
};

/** An overheard line — lands at an angle, like a note thrown on the table. */
export const Fragment: React.FC<{
  text: string; delay: number; x: number; y: number; rot?: number;
  color?: string; size?: number; accent?: string; strike?: number;
}> = ({text, delay, x, y, rot = 0, color = E.ink2, size = 30, accent, strike}) => {
  const f = useCurrentFrame();
  const s = useBeatSpring(delay, 11);
  const struck = strike !== undefined ? ramp(f, strike, strike + 10) : 0;
  return (
    <div style={{
      position: 'absolute', left: `calc(50% + ${x}px)`, top: `calc(50% + ${y}px)`,
      transform: `translate(-50%,-50%) rotate(${rot}deg) scale(${0.8 + s * 0.2})`,
      opacity: s,
    }}>
      <div style={{
        position: 'relative', fontFamily: F.body, fontSize: size, color,
        background: '#fff', borderLeft: `4px solid ${accent ?? E.line}`,
        borderRadius: 10, padding: '14px 22px', whiteSpace: 'nowrap',
        boxShadow: '0 12px 30px rgba(20,30,60,0.10)', fontStyle: 'italic',
      }}>
        “{text}”
        <div style={{
          position: 'absolute', left: 18, right: 18, top: '52%', height: 3,
          background: E.red, transform: `scaleX(${struck})`, transformOrigin: 'left',
          borderRadius: 2,
        }} />
      </div>
    </div>
  );
};

/** Rubber-stamp demand — rotates in and thumps down. */
export const Stamp: React.FC<{
  label: string; sub: string; delay: number; color?: string; rot?: number;
}> = ({label, sub, delay, color = E.red, rot = -4}) => {
  const f = useCurrentFrame();
  const p = ramp(f, delay, delay + 9, 0, 1, easeOut);
  const scale = interpolate(f, [delay, delay + 6, delay + 12], [1.7, 0.94, 1], {
    extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: easeOut,
  });
  return (
    <div style={{
      transform: `rotate(${rot}deg) scale(${scale})`, opacity: p,
      border: `4px solid ${color}`, borderRadius: 14, padding: '16px 26px',
      textAlign: 'center', background: `${color}0A`,
    }}>
      <div style={{
        fontFamily: F.display, fontSize: 40, fontWeight: 700, color,
        letterSpacing: '0.08em', lineHeight: 1,
      }}>{label}</div>
      <div style={{fontFamily: F.body, fontSize: 19, color: E.ink2, marginTop: 8}}>{sub}</div>
    </div>
  );
};

/** Text that gets struck through on a beat. */
export const Strike: React.FC<{
  children: React.ReactNode; at: number; size?: number; color?: string;
}> = ({children, at, size = 54, color = E.ink}) => {
  const f = useCurrentFrame();
  const w = ramp(f, at, at + 12, 0, 1, easeOut);
  return (
    <div style={{position: 'relative', display: 'inline-block'}}>
      <span style={{
        fontFamily: F.display, fontSize: size, fontWeight: 600, color,
        letterSpacing: '-0.02em',
      }}>{children}</span>
      <div style={{
        position: 'absolute', left: -6, right: -6, top: '54%', height: 5,
        background: E.red, transform: `scaleX(${w})`, transformOrigin: 'left',
        borderRadius: 3,
      }} />
    </div>
  );
};

/** Typewriter line for terminal-ish beats. */
export const TypeLine: React.FC<{
  text: string; delay: number; cps?: number; size?: number; color?: string;
}> = ({text, delay, cps = 34, size = 26, color = E.ink}) => {
  const f = useCurrentFrame();
  const n = Math.max(0, Math.floor(((f - delay) / FPS) * cps));
  const shown = text.slice(0, n);
  const done = n >= text.length;
  return (
    <div style={{fontFamily: F.mono, fontSize: size, color}}>
      {shown}
      {!done && f > delay ? (
        <span style={{opacity: Math.floor(f / 8) % 2 ? 1 : 0.15}}>▌</span>
      ) : null}
    </div>
  );
};

export const Brand: React.FC<{opacity?: number}> = ({opacity = 1}) => (
  <div style={{
    position: 'absolute', top: 44, left: 56, display: 'flex', alignItems: 'center',
    gap: 12, opacity,
  }}>
    <span style={{
      fontFamily: F.display, fontWeight: 700, fontSize: 26, color: E.ink,
      letterSpacing: '-0.02em',
    }}>SMRITI</span>
    <span style={{
      fontFamily: F.mono, fontSize: 14, color: E.amberDeep, background: `${E.amber}1F`,
      border: `1px solid ${E.amber}55`, borderRadius: 6, padding: '3px 9px',
      letterSpacing: '0.12em',
    }}>ENTERPRISE</span>
  </div>
);
