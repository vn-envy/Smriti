#!/usr/bin/env python3
"""
SMRITI launch film — sandbox preview renderer.

A faithful pure-Python (numpy + PIL) implementation of the Remotion film:
same storyboard, palette, timing and copy. The Remotion project renders the
master; this renders a watchable preview wherever there's no Chrome.

Usage: python3 render_preview.py --start 0 --end 300
Frames land in scripts/frames/f%05d.jpg (resumable — existing frames skipped).
"""
import argparse
import math
import os

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H = 1280, 720
SCALE = W / 1920.0  # design space is 1920×1080; all coords below are design-space
FPS = 30
TOTAL = 3300

# ———————————————————————— palette ————————————————————————
INK = (11, 15, 28)
INK2 = (18, 24, 41)
LINE = (38, 48, 74)
LINE2 = (51, 64, 95)
PAPER = (233, 237, 246)
MUTE = (139, 148, 172)
FAINT = (93, 103, 128)
AMBER = (244, 164, 60)
TEAL = (82, 199, 190)
VIOLET = (183, 148, 224)
ROSE = (224, 138, 160)
MERGED = (255, 217, 160)
SLATE = (74, 85, 112)
WHITE = (255, 255, 255)

CH_COLS = [AMBER, TEAL, VIOLET, ROSE]

# ———————————————————————— fonts ————————————————————————
GF = "/usr/share/fonts/truetype/google-fonts"
DJ = "/usr/share/fonts/truetype/dejavu"
_font_cache = {}

def font(kind, size_design):
    """kind: disp-bold/disp/disp-med/body/mono/mono-bold; size in design px"""
    size = max(8, int(round(size_design * SCALE)))
    key = (kind, size)
    if key not in _font_cache:
        path = {
            "disp-bold": f"{GF}/Poppins-Bold.ttf",
            "disp": f"{GF}/Poppins-Medium.ttf",
            "disp-med": f"{GF}/Poppins-Medium.ttf",
            "disp-reg": f"{GF}/Poppins-Regular.ttf",
            "body": f"{GF}/Poppins-Regular.ttf",
            "light": f"{GF}/Poppins-Light.ttf",
            "mono": f"{DJ}/DejaVuSansMono.ttf",
            "mono-bold": f"{DJ}/DejaVuSansMono-Bold.ttf",
        }[kind]
        _font_cache[key] = ImageFont.truetype(path, size)
    return _font_cache[key]

def X(v):  # design → device
    return v * SCALE

# ———————————————————————— easing ————————————————————————
def clamp01(x):
    return 0.0 if x < 0 else (1.0 if x > 1 else x)

def ease_out(x):
    return 1 - (1 - x) ** 3

def ease_in_out(x):
    return x * x * (3 - 2 * x)

def ease_in(x):
    return x ** 2.6

def ramp(f, a, b, ease=ease_out):
    if b <= a:
        return 1.0 if f >= b else 0.0
    return ease(clamp01((f - a) / (b - a)))

def springy(f, t0, stiff=1.0):
    """cheap spring: overshoot then settle; f,t0 in frames"""
    if f < t0:
        return 0.0
    t = (f - t0) / FPS * 6.0 * stiff
    return 1 - math.exp(-t) * math.cos(2.2 * t)

def mix(a, b, t):
    return tuple(int(round(a[i] + (b[i] - a[i]) * t)) for i in range(3))

def with_a(col, a):
    return (col[0], col[1], col[2], int(round(255 * clamp01(a))))

# ———————————————————————— deterministic rng ————————————————————————
def mulberry(seed):
    a = seed & 0xFFFFFFFF
    def rnd():
        nonlocal a
        a = (a + 0x6D2B79F5) & 0xFFFFFFFF
        t = (a ^ (a >> 15)) * (1 | a) & 0xFFFFFFFF
        t = (t + ((t ^ (t >> 7)) * (61 | t) & 0xFFFFFFFF)) ^ t
        return ((t ^ (t >> 14)) & 0xFFFFFFFF) / 4294967296
    return rnd

# ———————————————————————— text helpers ————————————————————————
def is_deva(ch):
    return "ऀ" <= ch <= "ॿ"

_deva_cache = {}
def deva_variant(fnt):
    """Poppins fallback (has Devanagari) at matching pixel size."""
    key = fnt.size
    if key not in _deva_cache:
        _deva_cache[key] = ImageFont.truetype(f"{GF}/Poppins-Regular.ttf", int(fnt.size * 0.96))
    return _deva_cache[key]

def runs(s):
    """split string into (text, deva?) runs"""
    out = []
    cur, mode = "", None
    for ch in s:
        m = is_deva(ch)
        if mode is None or m == mode:
            cur += ch
        else:
            out.append((cur, mode))
            cur = ch
        mode = m
    if cur:
        out.append((cur, mode))
    return out

def seg_width(draw, s, fnt):
    return sum(draw.textlength(r, font=(deva_variant(fnt) if dv else fnt)) for r, dv in runs(s))

def text_w(draw, s, fnt):
    return seg_width(draw, s, fnt)

def draw_runs(draw, x, y, s, fnt, fill):
    for r, dv in runs(s):
        f_ = deva_variant(fnt) if dv else fnt
        dy_ = fnt.size * 0.05 if dv else 0
        draw.text((x, y + dy_), r, font=f_, fill=fill)
        x += draw.textlength(r, font=f_)
    return x

def draw_tracked(draw, xy, s, fnt, fill, tracking=0.0, anchor_center=False):
    """letterspaced text; tracking in em fraction. Devanagari runs are drawn
    whole (letterspacing would break conjunct shaping)."""
    track = fnt.size * tracking
    pieces = []  # (text, font, width) — latin pieces are single chars
    for r, dv in runs(s):
        if dv:
            f_ = deva_variant(fnt)
            pieces.append((r, f_, draw.textlength(r, font=f_) + track))
        else:
            for ch in r:
                pieces.append((ch, fnt, draw.textlength(ch, font=fnt) + track))
    total = sum(p[2] for p in pieces) - (track if pieces else 0)
    x = xy[0] - (total / 2 if anchor_center else 0)
    for txt, f_, w_ in pieces:
        draw.text((x, xy[1]), txt, font=f_, fill=fill)
        x += w_

def draw_segments(draw, cx, y, segs, anchor="center"):
    """segs: (text, font, fill) or (text, font, fill, dy). devanagari-safe."""
    total = sum(seg_width(draw, s[0], s[1]) for s in segs)
    x = cx - total / 2 if anchor == "center" else cx
    for s in segs:
        txt, f, col = s[0], s[1], s[2]
        dy_ = (s[3] if len(s) > 3 else 0) * SCALE
        x = draw_runs(draw, x, y + dy_, txt, f, col)
    return total

def kicker(draw, cy, s, alpha, color=FAINT, y_off=0):
    if alpha <= 0.01:
        return
    fnt = font("mono", 17)
    draw_tracked(draw, (W / 2, X(cy) + y_off), s.upper(), fnt,
                 with_a(color, alpha)[:3] if alpha >= 1 else mix(INK, color, alpha),
                 tracking=0.3, anchor_center=True)

def rise_pos(f, at, dur=22, dist=26):
    p = ramp(f, at, at + dur)
    return p, (1 - p) * dist

# ———————————————————————— compose helpers ————————————————————————
_vignette = None
def get_vignette():
    global _vignette
    if _vignette is None:
        yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
        nx = (xx - W / 2) / (W * 0.60)
        ny = (yy - H * 0.45) / (H * 0.55)
        d = np.sqrt(nx * nx + ny * ny)
        v = 1.0 - 0.5 * np.clip((d - 0.72) / 0.55, 0, 1) ** 1.5
        _vignette = v[:, :, None].astype(np.float32)
    return _vignette

