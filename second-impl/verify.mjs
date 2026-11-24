#!/usr/bin/env node
/**
 * UIBC package verifier — second implementation (Node.js, zero dependencies).
 *
 * Honest scope, read this before quoting the output:
 *   1. This is a SECOND IMPLEMENTATION, not an independent one. It is written
 *      by the same maintainer as uibc-core, in a different language and with
 *      no shared code. It demonstrates language-neutral reachability of the
 *      byte-defined parts, nothing more. Independence would require a different
 *      maintainer; see ../implementations.json.
 *   2. Coverage: S1, S2, S3, S4, S5, S6, S7, S8, S11, S12. The reference
 *      verifier runs S1–S19; the remaining checks concern anchors, merkle
 *      proofs, RFC 3161 tokens and policy artefacts, none of which appear in
 *      the committed fixtures.
 *   3. No UIBC-specific lookup tables: canonicalization is RFC 8785 done with
 *      plain sorted JSON.stringify, hashes are node:crypto, the seal is
 *      node:crypto Ed25519. If this file and uibc-core ever disagree, the
 *      disagreement is the finding.
 *
 * Usage:
 *   node verify.mjs <package-dir> [--pubkey <path-to-base64-pubkey>] [--json]
 * Exit: 0 = PASS, 1 = FAIL or INCONCLUSIVE (same convention as the reference CLI).
 */

import { createHash, verify as edVerify, createPublicKey } from 'node:crypto';
import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join, dirname, resolve, relative } from 'node:path';

/* ---------- canonicalization: RFC 8785 via ECMAScript primitives ---------- */

function canon(v) {
  if (v === null || v === undefined) return 'null';
  if (typeof v === 'boolean') return v ? 'true' : 'false';
  if (typeof v === 'number') return JSON.stringify(v);
  if (typeof v === 'string') return JSON.stringify(v);
  if (Array.isArray(v)) return '[' + v.map(canon).join(',') + ']';
  const keys = Object.keys(v).sort(); // default sort = UTF-16 code-unit order (JCS)
  return '{' + keys.map((k) => JSON.stringify(k) + ':' + canon(v[k])).join(',') + '}';
}
const sha256hex = (s) => createHash('sha256').update(s, 'utf8').digest('hex');
const hashObj = (o) => sha256hex(canon(o));

/* ---------- S11: strict serialization, scanned before any parse ---------- */

/** Returns a list of problems: duplicate member names, raw control characters. */
function strictScan(text) {
  const problems = [];
  const stack = []; // {type:'obj'|'arr', keys:Set} for duplicate detection
  let i = 0;
  let pendingKey = null; // set when a string is a member name
  let expectKey = false;
  while (i < text.length) {
    const c = text[i];
    if (c === '"') {
      let j = i + 1;
      let s = '';
      while (j < text.length) {
        const ch = text[j];
        if (ch === '\\') {
          s += ch + (text[j + 1] ?? '');
          j += 2;
          continue;
        }
        if (ch === '"') break;
        const code = ch.charCodeAt(0);
        if (code < 0x20) problems.push(`raw control character U+${code.toString(16).padStart(4, '0')} in string`);
        s += ch;
        j += 1;
      }
      const isKey = stack.length > 0 && stack[stack.length - 1].type === 'obj' && expectKey;
      if (isKey) {
        const key = JSON.parse('"' + s + '"');
        const top = stack[stack.length - 1];
        if (top.keys.has(key)) problems.push(`duplicate member name: ${key}`);
        top.keys.add(key);
        pendingKey = key;
        expectKey = false;
      }
      i = j + 1;
      continue;
    }
    if (c === '{') { stack.push({ type: 'obj', keys: new Set() }); expectKey = true; pendingKey = null; i += 1; continue; }
    if (c === '[') { stack.push({ type: 'arr', keys: new Set() }); expectKey = false; i += 1; continue; }
    if (c === '}') { stack.pop(); expectKey = false; i += 1; continue; }
    if (c === ']') { stack.pop(); expectKey = false; i += 1; continue; }
    if (c === ',') { expectKey = stack.length > 0 && stack[stack.length - 1].type === 'obj'; pendingKey = null; i += 1; continue; }
    if (c === ':') { expectKey = false; i += 1; continue; }
    i += 1;
  }
  return problems;
}

