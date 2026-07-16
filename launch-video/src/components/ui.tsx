import React from 'react';
import {
  AbsoluteFill,
  Easing,
  interpolate,
  useCurrentFrame,
  useVideoConfig,
} from 'remotion';
import {C, F, TOTAL_FRAMES} from '../theme';

// ————— easing shorthands —————
export const easeOut = Easing.bezier(0.2, 0.7, 0.2, 1);
export const easeInOut = Easing.bezier(0.65, 0, 0.35, 1);

export const clamp01 = (v: number) => Math.min(1, Math.max(0, v));

/** 0→1 progress between two local frames, eased. */
export const ramp = (
  frame: number,
  from: number,
  to: number,
  easing: (t: number) => number = easeOut,
) =>
  interpolate(frame, [from, to], [0, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
    easing,
  });

// ————— film grain + vignette (as in the original teaser) —————
const GRAIN_URI =
  "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='160' height='160'%3E%3Cfilter id='n'%3E%3CfeTurbulence baseFrequency='0.9' numOctaves='2'/%3E%3C/filter%3E%3Crect width='160' height='160' filter='url(%23n)' opacity='0.6'/%3E%3C/svg%3E\")";

export const FilmChrome: React.FC<{showBrand?: boolean}> = ({showBrand}) => {
  const frame = useCurrentFrame();
  const brandIn = ramp(frame, 250, 275);
  const pct = (Math.min(frame, TOTAL_FRAMES) / TOTAL_FRAMES) * 100;
  const secs = Math.floor(frame / 30);
  const pad = (n: number) => String(Math.floor(n)).padStart(2, '0');
  return (
    <AbsoluteFill style={{pointerEvents: 'none'}}>
      {/* vignette */}
      <AbsoluteFill
        style={{
          background:
            'radial-gradient(120% 95% at 50% 45%, transparent 55%, rgba(0,0,0,.5))',
        }}
      />
      {/* grain */}
      <AbsoluteFill style={{backgroundImage: GRAIN_URI, opacity: 0.05}} />
      {/* brand tag */}
      {showBrand !== false && (
        <div
          style={{
            position: 'absolute',
            top: 36,
            left: 44,
            fontFamily: F.mono,
            fontSize: 15,
            color: C.faint,
            letterSpacing: '.14em',
            opacity: brandIn,
          }}
        >
          <span style={{color: C.mute, fontWeight: 500}}>smriti</span>{' '}
          <span style={{color: C.amber, fontFamily: F.deva}}>स्मृति</span>
          {'  ·  launch film · 1:50'}
        </div>
      )}
      {/* progress bar */}
      <div
        style={{
          position: 'absolute',
          left: 0,
          bottom: 0,
          height: 3,
          width: `${pct}%`,
          background: C.amber,
          boxShadow: '0 0 12px rgba(244,164,60,.8)',
        }}
      />
      <div
        style={{
          position: 'absolute',
          right: 44,
          bottom: 24,
          fontFamily: F.mono,
          fontSize: 13,
          color: C.faint,
          letterSpacing: '.1em',
        }}
      >
        {`0${Math.floor(secs / 60)}:${pad(secs % 60)} / 01:50`}
      </div>
    </AbsoluteFill>
  );
};

// ————— scene shell: handles its own fade in/out at the edges —————
export const Scene: React.FC<{
  children: React.ReactNode;
  fadeIn?: number;
  fadeOut?: number;
  background?: string;
}> = ({children, fadeIn = 14, fadeOut = 14, background}) => {
  const frame = useCurrentFrame();
  const {durationInFrames} = useVideoConfig();
  const a = ramp(frame, 0, fadeIn, easeInOut);
  const b = 1 - ramp(frame, durationInFrames - fadeOut, durationInFrames - 1, easeInOut);
  return (
    <AbsoluteFill style={{background, opacity: Math.min(a, b)}}>
      {children}
    </AbsoluteFill>
  );
};

// ————— frame-driven typewriter —————
export const TypeOn: React.FC<{
  text: string;
  startFrame: number;
  cps?: number; // characters per second
  caret?: boolean;
  style?: React.CSSProperties;
}> = ({text, startFrame, cps = 20, caret = true, style}) => {
  const frame = useCurrentFrame();
  const chars = clamp01(((frame - startFrame) / 30) * (cps / text.length) * text.length);
  const n = Math.max(0, Math.floor(((frame - startFrame) / 30) * cps));
  const shown = text.slice(0, Math.min(text.length, n));
  const blink = Math.floor(frame / 14) % 2 === 0;
  void chars;
  return (
    <span style={style}>
      {shown}
      {caret && frame >= startFrame - 8 && (
        <span
          style={{
            display: 'inline-block',
            width: '0.055em',
            height: '0.92em',
            background: C.amber,
            verticalAlign: '-0.12em',
            marginLeft: '0.09em',
            opacity: blink ? 1 : 0,
          }}
        />
      )}
    </span>
  );
};

// ————— rise-in text (fade + translateY) —————
export const Rise: React.FC<{
  at: number;
  dur?: number;
  children: React.ReactNode;
  style?: React.CSSProperties;
  dist?: number;
}> = ({at, dur = 22, children, style, dist = 26}) => {
  const frame = useCurrentFrame();
  const p = ramp(frame, at, at + dur);
  return (
    <div
      style={{
        opacity: p,
        transform: `translateY(${(1 - p) * dist}px)`,
        ...style,
      }}
    >
      {children}
    </div>
  );
};

export const Kicker: React.FC<{children: React.ReactNode; style?: React.CSSProperties}> = ({
  children,
  style,
}) => (
  <p
    style={{
      fontFamily: F.mono,
      fontSize: 17,
      letterSpacing: '.3em',
      textTransform: 'uppercase',
      color: C.faint,
      margin: 0,
      ...style,
    }}
  >
    {children}
  </p>
);

/** Devanagari gloss span */
export const Deva: React.FC<{children: React.ReactNode; color?: string}> = ({
  children,
  color = C.amber,
}) => <span style={{fontFamily: F.deva, color, fontWeight: 500}}>{children}</span>;
