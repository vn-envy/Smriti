/**
 * CPU-only GBrain PGLite maintenance diagnostic.
 *
 * Required environment:
 *   GBRAIN_ROOT=/path/to/gbrain
 *   GBRAIN_DB_SOURCE=/path/to/closed/pglite/database
 *
 * The source database is recursively copied before any engine opens it. All
 * ANALYZE and restart work targets that copy. No embedding or model calls are
 * made; this measures the keyword path used by the preserved 5k fixture.
 */
import { cpSync, existsSync, mkdtempSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { tmpdir } from 'node:os';

const queries = [
  'passport renewal appointment',
  'doctor knee recommendation',
  'project launch date',
  'invoice due date',
  'emergency contact',
];
const queryCount = 10;
const limit = 5;

function required(name: string): string {
  const value = process.env[name];
  if (!value) throw new Error(`${name} is required`);
  return value;
}

function queryName(index: number): string {
  return queries[index % queries.length];
}

async function engineFor(dbPath: string, root: string) {
  const factory = await import(join(root, 'src/core/engine-factory.ts'));
  const engine = await factory.createEngine({ engine: 'pglite', database_path: dbPath });
  await engine.connect({ engine: 'pglite', database_path: dbPath });
  await engine.initSchema();
  return engine;
}

async function batch(engine: any) {
  const rows = [];
  for (let index = 0; index < queryCount; index += 1) {
    const query = queryName(index);
    const started = performance.now();
    const hits = await engine.searchKeyword(query, { limit, orFallback: true });
    rows.push({
      index,
      query,
      ms: performance.now() - started,
      slugs: hits.map((hit: any) => hit.slug),
      returned_count: hits.length,
    });
  }
  return rows;
}

function comparable(rows: any[]) {
  return rows.map((row) => ({ query: row.query, slugs: row.slugs }));
}

function queryIntegrity(rows: any[]) {
  return {
    all_queries_returned_five: rows.every((row) => row.returned_count === limit),
    unique_query_order: rows.map((row) => row.query),
  };
}

async function childRestart(root: string, dbPath: string) {
  const started = performance.now();
  const engine = await engineFor(dbPath, root);
  const startup_ms = performance.now() - started;
  const rows = await batch(engine);
  await engine.disconnect();
  return { rows, startup_ms };
}

async function freshProcess(root: string, dbPath: string) {
  const script = process.argv[1];
  if (!script) throw new Error('cannot determine probe script path for restart');
  const child = Bun.spawn([process.execPath, script], {
    env: { ...process.env, GBRAIN_CHILD: '1', GBRAIN_DB_COPY: dbPath },
    stdout: 'pipe',
    stderr: 'pipe',
  });
  const [exitCode, stdout, stderr] = await Promise.all([
    child.exited,
    new Response(child.stdout).text(),
    new Response(child.stderr).text(),
  ]);
  if (exitCode !== 0) throw new Error(`restart child exited ${exitCode}: ${stderr}`);
  return JSON.parse(stdout);
}

async function main() {
  const root = required('GBRAIN_ROOT');
  const source = required('GBRAIN_DB_SOURCE');
  if (!existsSync(root)) throw new Error(`GBRAIN_ROOT does not exist: ${root}`);
  if (!existsSync(source)) throw new Error(`GBRAIN_DB_SOURCE does not exist: ${source}`);
  if (process.env.GBRAIN_CHILD === '1') {
    const copiedDb = required('GBRAIN_DB_COPY');
    const restart = await childRestart(root, copiedDb);
    console.log(JSON.stringify(restart));
    return;
  }
  const copiedRoot = mkdtempSync(join(tmpdir(), 'gbrain-maintenance-copy-'));
  const copiedDb = join(copiedRoot, 'db');
  cpSync(source, copiedDb, { recursive: true });

  const engine = await engineFor(copiedDb, root);
  const documents = (await engine.listPages({ sourceId: 'default', slugPrefix: 'bench/', limit: 100000 })).length;
  const before = await batch(engine);
  const maintenanceStarted = performance.now();
  await engine.executeRaw('ANALYZE');
  const maintenance_ms = performance.now() - maintenanceStarted;
  const after = await batch(engine);
  await engine.disconnect();
  const restart = await freshProcess(root, copiedDb);
  const beforeComparable = comparable(before);
  const afterComparable = comparable(after);
  const restartComparable = comparable(restart.rows);
  const result = {
    schema_version: 1,
    track: 'CPU-only copied-database GBrain repeat-maintenance diagnostic; source fixture may already be analyzed; no embedding or model calls',
    configuration: {
      engine: 'pglite',
      query_count: queryCount,
      search_limit: limit,
      orFallback: true,
      model: null,
      embedding: null,
      root,
      source_db: source,
      copied_db: copiedDb,
      source_mutated: false,
      source_state: 'The preserved fixture used for this run was already analyzed; this is not evidence of the original cold-start cliff.',
      copy_strategy: 'recursive copy before engine connect; ANALYZE and restart target copied_db',
    },
    documents,
    before,
    maintenance_ms,
    after,
    restart,
    verification: {
      before: queryIntegrity(before),
      after: queryIntegrity(after),
      restart: queryIntegrity(restart.rows),
      identical_ranked_results_before_after: JSON.stringify(beforeComparable) === JSON.stringify(afterComparable),
      identical_ranked_results_after_restart: JSON.stringify(afterComparable) === JSON.stringify(restartComparable),
    },
    limitations: [
      'One deterministic ten-query order; caches and concurrent host workload are not randomized.',
      'Returned slugs are compared exactly; this diagnostic does not claim semantic relevance beyond the fixture check.',
      'The provided source fixture was already analyzed; this run validates repeat maintenance and restart preservation, not the original cold-start cliff.',
    ],
    reproduce: 'GBRAIN_ROOT=/path/to/gbrain GBRAIN_DB_SOURCE=/path/to/closed/db bun audit/2026-09-05/qa/gbrain_maintenance_probe.ts',
  };
  const output = process.env.GBRAIN_OUT;
  if (output) writeFileSync(output, JSON.stringify(result, null, 2) + '\n');
  console.log(JSON.stringify(result, null, 2));
}

await main();