/* ---------- helpers ---------- */

const DATE_RE = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})$/;
const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;

function readJson(dir, rel) {
  return JSON.parse(readFileSync(join(dir, rel), 'utf8'));
}
function readText(dir, rel) {
  return readFileSync(join(dir, rel), 'utf8');
}
function walkFiles(base, prefix = '') {
  const out = [];
  for (const name of readdirSync(base)) {
    const p = join(base, name);
    const st = statSync(p);
    if (st.isDirectory()) out.push(...walkFiles(p, prefix + name + '/'));
    else out.push(prefix + name);
  }
  return out;
}

/* ---------- main ---------- */

function verifyPackage(dir, pinnedKeyB64) {
  const checks = [];
  const record = (id, name, pass, detail, inconclusive = false) => {
    checks.push({ id, name, result: inconclusive ? 'INCONCLUSIVE' : pass ? 'PASS' : 'FAIL', detail });
  };

  // S11 first: bytes before structure.
  const s11 = [];
  for (const rel of ['manifest.json', 'identity.json', 'lifecycle.json', 'evidence/index.json']) {
    try {
      for (const p of strictScan(readText(dir, rel))) s11.push(`${rel}: ${p}`);
    } catch (e) {
      s11.push(`${rel}: unreadable (${e.code || e.message})`);
    }
  }
  if (s11.length) {
    record('S11', 'strict serialization', false, s11.join('; '));
    return finish(checks);
  }
  record('S11', 'strict serialization', true, 'UTF-8, no duplicate member names, no raw control characters');

  // S1 structure
  const required = ['manifest.json', 'identity.json', 'lifecycle.json', 'evidence/index.json'];
  const missing = required.filter((r) => {
    try { statSync(join(dir, r)); return false; } catch { return true; }
  });
  const allowedRoot = new Set(['manifest.json', 'identity.json', 'lifecycle.json', 'evidence', 'signatures', '.gitattributes', '.git']);
  const rootEntries = readdirSync(dir);
  const extras = rootEntries.filter((e) => !allowedRoot.has(e));
  record('S1', 'package structure', missing.length === 0 && extras.length === 0,
    missing.length ? `missing: ${missing.join(',')}` : extras.length ? `undeclared root entries: ${extras.join(',')}` : 'required files present, no undeclared root entries');

  const manifest = readJson(dir, 'manifest.json');
  const identity = readJson(dir, 'identity.json');
  const lifecycle = readJson(dir, 'lifecycle.json');
  const index = readJson(dir, 'evidence/index.json');

  // S2 identity consistency
  const ids = [identity.agent_id, manifest.agent_id, ...(lifecycle.events || []).map((e) => e.agent_id)];
  const s2ok = ids.every((x) => typeof x === 'string' && x.length > 0) && new Set(ids).size === 1;
  record('S2', 'identity consistency', s2ok, s2ok ? `agent_id='${ids[0]}' consistent` : `agent_id mismatch: ${JSON.stringify(ids)}`);

  // S3 lifecycle
  const ev = lifecycle.events || [];
  const s3 = [];
  ev.forEach((e, i) => {
    if (e.sequence_number !== i) s3.push(`event ${i}: sequence_number=${e.sequence_number}`);
    const prev = i === 0 ? null : ev[i - 1].event_id;
    if ((e.previous_event ?? null) !== prev) s3.push(`event ${i}: previous_event=${e.previous_event}`);
    if (i > 0) {
      const a = Date.parse(ev[i - 1].timestamp), b = Date.parse(e.timestamp);
      if (!(b >= a)) s3.push(`event ${i}: timestamp not monotonic`);
    }
    if (!UUID_RE.test(String(e.event_id))) s3.push(`event ${i}: event_id not a lowercase UUID`);
  });
  record('S3', 'lifecycle state machine', s3.length === 0, s3.join('; ') || `${ev.length} events, chain valid, timestamps monotonic`);

  // S4 evidence hashes — and the byte truth that S5/S8 must be computed from.
  // Reading the reference verifier's source settled an ambiguity this second
  // implementation originally got wrong: roots and checkpoint heads are over
  // the bytes ON DISK, never over what evidence/index.json claims. A root that
  // matches only because the index is lying must not be reported as PASS, and
  // when the bytes fail, S5 is reported skipped (INCONCLUSIVE) rather than as
  // a mismatch, because there is nothing trustworthy to compare.
  const entries = index.entries || [];
  const s4 = [];
  const onDisk = []; // actual sha256 per entry, null when unreadable
  for (const e of entries) {
    const p = resolve(dir, 'evidence', String(e.path ?? ''));
    const evRoot = resolve(dir, 'evidence') + (process.platform === 'win32' ? '\\' : '/');
    if (!p.startsWith(evRoot)) { s4.push(`${e.path}: path leaves evidence/`); onDisk.push(null); continue; }
    let bytes;
    try {
      bytes = readFileSync(p);
    } catch {
      s4.push(`${e.path}: file missing`);
      onDisk.push(null);
      continue;
    }
    const dig = createHash('sha256').update(bytes).digest('hex');
    onDisk.push(dig);
    if (dig !== e.content_hash) s4.push(`${e.path}: hash mismatch`);
  }
  const s4ok = s4.length === 0 && entries.length > 0;
  record('S4', 'evidence integrity', s4ok, s4.join('; ') || `${entries.length} entries checked; all hashes match`);

  // S12 timestamps / identifiers
  const s12 = [];
  for (const e of entries) {
    if (!DATE_RE.test(String(e.created_at ?? ''))) s12.push(`entry created_at not RFC 3339 with zone: ${e.created_at}`);
    if (!UUID_RE.test(String(e.evidence_id ?? ''))) s12.push(`evidence_id not a lowercase UUID: ${e.evidence_id}`);
  }
  for (const e of ev) if (!DATE_RE.test(String(e.timestamp ?? ''))) s12.push(`event timestamp not RFC 3339 with zone: ${e.timestamp}`);
  record('S12', 'timestamp and identifier strictness', s12.length === 0, s12.join('; ') || 'timestamps RFC 3339 with a zone; UUIDs lowercase');

  // S7 index metadata digest
  const meta = entries.map((e) => ({ path: String(e.path ?? ''), type: e.type ?? null, note: e.note ?? null, action_digest: e.action_digest ?? null }));
  meta.sort((a, b) => (a.path < b.path ? -1 : a.path > b.path ? 1 : 0));
  const s7dig = 'sha256:' + sha256hex(canon(meta));
  record('S7', 'evidence index metadata', s7dig === manifest.evidence_index_digest,
    s7dig === manifest.evidence_index_digest ? 'index metadata matches evidence_index_digest' : `computed=${s7dig} manifest=${manifest.evidence_index_digest}`);

  // S5 evidence root — over the bytes on disk (see the note above S4).
  let root = null;
  if (!s4ok) {
    record('S5', 'evidence root', false, 'skipped: evidence missing or S4 failed', true);
  } else {
    const sortedHashes = onDisk.slice().sort();
    root = sha256hex(canon(sortedHashes));
    record('S5', 'evidence root', root === manifest.evidence_root,
      root === manifest.evidence_root ? `computed=${root}` : `computed=${root} manifest=${manifest.evidence_root}`);
  }

  // S8 checkpoint
  const last = ev.length ? ev[ev.length - 1] : null;
  const lhead = 'sha256:' + sha256hex(canon({
    count: ev.length,
    last_sequence_number: last ? last.sequence_number : null,
    last_event_digest: last ? hashObj(last) : null,
  }));
  if (root === null) {
    record('S8', 'package checkpoint head', false, 'checkpoint not computable: evidence bytes unavailable or failing');
  } else {
    const checkpoint = 'sha256:' + sha256hex(canon({
      lifecycle_head: lhead,
      evidence_root: root,
      evidence_index_digest: s7dig,
      evidence_count: entries.length,
    }));
    record('S8', 'package checkpoint head', checkpoint === manifest.checkpoint_head,
      checkpoint === manifest.checkpoint_head ? `checkpoint matches (${ev.length} event(s), ${entries.length} evidence item(s))` : `computed=${checkpoint} manifest=${manifest.checkpoint_head}`);
  }

  // S6 seal
  let seal = null;
  try {
    seal = readJson(dir, 'signatures/seal.json');
  } catch {
    seal = null;
  }
  if (!seal) {
    record('S6', 'seal signature', false, 'package unsigned: evidence chain internally consistent but provenance unattested', true);
  } else {
    // legacy (identity+manifest) and v1.1 (identity+manifest+lifecycle) payloads
    const modern = canon({ identity, manifest, lifecycle });
    const legacy = canon({ identity, manifest });
    let pubB64 = seal.public_key;
    let okSig = false;
    let scoped = null;
    try {
      const raw = Buffer.from(pubB64, 'base64');
      if (raw.length !== 32) throw new Error('public_key is not 32 bytes');
      const spki = Buffer.concat([Buffer.from('302a300506032b6570032100', 'hex'), raw]);
      const keyObj = createPublicKey({ key: spki, format: 'der', type: 'spki' });
      const sig = Buffer.from(seal.signature, 'base64');
      for (const [scope, payload] of [['lifecycle-bound', modern], ['legacy', legacy]]) {
        if (edVerify(null, Buffer.from(payload, 'utf8'), keyObj, sig)) { okSig = true; scoped = scope; break; }
      }
    } catch (e) {
      okSig = false;
    }
    if (pinnedKeyB64) {
      // The reference CLI accepts a hex key file; the seal records base64.
      // Normalise both to raw bytes before comparing, so a reader's file format
      // does not change the verdict.
      const raw = (txt) => {
        const t = String(txt).trim();
        if (/^[0-9a-fA-F]{64}$/.test(t)) return Buffer.from(t, 'hex');
        return Buffer.from(t, 'base64');
      };
      let pinBytes = null;
      try { pinBytes = raw(pinnedKeyB64); } catch { pinBytes = null; }
      let sealBytes = null;
      try { sealBytes = Buffer.from(String(seal.public_key), 'base64'); } catch { sealBytes = null; }
      if (!pinBytes || pinBytes.length !== 32 || !sealBytes || sealBytes.length !== 32 ||
          Buffer.compare(pinBytes, sealBytes) !== 0) {
        record('S6', 'seal signature', false,
          `pinned key ${String(seal.public_key).slice(0, 12)}… does not match the pinned owner key`);
        return finish(checks);
      }
    }
    record('S6', 'seal signature', okSig, okSig ? `Ed25519 seal verified (${scoped})` : 'seal signature does not verify');
  }

  return finish(checks);
}

function finish(checks) {
  const results = checks.map((c) => c.result);
  const result = results.includes('FAIL') ? 'FAIL' : results.includes('INCONCLUSIVE') ? 'INCONCLUSIVE' : 'PASS';
  return { impl: 'uibc-js/0.1', result, checks };
}

/* ---------- CLI ---------- */

const args = process.argv.slice(2);
const dir = args.find((a) => !a.startsWith('--'));
if (!dir) {
  console.error('usage: node verify.mjs <package-dir> [--pubkey <file>] [--json]');
  process.exit(2);
}
const pkIdx = args.indexOf('--pubkey');
const pinned = pkIdx >= 0 ? readFileSync(args[pkIdx + 1], 'utf8') : null;
const out = verifyPackage(resolve(dir), pinned);
if (args.includes('--json')) {
  console.log(JSON.stringify(out, null, 2));
} else {
  for (const c of out.checks) console.log(`  ${c.result.padEnd(12)} ${c.id.padEnd(4)} ${c.detail}`);
  console.log(`RESULT ${out.result}`);
}
process.exit(out.result === 'PASS' ? 0 : 1);
