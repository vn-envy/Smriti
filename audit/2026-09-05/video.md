# SMRITI 30-second launch teaser

- Composition: `SmritiLaunch30`, 1920×1080, 30 fps, 900 frames (exactly 30 seconds).
- Story: stale memory → timestamped supersession → four-channel retrieval confluence → portable SQLite core → launch card.
- Claims mirror `site/index.html`: superseded facts are retained, four retrieval channels are fused, storage is one SQLite file, and the project is Apache-2.0.
- Visual system mirrors the site: `#0B0F1C` ink, paper white, amber/teal/violet/rose channel colors, Space Grotesk, Inter, and JetBrains Mono.
- Browser preview: `public/webgpu-preview.html`. Its Three.js `WebGPURenderer` selects WebGPU when `navigator.gpu` and an adapter are available, initializes it asynchronously, and visibly reports `WEBGPU · ACTIVE`. The same renderer explicitly falls back to its WebGL2 backend and reports `WEBGL2 · FALLBACK`; the fallback is never labelled WebGPU.
- Export path: Remotion renders the deterministic Three/R3F scene to H.264. The browser preview is the separately verifiable native WebGPU path for the same confluence/core design.
- Browser QA on 2026-09-06: Chrome initialized `WebGPUBackend`; the preview visibly reported `WEBGPU · ACTIVE` and played its timed story with replay control. Serve with `cd launch-video && python3 -m http.server 4174 -d public`, then open `http://127.0.0.1:4174/webgpu-preview.html`.
- Final master: `launch-video/out/smriti-launch-teaser-30s-exact.mp4` — H.264/AAC, 1920×1080, 30 fps, 900 video frames, container duration exactly `30.000000` seconds.
