#!/usr/bin/env node

/**
 * Fetch the latest Codex manual from the official OpenAI source.
 *
 * Reads a MANUAL_ACCESS_TOKEN from the environment.
 * Writes the manual to stdout as JSON with keys:
 *   manual {string}  - the full manual text
 *   version {string}  - version identifier
 *   fetchedAt {string}  - ISO-8601 timestamp
 */

import { writeFileSync } from "node:fs";

const TOKEN = process.env.MANUAL_ACCESS_TOKEN;
if (!TOKEN) {
  console.error("MANUAL_ACCESS_TOKEN is not set");
  process.exit(1);
}

const BASE_URL =
  process.env.CODEX_MANUAL_BASE_URL ??
  "https://developers.openai.com/api/docs/manual";

const headers = {
  Authorization: `Bearer ${TOKEN}`,
  Accept: "application/json",
  "User-Agent": "codex-manual-fetcher/1.0",
};

/**
 * Fetch a URL with retries on transient failures.
 * @param {string} url
 * @param {RequestInit} [init]
 * @param {{ retries?: number, backoffMs?: number }} [opts]
 * @returns {Promise<Response>}
 */
async function fetchWithRetry(url, init, { retries = 3, backoffMs = 500 } = {}) {
  let lastError;
  for (let attempt = 1; attempt <= retries; attempt++) {
    try {
      const res = await fetch(url, { ...init, headers });
      if (res.ok) return res;

      // Do not retry client errors except 429.
      if (res.status >= 400 && res.status < 500 && res.status !== 429) {
        const body = await res.text().catch(() => "");
        throw new Error(
          `Fetch failed with status ${res.status}${body ? `: ${body}` : ""}`
        );
      }

      lastError = new Error(`Fetch returned status ${res.status}`);
    } catch (err) {
      if (err instanceof TypeError || err.cause) {
        // Network-level error.
        lastError = err;
      } else {
        throw err;
      }
    }

    if (attempt < retries) {
      const delay = backoffMs * 2 ** (attempt - 1);
      console.error(
        `Attempt ${attempt} failed, retrying in ${delay}ms...`
      );
      await new Promise((resolve) => setTimeout(resolve, delay));
    }
  }

  throw lastError ?? new Error("Fetch failed after retries");
}

/**
 * Fetch the manual index listing available versions.
 * @returns {Promise<Array<{ id: string, version: string, publishedAt: string }>>}
 */
async function fetchIndex() {
  console.error("Fetching manual index...");
  const res = await fetchWithRetry(`${BASE_URL}/index.json`);
  const body = await res.json();

  if (!body?.entries?.length) {
    throw new Error("Manual index returned no entries");
  }

  return body.entries;
}

/**
 * Fetch a specific manual version.
 * @param {string} versionId
 * @returns {Promise<{ manual: string, version: string, fetchedAt: string }>}
 */
async function fetchVersion(versionId) {
  console.error(`Fetching manual version ${versionId}...`);
  const res = await fetchWithRetry(`${BASE_URL}/${versionId}.json`);
  const body = await res.json();

  if (!body?.content) {
    throw new Error(`Manual version ${versionId} has no content`);
  }

  return {
    manual: body.content,
    version: body.version ?? versionId,
    fetchedAt: new Date().toISOString(),
  };
}

/**
 * Determine the stable version to fetch.
 *
 * Strategy:
 * 1. If CODEX_MANUAL_VERSION is set, use that exact version.
 * 2. Otherwise pick the latest published entry from the index.
 *
 * @param {Array<{ id: string, version: string, publishedAt: string }>} entries
 * @returns {string}
 */
function resolveVersion(entries) {
  const envVersion = process.env.CODEX_MANUAL_VERSION;
  if (envVersion) {
    const match = entries.find(
      (e) => e.id === envVersion || e.version === envVersion
    );
    if (match) return match.id;
    console.error(
      `Requested version ${envVersion} not found in index; falling back to latest`
    );
  }

  // Sort by publishedAt descending.
  const sorted = [...entries].sort(
    (a, b) => new Date(b.publishedAt) - new Date(a.publishedAt)
  );
  if (!sorted.length) throw new Error("No versions available");

  console.error(`Resolved to version ${sorted[0].id} (${sorted[0].version})`);
  return sorted[0].id;
}

/**
 * Write the manual to an output file or stdout.
 * @param {{ manual: string, version: string, fetchedAt: string }} result
 */
function outputResult(result) {
  const outPath = process.env.CODEX_MANUAL_OUTPUT;
  const json = JSON.stringify(result, null, 2);

  if (outPath) {
    writeFileSync(outPath, json, "utf-8");
    console.error(`Manual written to ${outPath}`);
  } else {
    process.stdout.write(json);
  }
}

// --- Main ---

async function main() {
  try {
    const entries = await fetchIndex();
    const versionId = resolveVersion(entries);
    const result = await fetchVersion(versionId);
    outputResult(result);
  } catch (err) {
    console.error(err.message);
    process.exit(1);
  }
}

main();