def blob_bg(f, cols, speed=0.45, opacity=0.5):
    """mesh-gradient-ish moving blobs, rendered small then upscaled"""
    w8, h8 = W // 10, H // 10
    yy, xx = np.mgrid[0:h8, 0:w8].astype(np.float32)
    acc = np.zeros((h8, w8, 3), np.float32)
    tt = f / FPS * speed
    P = [(0.28, 0.36, 0.55, 0.9), (0.74, 0.3, 0.5, -0.7), (0.5, 0.75, 0.6, 0.5), (0.85, 0.72, 0.45, -1.1)]
    for (bx, by, br, sp), col in zip(P, cols):
        cx = (bx + 0.12 * math.sin(tt * sp + bx * 9)) * w8
        cy = (by + 0.12 * math.cos(tt * sp * 0.8 + by * 7)) * h8
        d2 = (xx - cx) ** 2 + (yy - cy) ** 2
        g = np.exp(-d2 / (2 * (br * w8 * 0.55) ** 2))
        for c in range(3):
            acc[:, :, c] += g * col[c]
    acc = np.clip(acc, 0, 255)
    img = Image.fromarray(acc.astype(np.uint8)).resize((W, H), Image.BILINEAR)
    return np.asarray(img).astype(np.float32) * opacity

def splat_glow(pts, blur=2.2):
    """pts: list of (x_dev, y_dev, (r,g,b), alpha). additive glow layer (device px)"""
    hw, hh = W // 2, H // 2
    buf = np.zeros((hh, hw, 3), np.float32)
    if pts:
        arr = np.array([(p[0] / 2, p[1] / 2) for p in pts], np.float32)
        cols = np.array([p[2] for p in pts], np.float32)
        alps = np.array([p[3] for p in pts], np.float32)[:, None]
        xi = arr[:, 0].astype(np.int32)
        yi = arr[:, 1].astype(np.int32)
        m = (xi >= 1) & (xi < hw - 1) & (yi >= 1) & (yi < hh - 1) & (alps[:, 0] > 0.003)
        xi, yi = xi[m], yi[m]
        v = (cols[m] * alps[m])
        np.add.at(buf, (yi, xi), v)
        np.add.at(buf, (yi, xi + 1), v * 0.45)
        np.add.at(buf, (yi, xi - 1), v * 0.45)
        np.add.at(buf, (yi + 1, xi), v * 0.45)
        np.add.at(buf, (yi - 1, xi), v * 0.45)
    img = Image.fromarray(np.clip(buf, 0, 255).astype(np.uint8)).filter(
        ImageFilter.GaussianBlur(blur))
    return np.asarray(img.resize((W, H), Image.BILINEAR)).astype(np.float32)

def rounded_rect(draw, box, radius, fill=None, outline=None, width=1):
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)

# ———————————————————————— 3D mini-engine ————————————————————————
def look_at(eye, target, up=(0, 1, 0)):
    eye = np.array(eye, np.float32)
    fwd = np.array(target, np.float32) - eye
    fwd /= np.linalg.norm(fwd)
    right = np.cross(fwd, np.array(up, np.float32))
    right /= np.linalg.norm(right)
    up2 = np.cross(right, fwd)
    return eye, right, up2, fwd

def project(pts, eye, right, up2, fwd, fov_deg=55.0):
    """pts (N,3) → xs, ys (design px), depth"""
    rel = pts - eye
    xv = rel @ right
    yv = rel @ up2
    zv = rel @ fwd  # + into screen
    zv = np.maximum(zv, 0.05)
    f_ = (1080 / 2) / math.tan(math.radians(fov_deg / 2))
    xs = 1920 / 2 + xv * f_ / zv
    ys = 1080 / 2 - yv * f_ / zv
    return xs, ys, zv

# ———————————————————————— scene state (precomputed, seeded) ————————————————————————
def cubic(p0, p1, p2, p3, t):
    u = 1 - t
    return (u**3) * p0 + 3 * (u**2) * t * p1 + 3 * u * (t**2) * p2 + (t**3) * p3

MERGE_T = 0.62
S_SAMP = 560

def build_paths():
    CONF = np.array([2.6, 0.25, 0.0], np.float32)
    ex = [CONF, np.array([6.5, 0.9, 0.7]), np.array([10.5, -0.4, -0.5]), np.array([16, 0.2, 0.0])]
    chans = [
        [np.array([-15, 4.7, -2.0]), np.array([-7, 4.0, 2.5]), np.array([-2, 1.6, -1.5]), CONF],
        [np.array([-15, 1.9, 2.6]), np.array([-8, -0.6, -2.5]), np.array([-2.5, 1.2, 2.0]), CONF],
        [np.array([-15, -2.3, -2.6]), np.array([-7, -1.4, 2.0]), np.array([-2, -1.4, -2.0]), CONF],
        [np.array([-15, -4.9, 1.6]), np.array([-8, -4.0, -2.0]), np.array([-2.5, -0.8, 1.6]), CONF],
    ]
    SPLIT = int(S_SAMP * MERGE_T)
    paths = []
    for c in chans:
        pts = [cubic(c[0], c[1], c[2], c[3], i / (SPLIT - 1)) for i in range(SPLIT)]
        pts += [cubic(ex[0], ex[1], ex[2], ex[3], i / (S_SAMP - SPLIT - 1)) for i in range(S_SAMP - SPLIT)]
        paths.append(np.stack(pts).astype(np.float32))
    return paths

_PATHS = build_paths()

def smoothstep(a, b, x):
    t = clamp01((x - a) / (b - a))
    return t * t * (3 - 2 * t)

def spread_at(t):
    if t < MERGE_T:
        return 1.05 - 0.8 * smoothstep(0.4, MERGE_T, t)
    return 0.32 + 0.4 * smoothstep(MERGE_T, 1.0, t)

def make_river_particles(n=3600, seed=42):
    rnd = mulberry(seed)
    meta = []
    for i in range(n):
        off = np.array([rnd() * 2 - 1, rnd() * 2 - 1, rnd() * 2 - 1], np.float32)
        off /= (np.linalg.norm(off) + 1e-6)
        meta.append((i % 4, rnd(), 0.018 + rnd() * 0.034, off, rnd() ** 1.6, rnd() * 1000, 1.1 + rnd() * 1.9))
    return meta

_RIVER = make_river_particles()

def make_motes(seed=108, n=90):
    rnd = mulberry(seed)
    return [(rnd() * 1920, rnd() * 1080, 1 + rnd() * 2.2, 0.06 + rnd() * 0.22,
             rnd() * math.pi * 2, 0.25 + rnd() * 0.75) for _ in range(n)]

_MOTES = make_motes()

def make_halo(seed=2026, n=200):
    rnd = mulberry(seed)
    pts = []
    for _ in range(n):
        r = 2.3 + rnd() * 2.6
        th = rnd() * math.pi * 2
        ph = math.acos(2 * rnd() - 1)
        pts.append((r * math.sin(ph) * math.cos(th), r * math.sin(ph) * math.sin(th) * 0.7, r * math.cos(ph)))
    return np.array(pts, np.float32)

_HALO = make_halo()

# ————————————————————————————————————————————————————————————————
# SCENES — local frame l, draw onto (arr float32 canvas, draw PIL)
# ————————————————————————————————————————————————————————————————

