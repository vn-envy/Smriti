/**
 * Persistent GBrain semantic/hybrid public-retrieval worker.
 *
 * This is deliberately separate from gbrain_growth_worker.ts.  The latter is
 * the lexical, --no-embedding track; this worker configures the pinned GBrain
 * gateway to use the real local Ollama nomic model and fails closed if a
 * query degrades to keyword-only retrieval.
 */
import { createInterface } from 'node:readline';

const gbrainRoot = process.env.GBRAIN_ROOT;
if (!gbrainRoot) throw new Error('GBRAIN_ROOT must point to the pinned gbrain checkout');
const dbPath = process.env.GBRAIN_DB_PATH;
if (!dbPath) throw new Error('GBRAIN_DB_PATH is required');
const baseUrl = process.env.GBRAIN_OLLAMA_BASE_URL ?? 'http://localhost:11436/v1';
const embeddingModel = process.env.GBRAIN_EMBEDDING_MODEL ?? 'ollama:nomic-embed-text:v1.5';
const embeddingDimensions = Number(process.env.GBRAIN_EMBEDDING_DIMENSIONS ?? '768');
if (!Number.isInteger(embeddingDimensions) || embeddingDimensions < 1) {
  throw new Error(`GBRAIN_EMBEDDING_DIMENSIONS must be a positive integer, got ${embeddingDimensions}`);
}

const { configureGateway, embedQuery } = await import(`${gbrainRoot}/src/core/ai/gateway.ts`);
const { createEngine } = await import(`${gbrainRoot}/src/core/engine-factory.ts`);
const { importFromContent } = await import(`${gbrainRoot}/src/core/import-file.ts`);
const { hybridSearch } = await import(`${gbrainRoot}/src/core/search/hybrid.ts`);

// This is the same OpenAI-compatible /v1 endpoint used by the pinned Ollama
// recipe.  No fake/test queryEmbedFn is installed here.
configureGateway({
  embedding_model: embeddingModel,
  embedding_dimensions: embeddingDimensions,
  base_urls: { ollama: baseUrl },
  env: {},
});

const engine = await createEngine({ engine: 'pglite', database_path: dbPath });
await engine.connect({ engine: 'pglite', database_path: dbPath });
await engine.initSchema();

function reply(value: unknown): void {
  process.stdout.write(`${JSON.stringify(value)}\n`);
}

async function dimensionProbe(): Promise<number> {
  const vector = await embedQuery('semantic retrieval dimension probe');
  return vector.length;
}

async function handle(message: Record<string, unknown>): Promise<void> {
  const op = message.op;
  if (op === 'ready') {
    const measuredDimensions = await dimensionProbe();
    if (measuredDimensions !== embeddingDimensions) {
      throw new Error(
        `semantic embedding dimension mismatch: configured ${embeddingDimensions}, measured ${measuredDimensions}`,
      );
    }
    reply({
      ok: true,
      ready: true,
      semantic: true,
      embedding_model: embeddingModel,
      embedding_dimensions: embeddingDimensions,
      measured_embedding_dimensions: measuredDimensions,
      ollama_base_url: baseUrl,
    });
    return;
  }
  if (op === 'put_many') {
    const docs = Array.isArray(message.documents) ? message.documents : [];
    let imported = 0;
    let skipped = 0;
    const failures: string[] = [];
    const statuses: Array<{ id: string; status: string; error?: string }> = [];
    for (const value of docs) {
      const doc = value as { id: string; timestamp: string; text: string };
      const content = `---\nid: ${doc.id}\ndate: ${doc.timestamp}\n---\n\n${doc.text}`;
      // Omitting noEmbed is intentional: this is the real document-embedding
      // path.  Dataset labels stay outside the imported content.
      const result = await importFromContent(engine, `bench/${doc.id}`, content, {
        sourceId: 'default',
        source_kind: 'benchmark',
        source_uri: `benchmark://${doc.id}`,
        ingested_via: 'engine-importFromContent-semantic',
      });
      const status = String(result.status ?? 'unknown');
      const error = result.error == null ? undefined : String(result.error);
      statuses.push({ id: doc.id, status, ...(error ? { error } : {}) });
      if (status === 'imported' && !error) imported += 1;
      else if (status === 'skipped' && !error) skipped += 1;
      else failures.push(`${doc.id}:${status}${error ? `:${error}` : ''}`);
    }
    const pageCount = (await engine.listPages({ sourceId: 'default', slugPrefix: 'bench/', limit: 100000 })).length;
    const stats = await engine.getStats({ sourceId: 'default' });
    // Import status alone does not prove that vectors reached storage. The
    // engine's supported stats API is the source of truth for this gate.
    if (Number(stats.embedded_count) !== Number(stats.chunk_count)) {
      throw new Error(
        `semantic import vector coverage incomplete: ${stats.embedded_count}/${stats.chunk_count} chunks embedded`,
      );
    }
    if (failures.length > 0) {
      reply({ ok: false, error: `import failures: ${failures.join(',')}`, imported, skipped, failures, statuses, page_count: pageCount, vector_stats: stats });
    } else {
      reply({ ok: true, imported, skipped, statuses, page_count: pageCount, vector_stats: stats });
    }
    return;
  }
  if (op === 'search') {
    const query = String(message.query ?? '');
    const limit = Number(message.limit ?? 5);
    if (!Number.isInteger(limit) || limit < 1) throw new Error(`invalid search limit ${limit}`);
    let meta: Record<string, unknown> | undefined;
    const rows = await hybridSearch(engine, query, {
      limit,
      expansion: false,
      reranker: { enabled: false },
      autocut: false,
      onMeta: (value) => { meta = value as unknown as Record<string, unknown>; },
    });
    // A semantic run must prove the vector arm ran. Keyword fallback is an
    // operational failure, never a valid semantic result.
    if (meta?.vector_enabled !== true) {
      throw new Error(`semantic search degraded to keyword-only: ${JSON.stringify(meta ?? {})}`);
    }
    const degraded = Array.isArray(meta?.degraded) ? meta.degraded : [];
    const vectorFailureStages = new Set([
      'embed_timeout', 'embed_unavailable', 'vector_arm_failed',
      'rescore_skipped', 'expansion_partial',
    ]);
    const vectorFailures = degraded.filter((entry) =>
      entry && typeof entry === 'object' && vectorFailureStages.has(String((entry as { stage?: unknown }).stage)),
    );
    if (vectorFailures.length > 0) {
      throw new Error(`semantic search had vector degradation: ${JSON.stringify(vectorFailures)}`);
    }
    reply({
      ok: true,
      semantic: true,
      embedding_model: embeddingModel,
      embedding_dimensions: embeddingDimensions,
      results: rows.map((row) => ({ slug: row.slug, score: row.score })),
      search_meta: meta,
    });
    return;
  }
  if (op === 'close') {
    await engine.disconnect();
    reply({ ok: true, closed: true });
    process.exit(0);
  }
  throw new Error(`unknown operation: ${String(op)}`);
}

const rl = createInterface({ input: process.stdin, crlfDelay: Infinity });
for await (const line of rl) {
  if (!line.trim()) continue;
  try {
    await handle(JSON.parse(line) as Record<string, unknown>);
  } catch (error) {
    reply({ ok: false, error: error instanceof Error ? error.message : String(error) });
  }
}
