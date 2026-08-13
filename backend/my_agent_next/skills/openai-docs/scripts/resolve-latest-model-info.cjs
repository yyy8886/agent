#!/usr/bin/env node

/**
 * Resolve the latest OpenAI model metadata by fetching the live latest-model
 * guide.  Prints a JSON object to stdout with keys:
 *
 *   model              {string}  - the current recommended model ID
 *   migrationGuideUrl  {string}  - URL of the current migration guide
 *   promptingGuideUrl  {string}  - URL of the current prompting guide
 *   fetchedAt          {string}  - ISO-8601 timestamp
 *
 * Environment:
 *   LATEST_MODEL_URL   override the default guide URL
 *   LATEST_MODEL_TOKEN optional Bearer token for the request
 */

"use strict";

const DEFAULT_URL =
  process.env.LATEST_MODEL_URL ??
  "https://developers.openai.com/api/docs/guides/latest-model";

async function fetchGuide(url, token) {
  const headers = { Accept: "application/json" };
  if (token) headers.Authorization = `Bearer ${token}`;

  const res = await fetch(url, { headers });
  if (!res.ok) {
    throw new Error(`Failed to fetch ${url}: status ${res.status}`);
  }
  return res.json();
}

/**
 * Extract the first model ID found in the guide's JSON structure.
 * Walks common shapes: body.model, body.recommendedModel, body.currentModel,
 * and top-level model.
 */
function extractModel(body) {
  if (typeof body !== "object" || body === null) return undefined;

  // Direct model field on body.
  if (typeof body.model === "string" && body.model) return body.model;
  if (typeof body.recommendedModel === "string" && body.recommendedModel) {
    return body.recommendedModel;
  }
  if (typeof body.currentModel === "string" && body.currentModel) {
    return body.currentModel;
  }

  // Walk the document looking for a model slug (e.g. gpt-5.6-sol).
  const slugRe = /^(gpt-\d[.\w-]*[a-z]+)\b/i;
  const stack = [body];
  const visited = new Set();

  while (stack.length) {
    const node = stack.pop();
    if (visited.has(node)) continue;
    visited.add(node);

    if (typeof node === "string") {
      const m = node.match(slugRe);
      if (m) return m[1];
      continue;
    }

    if (Array.isArray(node)) {
      for (let i = node.length - 1; i >= 0; i--) stack.push(node[i]);
    } else if (typeof node === "object" && node !== null) {
      const values = Object.values(node);
      for (let i = values.length - 1; i >= 0; i--) stack.push(values[i]);
    }
  }

  return undefined;
}

/**
 * Build the migration and prompting guide URLs from a resolved model slug.
 */
function buildGuideUrls(model) {
  const base = "https://developers.openai.com/api/docs/guides";
  return {
    migrationGuideUrl: `${base}/model-guidance?model=${model}`,
    promptingGuideUrl: `${base}/model-guidance?model=${model}#prompting-best-practices`,
  };
}

async function main() {
  const url = DEFAULT_URL;
  const token = process.env.LATEST_MODEL_TOKEN || undefined;

  let body;
  try {
    body = await fetchGuide(url, token);
  } catch (err) {
    console.error(`Fetch error: ${err.message}`);
    process.exit(1);
  }

  const model = extractModel(body);
  if (!model) {
    console.error("Could not extract model ID from latest-model guide");
    process.exit(1);
  }

  const { migrationGuideUrl, promptingGuideUrl } = buildGuideUrls(model);

  const result = {
    model,
    migrationGuideUrl,
    promptingGuideUrl,
    fetchedAt: new Date().toISOString(),
  };

  process.stdout.write(JSON.stringify(result));
}

main();