def type_count(l, start, cps, n):
    return max(0, min(n, int((l - start) / FPS * cps)))

def s1_cold_open(l, arr, img, draw):
    dim = 1 - ramp(l, 214, 239) * 0.35
    # motes
    pts = []
    for (mx, my, r, drift, ph, dm) in _MOTES:
        y = ((my - l * drift) % 1120 + 1120) % 1120 - 20
        tw = 0.5 + 0.5 * math.sin(l * 0.03 + ph)
        a = 0.16 * dm * (0.4 + 0.6 * tw)
        pts.append((X(mx + math.sin(l * 0.01 + ph) * 14), X(y), (140, 156, 200), a * 2.2))
    arr += splat_glow(pts, blur=1.6)
    # kicker
    p, dy = rise_pos(l, 10)
    kicker(draw, 330, "july 2026 · an open-source release", p * dim, y_off=dy * SCALE)
    # headline typed
    s = "agents forget."
    n = type_count(l, 26, 13, len(s))
    fnt = font("disp", 108)
    shown = s[:n]
    tw_ = draw.textlength(shown, font=fnt)
    caret = "▎" if (l // 14) % 2 == 0 and l >= 18 else ""
    draw.text((W / 2 - tw_ / 2, X(430)), shown, font=fnt, fill=mix(INK, PAPER, dim))
    if caret and n < len(s) + 4:
        draw.text((W / 2 + tw_ / 2 + 2, X(432)), "|", font=fnt, fill=mix(INK, AMBER, dim))
    # subline
    p2, dy2 = rise_pos(l, 128, 26)
    if p2 > 0:
        f2 = font("disp-reg", 42)
        col = mix(INK, MUTE, p2 * dim)
        colr = mix(INK, ROSE, p2 * dim)
        draw_segments(draw, W / 2, X(596) + dy2 * SCALE, [
            ("every session starts from ", f2, col), ("zero", f2, colr), (".", f2, col)])

def s2_infra_tax(l, arr, img, draw):
    SLABS = [
        ("postgres + pgvector", "to run"), ("neo4j", "to version-match"),
        ("qdrant", "to keep alive"), ("redis", "to babysit"),
        ("docker compose", "to debug"), ("a cloud account", "to trust"),
        ("$249/mo pro tier", "to unlock graph"),
    ]
    SLAB_H, GAP, D0, STEP = 82, 12, 40, 26
    shake = 0.0
    for i in range(len(SLABS)):
        land = D0 + i * STEP + 12
        if l >= land:
            dt = l - land
            shake += math.exp(-dt * 0.28) * math.sin(dt * 1.7) * 7
    zoom = 1 + (0.86 - 1) * ramp(l, D0, D0 + 7 * STEP, ease_in_out)
    implode = ramp(l, 300, 336, ease_in)
    scale = zoom * (1 - implode)
    flick = 1.0 if not (262 <= l < 292) else (1.0 if (l // 3) % 2 == 0 else 0.55)
    p, dy = rise_pos(l, 8)
    kicker(draw, 96, "the usual fix is infrastructure", p, y_off=dy * SCALE)

    tower_h = len(SLABS) * (SLAB_H + GAP)
    cy0 = 1080 / 2 + 30
    if scale > 0.02:
        layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ld = ImageDraw.Draw(layer)
        for i, (label, tag) in enumerate(SLABS):
            t0 = D0 + i * STEP
            if l < t0:
                continue
            drop = min(1.0, springy(l, t0, 1.15))
            y_rel = (len(SLABS) - 1 - i) * (SLAB_H + GAP) - tower_h / 2
            fall = (1 - drop) * -560
            heat = i / (len(SLABS) - 1)
            top = cy0 + y_rel + fall
            box = [X(1920 / 2 - 310 + shake), X(top), X(1920 / 2 + 310 + shake), X(top + SLAB_H)]
            bcol = mix(LINE2, (224, 138, 160), 0.45) if heat > 0.55 else LINE2
            rounded_rect(ld, box, int(X(14)), fill=(*INK2, int(255 * flick)), outline=(*bcol, int(255 * flick)), width=max(1, int(X(1.5))))
            ld.text((X(1920 / 2 - 280 + shake), X(top + 24)), label, font=font("mono", 25), fill=(*PAPER, int(255 * flick)))
            tagf = font("mono", 15)
            tw_ = ld.textlength(tag, font=tagf)
            tcol = ROSE if heat > 0.55 else FAINT
            ld.text((X(1920 / 2 + 280 + shake) - tw_, X(top + 32)), tag, font=tagf, fill=(*tcol, int(255 * flick)))
        if scale < 0.999:
            nw = max(2, int(W * scale))
            nh = max(2, int(H * scale))
            lay2 = layer.resize((nw, nh), Image.BILINEAR).rotate(implode * 14, expand=False)
            layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            layer.paste(lay2, ((W - nw) // 2, (H - nh) // 2), lay2)
        img.paste(layer, (0, 0), layer)

    # caption
    p3, dy3 = rise_pos(l, 236)
    if p3 > 0 and implode < 0.98:
        a = p3 * (1 - implode)
        f3 = font("mono", 20)
        col = mix(INK, MUTE, a)
        draw_segments(draw, W / 2, X(942) + dy3 * SCALE, [
            ("a cluster to keep alive — before your agent remembers ", f3, col),
            ("one fact", f3, mix(INK, ROSE, a))])
    # energy converging into a point as the tower implodes
    if implode > 0.02 and implode < 1.0:
        rnd = mulberry(555)
        pts = []
        for _ in range(90):
            ang = rnd() * math.pi * 2
            r0 = 320 + rnd() * 420
            rr = r0 * (1 - implode) * (0.4 + 0.6 * rnd())
            a = 0.5 + implode * 1.6
            pts.append((W / 2 + math.cos(ang + implode * 2.4) * rr * SCALE,
                        H / 2 + math.sin(ang + implode * 2.4) * rr * SCALE * 0.8,
                        AMBER, a))
        arr += splat_glow(pts, blur=1.8)
    # flash: tight bright amber bloom that grows and dies
    phase = clamp01((l - 326) / 32)
    bright = float(np.interp(l, [326, 336, 344, 358], [0, 1.0, 0.75, 0]))
    if bright > 0.01:
        sigma = (30 + 780 * phase) * SCALE
        yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
        d2 = (xx - W / 2) ** 2 + (yy - H / 2) ** 2
        g = np.exp(-d2 / (2 * sigma * sigma))[:, :, None]
        core = np.exp(-d2 / (2 * (sigma * 0.28) ** 2))[:, :, None]
        arr += (g * np.array(AMBER, np.float32)[None, None, :] * 0.9 +
                core * np.array((255, 236, 200), np.float32)[None, None, :]) * bright

def draw_cube(arr, img, draw, l):
    bloom = min(1.0, springy(l, 16, 0.8))
    if bloom <= 0.01:
        return
    rotY = l * 0.011
    rotX = 0.32 + math.sin(l * 0.008) * 0.06
    bob = math.sin(l * 0.045) * 0.09
    z_toward = np.interp(l, [0, 420], [0, 0.9])
    center = np.array([0, 1.02 + bob, z_toward], np.float32)
    s = 0.60 * bloom
    vs = []
    for dx in (-1, 1):
        for dy in (-1, 1):
            for dz in (-1, 1):
                vs.append((dx * s, dy * s, dz * s))
    vs = np.array(vs, np.float32)
    cy, sy = math.cos(rotY), math.sin(rotY)
    cx_, sx_ = math.cos(rotX), math.sin(rotX)
    Ry = np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]], np.float32)
    Rx = np.array([[1, 0, 0], [0, cx_, -sx_], [0, sx_, cx_]], np.float32)
    vw = vs @ Ry.T @ Rx.T + center
    eye, right, up2, fwd = look_at((0, 0.35, 6.6), (0, 0.62, 0))
    xs, ys, zs = project(vw, eye, right, up2, fwd, 42)
    # faces (painter's)
    FACES = [(0, 1, 3, 2), (4, 5, 7, 6), (0, 1, 5, 4), (2, 3, 7, 6), (0, 2, 6, 4), (1, 3, 7, 5)]
    order = sorted(FACES, key=lambda f_: -np.mean([zs[i] for i in f_]))
    light = np.array([0.5, 0.6, 0.62])
    for f_ in order:
        pts3 = vw[list(f_)]
        n = np.cross(pts3[1] - pts3[0], pts3[2] - pts3[0])
        n = n / (np.linalg.norm(n) + 1e-6)
        lum = 0.55 + 0.45 * abs(float(n @ light))
        col = mix(INK2, (36, 48, 78), lum)
        poly = [(X(xs[i]), X(ys[i])) for i in f_]
        draw.polygon(poly, fill=col)
    # edges: crisp amber lines + a soft additive underglow
    E = [(0, 1), (1, 3), (3, 2), (2, 0), (4, 5), (5, 7), (7, 6), (6, 4), (0, 4), (1, 5), (3, 7), (2, 6)]
    pts = []
    edge_col = mix(INK, AMBER, 0.9 * min(1.0, bloom))
    for a, b in E:
        draw.line([X(xs[a]), X(ys[a]), X(xs[b]), X(ys[b])], fill=edge_col, width=max(1, int(X(2.2))))
        for tt in np.linspace(0, 1, 14):
            px = xs[a] + (xs[b] - xs[a]) * tt
            py = ys[a] + (ys[b] - ys[a]) * tt
            pts.append((X(px), X(py), AMBER, 0.16))
    # core glow + halo
    cxs, cys, _ = project(center[None, :], eye, right, up2, fwd, 42)
    core = 1.6 + math.sin(l * 0.09) * 0.5
    for rr, aa in [(0, 7.0 * core), (2, 3.6 * core), (4, 1.8 * core)]:
        pts.append((X(cxs[0]), X(cys[0]) + rr, MERGED, aa))
    hal = _HALO @ Ry.T * 0.72 + center
    hx, hy, hz = project(hal, eye, right, up2, fwd, 42)
    for i in range(len(hx)):
        pts.append((X(hx[i]), X(hy[i]), MERGED, 0.28 * bloom))
    arr += splat_glow(pts, blur=1.7)

def s3_reveal(l, arr, img, draw):
    arr += blob_bg(l, [(11, 15, 28), (14, 22, 44), (20, 27, 46), (52, 38, 18)], speed=0.45, opacity=0.4)
    draw_cube(arr, img, draw, l)
    p, dy = rise_pos(l, 40)
    kicker(draw, 92, "smriti's fix", p, y_off=dy * SCALE)
    # headline
    p1, d1 = rise_pos(l, 64, 26)
    if p1 > 0:
        fh = font("disp", 92)
        col = mix(INK, PAPER, p1)
        draw_segments(draw, W / 2, X(560) + d1 * SCALE, [
            ("one ", fh, col), ("SQLite", fh, mix(INK, AMBER, p1)), (" file.", fh, col)])
    p2, d2 = rise_pos(l, 118, 24)
    if p2 > 0:
        f2 = font("mono", 21)
        draw_tracked(draw, (W / 2, X(700) + d2 * SCALE), "no postgres · no neo4j · no docker · no cloud account",
                     f2, mix(INK, MUTE, p2), tracking=0.04, anchor_center=True)
    p3, d3 = rise_pos(l, 210, 26)
    if p3 > 0:
        fw_ = font("disp-bold", 76)
        fd = font("disp", 58)
        draw_segments(draw, W / 2, X(772) + d3 * SCALE, [
            ("smriti", fw_, mix(INK, PAPER, p3)), ("  स्मृति", fd, mix(INK, AMBER, p3))])
    p4, d4 = rise_pos(l, 244, 24)
    if p4 > 0:
        f4 = font("mono", 17)
        draw_tracked(draw, (W / 2, X(886) + d4 * SCALE), 'sanskrit · "that which is remembered"',
                     f4, mix(INK, FAINT, p4), tracking=0.08, anchor_center=True)
    p5, d5 = rise_pos(l, 300, 26)
    if p5 > 0:
        f5 = font("disp-reg", 40)
        col = mix(INK, MUTE, p5)
        draw_segments(draw, W / 2, X(936) + d5 * SCALE, [
            ("memory that knows ", f5, col), ("when", f5, mix(INK, AMBER, p5)), (".", f5, col)])
    infl = np.interp(l, [0, 18], [1, 0])
    if infl > 0.01:
        yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
        d2_ = ((xx - W / 2) ** 2 + (yy - H / 2) ** 2) / (W * 0.6) ** 2
        g = np.exp(-d2_ * 2.2)[:, :, None]
        arr += g * np.array(MERGED, np.float32)[None, None, :] * infl * 0.9

def s4_write_path(l, arr, img, draw):
    p, dy = rise_pos(l, 8)
    kicker(draw, 92, "the write path · named by nyaya, two millennia early", p, y_off=dy * SCALE)
    p1, d1 = rise_pos(l, 30, 26)
    if p1 > 0:
        fh = font("disp", 66)
        col = mix(INK, PAPER, p1)
        draw_segments(draw, W / 2, X(150) + d1 * SCALE, [
            ("experience leaves ", fh, col), ("impressions", fh, mix(INK, AMBER, p1)), (".", fh, col)])
    # messages
    MSGS = ['"I moved to Bengaluru on June 1st."', '"Starting the new role next week."',
            '"Remind me about the housewarming."']
    for i, m in enumerate(MSGS):
        t0 = 58 + i * 14
        fly = ramp(l, t0, t0 + 46)
        if fly <= 0:
            continue
        x = 240 + (116 + 40) * fly + 120
        fade = 1.0 if fly < 0.85 else 1 - (fly - 0.85) / 0.15
        a = min(ramp(l, t0 - 6, t0 + 6), fade)
        if a <= 0.01:
            continue
        fm = font("mono", 17)
        top = 316 + i * 52
        wbox = draw.textlength(m, font=fm) + X(32)
        rounded_rect(draw, [X(x), X(top), X(x) + wbox, X(top + 42)], int(X(10)),
                     fill=mix(INK, INK2, a), outline=mix(INK, LINE, a), width=1)
        draw.text((X(x + 16), X(top + 9)), m, font=fm, fill=mix(INK, MUTE, a))
    # stations
    ST = [
        (90, "anubhava", "अनुभव", "EXPERIENCE", "episodic log — append-only,\nembedded, FTS-indexed", TEAL),
        (150, "grahana", "ग्रहण", "EXTRACTION", "one LLM call per session,\ninto atomic facts", VIOLET),
        (210, "samskara", "संस्कार", "IMPRESSION", "the consolidated\nfact store", AMBER),
    ]
    total_w = 3 * 380 + 2 * 84
    x0 = (1920 - total_w) / 2
    for i, (at, name, deva, en, desc, colc) in enumerate(ST):
        pop = min(1.0, springy(l, at))
        if l < at:
            continue
        sc = 0.7 + 0.3 * pop
        bx = x0 + i * (380 + 84)
        by = 500 + (1 - pop) * 24
        bw, bh = 380, 172
        cx = bx + bw / 2
        cyy = by + bh / 2
        bw2, bh2 = bw * sc, bh * sc
        box = [X(cx - bw2 / 2), X(cyy - bh2 / 2), X(cx + bw2 / 2), X(cyy + bh2 / 2)]
        rounded_rect(draw, box, int(X(18)), fill=INK2, outline=LINE2, width=1)
        draw.line([box[0], box[1] + 2, box[2], box[1] + 2], fill=colc, width=max(2, int(X(3))))
        draw.text((X(bx + 28), X(by + 20)), name, font=font("disp", 34), fill=PAPER)
        nw_ = draw.textlength(name, font=font("disp", 34))
        draw.text((X(bx + 28) + nw_ + X(14), X(by + 30)), deva, font=font("disp-reg", 26), fill=colc)
        draw_tracked(draw, (X(bx + 28), X(by + 72)), en, font("mono", 14), colc, tracking=0.14)
        for j, ln in enumerate(desc.split("\n")):
            draw.text((X(bx + 28), X(by + 102 + j * 26)), ln, font=font("body", 17.5), fill=MUTE)
        if i < 2:
            nxt = ST[i + 1][0]
            aA = ramp(l, nxt - 10, nxt + 6)
            if aA > 0.01:
                ax = bx + bw + 18
                draw.text((X(ax), X(by + 70)), "─▸", font=font("mono", 34), fill=mix(INK, FAINT, aA))
    # fact chips
    FACTS = [("user", "lives_in", "Bengaluru", 268), ("user", "moved_on", "2026-06-01", 290),
             ("user", "has_event", "housewarming", 312)]
    fm = font("mono", 16.5)
    widths = []
    for s_, p_, o_, _ in FACTS:
        seg = f"{s_} → {p_} → {o_}"
        widths.append(draw.textlength(seg, font=fm) + X(40))
    totw = sum(widths) + X(18) * 2
    xx0 = W / 2 - totw / 2
    for (s_, p_, o_, at), w_ in zip(FACTS, widths):
        if l >= at:
            pop = min(1.0, springy(l, at, 1.3))
            box = [xx0, X(756), xx0 + w_, X(756 + 46)]
            rounded_rect(draw, box, int(X(23)), fill=(31, 27, 20), outline=(122, 90, 44), width=1)
            tx = xx0 + X(20)
            for seg, colc in [(s_, PAPER), (" → ", FAINT), (p_, AMBER), (" → ", FAINT), (o_, PAPER)]:
                draw.text((tx, X(766)), seg, font=fm, fill=colc)
                tx += draw.textlength(seg, font=fm)
        xx0 += w_ + X(18)
    p6, d6 = rise_pos(l, 352)
    if p6 > 0:
        f6 = font("mono", 19)
        col = mix(INK, MUTE, p6)
        draw_segments(draw, W / 2, X(946) + d6 * SCALE, [
            ("facts ", f6, col), ("and", f6, mix(INK, AMBER, p6)),
            (" raw episodes stay first-class — precision, with a recall safety net", f6, col)])

def s5_badha(l, arr, img, draw):
    SUP = 130
    superseded = l >= SUP
    shrink = ramp(l, SUP, SUP + 30)
    a_to = 0.97 + (0.5 - 0.97) * shrink
    pc, dyc = rise_pos(l, 12, 24)
    if pc <= 0:
        return
    cw = 1080
    chh = 356 + 204 * ramp(l, 226, 250)  # card grows to make room for the payoff
    cx0 = (1920 - cw) / 2
    cy0 = (1080 - 560) / 2 - 40 + dyc
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ld = ImageDraw.Draw(layer)
    rounded_rect(ld, [X(cx0), X(cy0), X(cx0 + cw), X(cy0 + chh)], int(X(22)),
                 fill=(*INK2, int(255 * pc)), outline=(*LINE, int(255 * pc)), width=1)
    img.paste(layer, (0, 0), layer)
    # query line typed
    q = 'mem.context("where does the user live?")'
    n = type_count(l, 26, 26, len(q))
    fm = font("mono", 20)
    draw.text((X(cx0 + 56), X(cy0 + 44)), "query · ", font=fm, fill=FAINT)
    off = draw.textlength("query · ", font=fm)
    draw.text((X(cx0 + 56) + off, X(cy0 + 44)), q[:n], font=fm, fill=PAPER)

    def fact_row(y, text, active, vis, badge):
        if vis <= 0.01:
            return
        dot = AMBER if active else SLATE
        draw.ellipse([X(cx0 + 58), X(y + 12), X(cx0 + 58 + 13), X(y + 25)], fill=mix(INK2, dot, vis))
        tcol = WHITE if active else FAINT
        fb = font("body", 31)
        draw.text((X(cx0 + 92), X(y)), text, font=fb, fill=mix(INK2, tcol, vis))
        tw_ = draw.textlength(text, font=fb)
        bx = cx0 + 92 + tw_ / SCALE + 22
        fbg = font("mono", 14.5)
        bw_ = draw.textlength(badge, font=fbg) + X(28)
        if active:
            rounded_rect(draw, [X(bx), X(y + 6), X(bx) + bw_, X(y + 40)], int(X(8)), fill=mix(INK2, AMBER, vis))
            draw.text((X(bx + 14), X(y + 13)), badge, font=fbg, fill=INK)
        else:
            rounded_rect(draw, [X(bx), X(y + 6), X(bx) + bw_, X(y + 40)], int(X(8)), outline=mix(INK2, LINE2, vis), width=1)
            draw.text((X(bx + 14), X(y + 13)), badge, font=fbg, fill=mix(INK2, FAINT, vis))

    def window_bar(y, frm, to, active, vis, drawp):
        if vis <= 0.01:
            return
        bx0, bx1 = cx0 + 92, cx0 + cw - 56
        rounded_rect(draw, [X(bx0), X(y), X(bx1), X(y + 9)], int(X(4)), fill=INK, outline=LINE, width=1)
        wfull = bx1 - bx0
        x_a = bx0 + frm * wfull
        x_b = bx0 + frm * wfull + (to - frm) * wfull * drawp
        if x_b > x_a:
            col = AMBER if active else SLATE
            rounded_rect(draw, [X(x_a), X(y + 1), X(x_b), X(y + 8)], int(X(3)), fill=mix(INK, col, vis))

    yA = cy0 + 108
    badgeA = "SUPERSEDED · 2026-06-01" if superseded else "CURRENT"
    fact_row(yA, "user lives in Hyderabad", not superseded, ramp(l, 56, 70), badgeA)
    window_bar(yA + 56, 0.03, a_to, not superseded, ramp(l, 62, 76), ramp(l, 62, 92))
    yB = yA + 100
    fact_row(yB, "user lives in Bengaluru", superseded, ramp(l, SUP, SUP + 16), "CURRENT")
    window_bar(yB + 56, 0.5, 0.97, superseded, ramp(l, SUP + 4, SUP + 18), ramp(l, SUP + 4, SUP + 40))

    # divider + QA
    aQ = ramp(l, 236, 254)
    if aQ > 0.01:
        draw.line([X(cx0 + 56), X(cy0 + 388), X(cx0 + cw - 56), X(cy0 + 388)], fill=mix(INK2, LINE, aQ), width=1)
        fq = font("mono", 22)
        a1 = ramp(l, 240, 256)
        if a1 > 0:
            tx = X(cx0 + 56)
            for seg, colc in [('"where now?"', PAPER), ("  →  ", FAINT), ("Bengaluru", AMBER)]:
                draw.text((tx, X(cy0 + 416)), seg, font=fq, fill=mix(INK2, colc, a1))
                tx += draw.textlength(seg, font=fq)
        a2 = ramp(l, 292, 308)
        if a2 > 0:
            tx = X(cx0 + 56)
            for seg, colc in [('"before June?"', PAPER), ("  →  ", FAINT), ("Hyderabad", AMBER),
                              ("   · one store, both answers", FAINT)]:
                draw.text((tx, X(cy0 + 468)), seg, font=fq, fill=mix(INK2, colc, a2))
                tx += draw.textlength(seg, font=fq)
    # captions (anchored to the card's final footprint so they don't drift)
    cap_base = (1080 - 560) / 2 - 40 + 560
    p2, d2 = rise_pos(l, 190, 24)
    if p2 > 0:
        f2 = font("mono", 20)
        yy_ = X(cap_base + 38) + d2 * SCALE
        draw_segments(draw, W / 2, yy_, [
            ("badha बाध", f2, mix(INK, AMBER, p2)), (" — superseded, ", f2, mix(INK, MUTE, p2)),
            ("never deleted", f2, mix(INK, PAPER, p2))])
    p3, d3 = rise_pos(l, 392, 26)
    if p3 > 0:
        f3 = font("disp-reg", 30)
        yy_ = X(cap_base + 92) + d3 * SCALE
        draw_segments(draw, W / 2, yy_, [
            ("correction is an ", f3, mix(INK, MUTE, p3)), ("event in time", f3, mix(INK, AMBER, p3)),
            (" — not an overwrite.", f3, mix(INK, MUTE, p3))])

def s6_sangama(l, arr, img, draw):
    time = l / FPS
    # camera
    z = np.interp(l, [0, 540], [17, 15.2])
    eye, right, up2, fwd = look_at(
        (math.sin(time * 0.07) * 0.5, math.cos(time * 0.09) * 0.3, z), (0.8, 0, 0))
    # pulses
    uPulse = 2.0
    for p0 in (120, 300):
        if l >= p0:
            pp = (l - p0) / FPS * 0.36
            if pp <= 1.3:
                uPulse = pp
    # particles
    pts_glow = []
    group_off = np.array([2.4, -0.7, 0.0], np.float32)
    n = len(_RIVER)
    P = np.empty((n, 3), np.float32)
    tvals = np.empty(n, np.float32)
    sizes = np.empty(n, np.float32)
    chs = np.empty(n, np.int32)
    for i, (ch, t0, sp, off, offR, seed, asize) in enumerate(_RIVER):
        tt = (t0 + time * sp) % 1.0
        path = _PATHS[ch]
        f_ = tt * (S_SAMP - 1)
        i0 = int(f_)
        i1 = min(S_SAMP - 1, i0 + 1)
        fr = f_ - i0
        base = path[i0] * (1 - fr) + path[i1] * fr
        sprd = spread_at(tt) * offR
        wob = 0.16 * math.sin(time * 0.9 + seed)
        P[i] = base + off * sprd + np.array([wob * off[1], wob * off[2], 0], np.float32)
        tvals[i] = tt
        sizes[i] = asize
        chs[i] = ch
    P += group_off
    xs, ys, zs = project(P, eye, right, up2, fwd, 55)
    merged_m = np.clip((tvals - MERGE_T) / 0.05, 0, 1)
    pulse_m = np.clip(1 - np.abs(tvals - uPulse) / 0.035, 0, 1)
    fog = np.exp(-0.020 * np.maximum(zs - 5, 0) ** 1.3)
    base_cols = np.array([CH_COLS[c] for c in chs], np.float32)
    mcol = np.array(MERGED, np.float32)
    cols = base_cols * (1 - merged_m[:, None] * 0.75) + mcol[None, :] * (merged_m[:, None] * 0.75)
    cols = cols * (1 + pulse_m[:, None] * 1.2)
    alph = (0.85 + merged_m * 0.2 + pulse_m * 0.9) * fog
    okm = (xs > -50) & (xs < 1970) & (ys > -50) & (ys < 1130)
    for i in np.nonzero(okm)[0]:
        pts_glow.append((X(xs[i]), X(ys[i]), tuple(np.clip(cols[i], 0, 255)), float(alph[i])))
    # badha pairs in depth
    rnd = mulberry(99)
    for _ in range(7):
        cx = (rnd() * 2 - 1) * 16
        cyv = (rnd() * 2 - 1) * 8
        cz = -7 - rnd() * 9
        dx = 0.5 + rnd() * 0.9
        dyv = (rnd() * 2 - 1) * 0.5
        phase = rnd() * 10
        period = 6 + rnd() * 5
        ph = ((time + phase) % period) / period
        sw = smoothstep(0.45, 0.58, ph)
        A = np.array([cx - dx / 2, cyv - dyv / 2, cz], np.float32)
        B = np.array([cx + dx / 2, cyv + dyv / 2, cz], np.float32)
        pxy = project(np.stack([A, B]), eye, right, up2, fwd, 55)
        ca = mix(SLATE, AMBER, 1 - sw)
        cb = mix(SLATE, AMBER, sw)
        pts_glow.append((X(pxy[0][0]), X(pxy[1][0]), ca, 0.5))
        pts_glow.append((X(pxy[0][1]), X(pxy[1][1]), cb, 0.5))
    # ambient motes 3d
    rndm = mulberry(7)
    for _ in range(240):
        mx = (rndm() * 2 - 1) * 26
        myv = (rndm() * 2 - 1) * 14
        mz = -3 - rndm() * 14
        pxy = project(np.array([[mx, myv, mz]], np.float32), eye, right, up2, fwd, 55)
        a = 0.10 + 0.10 * math.sin(time * 0.6 + rndm() * 700)
        pts_glow.append((X(pxy[0][0]), X(pxy[1][0]), (140, 158, 204), a))
    arr += splat_glow(pts_glow, blur=2.0)

    # overlays
    p, dy = rise_pos(l, 12)
    kicker(draw, 92, "the read path · smarana स्मरण · every query asks four ways", p, y_off=dy * SCALE)
    LB = [
        (46, 130, 292, AMBER, "shabda", "शब्द", "word · bm25"),
        (60, 158, 452, TEAL, "artha", "अर्थ", "meaning · vectors"),
        (74, 158, 636, VIOLET, "sambandha", "सम्बन्ध", "relation · entity hop"),
        (88, 130, 812, ROSE, "kala", "काल", "time · date proximity"),
    ]
    for at, lx, lyv, colc, name, deva, sub in LB:
        a = ramp(l, at, at + 20)
        if a <= 0.01:
            continue
        dyv = (1 - a) * 20
        draw.ellipse([X(lx), X(lyv + 6) + dyv, X(lx + 11), X(lyv + 17) + dyv], fill=mix(INK, colc, a))
        fl_ = font("mono", 22)
        tx = X(lx + 22)
        draw.text((tx, X(lyv) + dyv), name + " ", font=fl_, fill=mix(INK, PAPER, a))
        tx += draw.textlength(name + " ", font=fl_)
        draw.text((tx, X(lyv) + dyv), deva, font=font("disp-reg", 20), fill=mix(INK, colc, a))
        draw.text((X(lx + 22), X(lyv + 32) + dyv), sub, font=font("mono", 14.5), fill=mix(INK, MUTE, a))
    # confluence label + ring — anchored to the projected 3D confluence point
    aC = ramp(l, 168, 190)
    if aC > 0.01:
        conf_world = np.array([[2.6 + 2.4, 0.25 - 0.7, 0.0]], np.float32)
        cxs_, cys_, _ = project(conf_world, eye, right, up2, fwd, 55)
        cxr, cyr = X(cxs_[0]), X(cys_[0])
        ringp = ramp(l, 172, 214)
        if 0 < ringp < 1:
            rr = X(45 * (0.3 + ringp * 2.1))
            aR = 0.95 * (1 - ringp) * aC
            draw.ellipse([cxr - rr, cyr - rr, cxr + rr, cyr + rr],
                         outline=mix(INK, AMBER, aR), width=max(1, int(X(2))))
        fc = font("disp", 46)
        ty = cyr - X(196)
        draw_segments(draw, cxr, ty, [
            ("sangama ", fc, mix(INK, WHITE, aC)), ("संगम", font("disp-reg", 40), mix(INK, AMBER, aC))])
        draw_tracked(draw, (cxr, ty + X(66)), "four channels · one answer", font("mono", 17.5),
                     mix(INK, MUTE, aC), tracking=0.06, anchor_center=True)
    p6, d6 = rise_pos(l, 392)
    if p6 > 0:
        draw_tracked(draw, (W / 2, X(966) + d6 * SCALE),
                     "reciprocal-rank fusion · validity annotated · packed to a fixed token budget",
                     font("mono", 19), mix(INK, MUTE, p6), tracking=0.05, anchor_center=True)

def s7_receipts(l, arr, img, draw):
    p, dy = rise_pos(l, 8)
    kicker(draw, 108, "tested, not promised", p, y_off=dy * SCALE)
    CHIPS = [("1", " sqlite file"), ("0", " infrastructure"), ("~1.5k", " readable lines"),
             ("33", " offline tests"), ("42k", " rows/sec ingest"), ("ms", " queries at 12k memories"),
             ("apache-2.0", " · everything included")]
    fm = font("mono", 24)
    rows = [CHIPS[:4], CHIPS[4:]]
    yy0 = 210
    for r_i, row in enumerate(rows):
        widths = [draw.textlength(b + rest, font=fm) + X(64) for b, rest in row]
        totw = sum(widths) + X(18) * (len(row) - 1)
        xx0 = W / 2 - totw / 2
        for (b, rest), w_ in zip(row, widths):
            i = CHIPS.index((b, rest))
            t0 = 30 + i * 16
            if l >= t0:
                pop = min(1.0, springy(l, t0, 1.4))
                sc = 0.6 + 0.4 * pop
                chh = X(62) * sc
                cym = X(yy0 + r_i * 88) + X(31)
                box = [xx0 + w_ * (1 - sc) / 2, cym - chh / 2, xx0 + w_ * (1 + sc) / 2, cym + chh / 2]
                rounded_rect(draw, box, int(chh / 2), fill=(16, 21, 36), outline=LINE2, width=1)
                tx = xx0 + X(32)
                draw.text((tx, cym - fm.size * 0.62), b, font=fm, fill=AMBER)
                tx += draw.textlength(b, font=fm)
                draw.text((tx, cym - fm.size * 0.62), rest, font=fm, fill=PAPER)
            xx0 += w_ + X(18)
    # MCP
    p2, d2 = rise_pos(l, 188, 24)
    if p2 > 0:
        f2 = font("disp", 44)
        col = mix(INK, PAPER, p2)
        draw_segments(draw, W / 2, X(478) + d2 * SCALE, [
            ("drop it into ", f2, col), ("any agent", f2, mix(INK, AMBER, p2))])
    p3, d3 = rise_pos(l, 206, 22)
    if p3 > 0:
        tw_, th_ = 880, 150
        tx0 = (1920 - tw_) / 2
        ty0 = 566 + d3
        layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ld = ImageDraw.Draw(layer)
        rounded_rect(ld, [X(tx0), X(ty0), X(tx0 + tw_), X(ty0 + th_)], int(X(14)),
                     fill=(10, 14, 26, int(255 * p3)), outline=(*LINE, int(255 * p3)), width=1)
        for i in range(3):
            ld.ellipse([X(tx0 + 16 + i * 18), X(ty0 + 13), X(tx0 + 27 + i * 18), X(ty0 + 24)],
                       fill=(*LINE2, int(255 * p3)))
        ld.line([X(tx0), X(ty0 + 37), X(tx0 + tw_), X(ty0 + 37)], fill=(*LINE, int(255 * p3)), width=1)
        img.paste(layer, (0, 0), layer)
        cmd = "smriti-mcp --db memory.db"
        n = type_count(l, 222, 24, len(cmd))
        fmn = font("mono", 21)
        draw.text((X(tx0 + 26), X(ty0 + 56)), "$ ", font=fmn, fill=FAINT)
        off = draw.textlength("$ ", font=fmn)
        draw.text((X(tx0 + 26) + off, X(ty0 + 56)), cmd[:n], font=fmn, fill=PAPER)
        a4 = ramp(l, 268, 282)
        if a4 > 0:
            draw.text((X(tx0 + 26), X(ty0 + 100)), "✓ six typed tools · stdio json-rpc · offline by default",
                      font=font("mono", 17), fill=mix(INK, FAINT, a4))
    TOOLS = ["remember", "recall", "search", "facts_about", "add_fact", "stats"]
    fmt = font("mono", 15.5)
    widths = [draw.textlength(t_, font=fmt) + X(28) for t_ in TOOLS]
    totw = sum(widths) + X(12) * 5
    xx0 = W / 2 - totw / 2
    for t_, w_, i in zip(TOOLS, widths, range(6)):
        a = ramp(l, 284 + i * 7, 294 + i * 7)
        if a > 0.01:
            rounded_rect(draw, [xx0, X(766), xx0 + w_, X(766 + 36)], int(X(8)),
                         outline=mix(INK, LINE, a), width=1)
            draw.text((xx0 + X(14), X(773)), t_, font=fmt, fill=mix(INK, MUTE, a))
        xx0 += w_ + X(12)

def s8_honesty(l, arr, img, draw):
    p1, d1 = rise_pos(l, 14, 22)
    fh = font("disp", 78)
    if p1 > 0:
        tw_ = draw.textlength("no leaderboard claims.", font=fh)
        draw.text((W / 2 - tw_ / 2, X(206) + d1 * SCALE), "no leaderboard claims.", font=fh,
                  fill=mix(INK, PAPER, p1))
    p2, d2 = rise_pos(l, 54, 24)
    if p2 > 0:
        col = mix(INK, PAPER, p2)
        draw_segments(draw, W / 2, X(320) + d2 * SCALE, [
            ("the ", fh, col), ("benchmark harness", fh, mix(INK, AMBER, p2)),
            (" ships in the box.", fh, col)])
    p3, d3 = rise_pos(l, 116, 22)
    if p3 > 0:
        tw_, th_ = 760, 132
        tx0 = (1920 - tw_) / 2
        ty0 = 520 + d3
        rounded_rect(draw, [X(tx0), X(ty0), X(tx0 + tw_), X(ty0 + th_)], int(X(14)),
                     fill=(10, 14, 26), outline=LINE, width=1)
        cmd = "bash bench/ab.sh"
        n = type_count(l, 130, 20, len(cmd))
        fmn = font("mono", 21)
        draw.text((X(tx0 + 28), X(ty0 + 26)), "$ ", font=fmn, fill=FAINT)
        off = draw.textlength("$ ", font=fmn)
        draw.text((X(tx0 + 28) + off, X(ty0 + 26)), cmd[:n], font=fmn, fill=PAPER)
        a4 = ramp(l, 186, 200)
        if a4 > 0:
            draw.text((X(tx0 + 28), X(ty0 + 74)), "fixed judge · your data · your hardware → the delta, printed",
                      font=font("mono", 17), fill=mix(INK, FAINT, a4))
    p5, d5 = rise_pos(l, 216, 22)
    if p5 > 0:
        f5 = font("mono", 19)
        draw_segments(draw, W / 2, X(716) + d5 * SCALE, [
            ("run your own ", f5, mix(INK, MUTE, p5)), ("pariksha परीक्षा", f5, mix(INK, AMBER, p5)),
            (" · longmemeval + locomo included", f5, mix(INK, MUTE, p5))])

def s9_endcard(l, arr, img, draw):
    arr += blob_bg(l, [(11, 15, 28), (15, 22, 44), (19, 25, 42), (56, 40, 20)], speed=0.35, opacity=0.32)
    pulse = 0.5 + 0.5 * math.sin(l * 0.13)
    p1, d1 = rise_pos(l, 12, 24)
    if p1 > 0:
        fw_ = font("disp-bold", 148)
        fd = font("disp", 112)
        draw_segments(draw, W / 2, X(330) + d1 * SCALE, [
            ("smriti", fw_, mix(INK, PAPER, p1)), ("  स्मृति", fd, mix(INK, AMBER, p1))])
    p2, d2 = rise_pos(l, 40, 24)
    if p2 > 0:
        f2 = font("disp-reg", 48)
        col = mix(INK, MUTE, p2)
        segsw = draw_segments(draw, W / 2, X(566) + d2 * SCALE, [
            ("memory that knows ", f2, col), ("when", f2, mix(INK, AMBER, p2))])
        cxp = W / 2 + segsw / 2 + X(22)
        rr = X(7 + pulse * 5)
        cyp = X(566 + 36) + d2 * SCALE
        glow = [(cxp, cyp, AMBER, 1.4 + pulse)]
        arr += splat_glow(glow, blur=2.6)
    p3, d3 = rise_pos(l, 68, 24)
    if p3 > 0:
        f3 = font("mono", 23)
        draw_segments(draw, W / 2, X(700) + d3 * SCALE, [
            ("github.com/", f3, mix(INK, FAINT, p3)), ("vn-envy/Smriti", f3, mix(INK, MUTE, p3)),
            (" · apache-2.0 · ", f3, mix(INK, FAINT, p3)), ("pip install -e .", f3, mix(INK, MUTE, p3))])
    p4, d4 = rise_pos(l, 92, 24)
    if p4 > 0:
        cols = [(255, 153, 51), (245, 245, 245), (19, 136, 8)]
        label = "india-built · open source"
        fnt4 = font("mono", 16)
        track = fnt4.size * 0.14
        lw = sum(draw.textlength(ch, font=fnt4) + track for ch in label) - track
        block_w = 3 * X(16) + X(14) + lw
        bx = W / 2 - block_w / 2
        for i, colc in enumerate(cols):
            draw.ellipse([bx + i * X(16), X(772) + d4 * SCALE, bx + i * X(16) + X(9), X(781) + d4 * SCALE],
                         fill=mix(INK, colc, p4))
        draw_tracked(draw, (bx + 3 * X(16) + X(14), X(766) + d4 * SCALE), label,
                     fnt4, mix(INK, FAINT, p4), tracking=0.14)

# ———————————————————————— chrome + master ————————————————————————
SCENES = [
    (0, 240, s1_cold_open, 8, 16),
    (240, 600, s2_infra_tax, 10, 2),
    (600, 1020, s3_reveal, 2, 16),
    (1020, 1440, s4_write_path, 12, 16),
    (1440, 1920, s5_badha, 12, 16),
    (1920, 2460, s6_sangama, 14, 16),
    (2460, 2820, s7_receipts, 12, 16),
    (2820, 3090, s8_honesty, 12, 16),
    (3090, 3300, s9_endcard, 14, 26),
]

def film_chrome(f, draw):
    # brand tag
    a = ramp(f, 250, 275)
    if a > 0.01:
        fm = font("mono", 15)
        tx = X(44)
        draw.text((tx, X(36)), "smriti ", font=fm, fill=mix(INK, MUTE, a))
        tx += draw.textlength("smriti ", font=fm)
        draw.text((tx, X(36)), "स्मृति", font=font("disp-reg", 15), fill=mix(INK, AMBER, a))
        tx += draw.textlength("स्मृति", font=font("disp-reg", 15))
        draw.text((tx, X(36)), "  ·  launch film · 1:50", font=fm, fill=mix(INK, FAINT, a))
    # progress bar + timecode
    pct = min(f, TOTAL) / TOTAL
    draw.rectangle([0, H - max(2, int(X(3))), int(W * pct), H], fill=AMBER)
    secs = f // 30
    tc = f"0{secs // 60}:{secs % 60:02d} / 01:50"
    fm2 = font("mono", 13)
    tw_ = draw.textlength(tc, font=fm2)
    draw.text((W - X(44) - tw_, H - X(40)), tc, font=fm2, fill=FAINT)

def render_frame(f):
    arr = np.tile(np.array(INK, np.float32)[None, None, :], (H, W, 1))
    img = Image.fromarray(arr.astype(np.uint8))
    # find scene
    for (start, end, fn, fin, fout) in SCENES:
        if start <= f < end:
            l = f - start
            dur = end - start
            fade = min(ramp(l, 0, fin, ease_in_out), 1 - ramp(l, dur - fout, dur - 1, ease_in_out))
            arr = np.tile(np.array(INK, np.float32)[None, None, :], (H, W, 1))
            img = Image.new("RGB", (W, H), INK)
            draw = ImageDraw.Draw(img)
            fn(l, arr, img, draw)
            # composite: img (PIL vector art) over arr additive glow base
            vec = np.asarray(img).astype(np.float32)
            ink = np.array(INK, np.float32)[None, None, :]
            mask = (np.abs(vec - ink).sum(axis=2, keepdims=True) > 12).astype(np.float32)
            out = np.clip(ink + (vec - ink) * mask + (arr - ink) * 1.0, 0, 255)
            # scene fade to ink
            out = ink + (out - ink) * fade
            break
    else:
        out = arr
    # chrome
    imgc = Image.fromarray(np.clip(out, 0, 255).astype(np.uint8))
    drawc = ImageDraw.Draw(imgc)
    film_chrome(f, drawc)
    out = np.asarray(imgc).astype(np.float32)
    # vignette + grain
    out = out * get_vignette()
    g = np.random.default_rng(f).normal(0, 3.2, (H // 2, W // 2, 1)).astype(np.float32)
    g = np.repeat(np.repeat(g, 2, axis=0), 2, axis=1)
    out = np.clip(out + g, 0, 255)
    return Image.fromarray(out.astype(np.uint8))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", type=int, default=0)
    ap.add_argument("--end", type=int, default=TOTAL)
    ap.add_argument("--outdir", default=os.path.join(os.path.dirname(__file__), "frames"))
    args = ap.parse_args()
    os.makedirs(args.outdir, exist_ok=True)
    for f in range(args.start, min(args.end, TOTAL)):
        path = os.path.join(args.outdir, f"f{f:05d}.jpg")
        if os.path.exists(path):
            continue
        im = render_frame(f)
        im.save(path, quality=88)
    print(f"done {args.start}..{min(args.end, TOTAL)}")

if __name__ == "__main__":
    main()
