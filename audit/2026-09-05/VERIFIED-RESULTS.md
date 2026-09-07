# Independently verified build results

Updated 2026-09-07. Implementation now uses Luna (high), as requested; parent agent independently reviews and tests.

The earlier cross-platform core/enterprise candidate passed 169 tests after non-editable wheel installation on macOS Python 3.11 and Linux Python 3.12, and source-distribution installation with isolated build dependencies on Linux Python 3.9. Package hashes and exact scope are in [final-install-verification.json](raw/final-install-verification.json).

An actual database and v1 backup created by the original package were reopened/restored with explicit legacy embedding adoption and queried successfully. The earlier late-middle enterprise defect now returns Hyderabad for world-May/known-July, and Pune for world-May/known-September, with the correct June validity boundary in both returned records. Previously lost revisions cannot be recovered retroactively by migration.

The 30-second teaser is rendered and independently checked at 1920×1080, 30 fps, 900 frames, H.264/AAC. Chrome visibly reported WebGPU active; replay returned to the opening scene. See [video verification](video.md).

The 20-document diagnostic is not a broad leaderboard. Smriti recall@5 .85, Mem0 1.00, GBrain .95 used different embeddings/search configurations. The public LongMemEval oracle run is an evidence-only sanity ceiling, not full-haystack quality. Matched public retrieval, cost/speed growth runs, and the resulting final roadmap priorities remain unfinished. No universal superiority, zero-defect, or live-deployment claim is supported.

The subsequent HTTP retry fix was independently tested in an ordinary wheel outside the checkout: 185 core/enterprise tests passed, followed by 14 focused retry tests after a comment-only rebuild. Permanent HTTP errors fail fast; `http_attempts` counts actual requests separately from logical attempts and successful-response token totals. See [installed retry verification](raw/http-retry-installed-verification.json).

Graphify 0.9.54 installed successfully and extracted 229 nodes / 531 edges from the 13 Smriti core code files; a source-linked method query was independently checked. Hindsight 0.9.2 ran with embedded pg0 and local qwen3:8b/nomic models, retaining three dated updates and returning current/historical evidence. These are real installation smokes, not comparable quality scores. See [Graphify evidence](raw/graphify-installed-smoke.json), [Hindsight fresh-bank trace](hindsight-smoke-full.json), and [independent Hindsight recall](raw/hindsight-independent-recall.json).
