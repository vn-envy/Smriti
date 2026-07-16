# SMRITI — Launch Film Storyboard

**"Memory that knows when."** · 110 seconds · 1920×1080 · 30fps · 3300 frames

The film is a three-act argument, told in the product's own visual language
(ink, amber, the four river colors) and its own lexicon (the Nyaya account of
memory). Act I: the wound and the tax. Act II: the idea — one file, impressions,
supersession, confluence. Act III: the receipts and the handshake.

Structural rhythm: dark → cluttered → clean → flowing → certain.

| # | Frames | Time | Scene | What happens |
|---|--------|------|-------|--------------|
| 1 | 0–240 | 0:00–0:08 | **Cold open** | Black. Drifting memory motes. Typed: `agents forget.` beat. `every session starts from zero.` |
| 2 | 240–600 | 0:08–0:20 | **The tax** | "the usual fix is infrastructure." Slabs slam in and stack into a looming tower: Postgres · Neo4j · Qdrant · Redis · Docker · a cloud account · a $249/mo tier. The tower flickers red, then implodes to a single point of amber light. |
| 3 | 600–1020 | 0:20–0:34 | **Reveal** (three.js) | The point blooms into a slowly-orbiting amber cube — *one SQLite file* — floating over a dim MeshGradient nebula. Wordmark rises: **smriti स्मृति** · "that which is remembered" · *memory that knows when.* |
| 4 | 1020–1440 | 0:34–0:48 | **Write path** | "Nyaya, two millennia ago: experience leaves impressions; recollection arises from them." A session card distills into atomic facts through the pipeline: anubhava अनुभव → grahana ग्रहण → samskara संस्कार. One LLM call, glossed. |
| 5 | 1440–1920 | 0:48–1:04 | **Badha** (the soul) | The supersession card. `user lives in Hyderabad · CURRENT` — a new fact arrives — the badge flips to `SUPERSEDED · 2026-06-01`, validity windows draw. Payoff: *"where now?" → Bengaluru. "before June?" → Hyderabad.* One store, both answers. Caption: **badha बाध — superseded, never deleted.** |
| 6 | 1920–2460 | 1:04–1:22 | **Sangama** (three.js hero) | The four retrieval rivers — shabda (amber), artha (teal), sambandha (violet), kala (rose) — braid through 3D space and meet in one bright confluence. A recall pulse sweeps the streams. Ring flash: **sangama संगम · four channels, one answer.** Camera drifts, deterministic. |
| 7 | 2460–2820 | 1:22–1:34 | **Receipts** | Chips stamp in: 1 sqlite file · 0 infrastructure · ~1.5k readable lines · 33 offline tests · 42k rows/sec · apache-2.0, everything. Then the MCP drop-in: `smriti-mcp --db memory.db` + six typed tools. |
| 8 | 2820–3090 | 1:34–1:43 | **Honesty** | "no leaderboard claims. the benchmark harness ships in the box." Terminal types `bash bench/ab.sh`. *run your own pariksha परीक्षा.* |
| 9 | 3090–3300 | 1:43–1:50 | **End card** | Logo large, tagline pulse, tricolor dots. `github.com/vn-envy/Smriti` · apache-2.0 · MeshGradient breathes underneath. |

## Tech
- **Remotion 4** — deterministic, frame-driven; every animation is a pure function of `useCurrentFrame()`.
- **@remotion/three + react-three-fiber** — scenes 3 & 6 (cube reveal, particle rivers ported from `smriti-landing.html`).
- **@paper-design/shaders-react** — MeshGradient / GrainGradient backdrops, driven by the `frame` prop (speed 0) so renders are reproducible.
- **Score** — generated tanpura-style drone (D + A partials, slow beating) with soft pentatonic chimes on scene boundaries, synthesized in `scripts/make-audio.py`.
- **Fonts** — Space Grotesk, Inter, JetBrains Mono, Noto Sans Devanagari, self-hosted from `public/fonts` (offline render, no CDN).

## Palette (from the repo)
ink `#0B0F1C` · paper `#E9EDF6` · amber `#F4A43C` · teal `#52C7BE` · violet `#B794E0` · rose `#E08AA0` · merged `#FFD9A0` · slate `#4A5570`
