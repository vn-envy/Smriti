/**
 * Persistent gbrain growth-benchmark worker.
 *
 * The benchmark talks to this process over JSONL so engine startup and PGLite
 * schema initialization are paid once per run, rather than once per document
 * or query. It deliberately uses gbrain's public importFromContent pipeline
 * with no embedding provider: this is the separately labelled lexical track.
 */
import { createInterface } from 'node:readline';

const gbrainRoot = process.env.GBRAIN_ROOT;
if (!gbrainRoot) throw new Error('GBRAIN_ROOT must point to the pinned gbrain checkout');
const { createEngine } = await import(`${gbrainRoot}/src/core/engine-factory.ts`);
const { importFromContent } = await import(`${gbrainRoot}/src/core/import-file.ts`);

const dbPath = process.env.GBRAIN_DB_PATH;
if (!dbPath) throw new Error('GBRAIN_DB_PATH is required');

const engine = await createEngine({ engine: 'pglite', database_path: dbPath });
await engine.connect({ engine: 'pglite', database_path: dbPath });
await engine.initSchema();

function reply(value: unknown): void {
  process.stdout.write(`${JSON.stringify(value)}\n`);
}

async function handle(message: Record<string, unknown>): Promise<void> {
  const op = message.op;
  if (op === 'ready') {
    reply({ ok: true, ready: true });
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
      const result = await importFromContent(engine, `bench/${doc.id}`, content, {
        noEmbed: true,
        sourceId: 'default',
        source_kind: 'benchmark',
        source_uri: `benchmark://${doc.id}`,
        ingested_via: 'engine-importFromContent',
      });
      const status = String(result.status ?? 'unknown');
      const error = result.error == null ? undefined : String(result.error);
      statuses.push({ id: doc.id, status, ...(error ? { error } : {}) });
      if (status === 'imported' && !error) imported += 1;
      else if (status === 'skipped' && !error) skipped += 1;
      else failures.push(`${doc.id}:${status}${error ? `:${error}` : ''}`);
    }
    const pageCount = (await engine.listPages({ sourceId: 'default', slugPrefix: 'bench/', limit: 100000 })).length;
    if (failures.length > 0) {
      reply({ ok: false, error: `import failures: ${failures.join(',')}`, imported, skipped, failures, statuses, page_count: pageCount });
    } else {
      reply({ ok: true, imported, skipped, statuses, page_count: pageCount });
    }
    return;
  }
  if (op === 'search') {
    const query = String(message.query ?? '');
    const limit = Number(message.limit ?? 5);
    const rows = await engine.searchKeyword(query, { limit, orFallback: true });
    reply({ ok: true, results: rows.map((row) => ({ slug: row.slug, score: row.score })) });
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
