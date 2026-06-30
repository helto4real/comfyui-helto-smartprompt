import { app } from "../../scripts/app.js";

const NODE_CLASS = "SmartPromptManager";
const EXTENSION_NAME = "helto.smartPromptManager";
const VALID_NAME_RE = /^[A-Za-z0-9_-]+$/;
const TOKEN_RE = /\{\{([^{}]*)\}\}/g;
const MODES = ["random", "fixed", "cycle"];
const SEED_CONTROL_MODES = ["fixed", "increment", "decrement", "randomize"];
const SEED_MAX = Number.MAX_SAFE_INTEGER;
const SPM_CACHE_TOKEN_PREFIX = "spm-cache-v1:";
const SPM_PRIVACY_FIELD = "spm_data";
const SPM_SEED_QUEUE_WRAPPER_KEY = "__smartPromptManagerSeedQueuePromptWrapper";
const SPM_SEED_QUEUE_INSTALL_KEY = "__smartPromptManagerSeedQueuePromptInstallScheduled";
const SPM_GRAPH_TO_PROMPT_WRAPPER_KEY = "__smartPromptManagerGraphToPromptWrapper";
const SPM_GRAPH_TO_PROMPT_INSTALL_KEY = "__smartPromptManagerGraphToPromptInstallScheduled";
const SPM_SEED_QUEUE_INSTALL_ATTEMPT_LIMIT = 80;
const VIRTUAL_FOLDERS = [
  { id: "all", name: "All" },
  { id: "unsorted", name: "Unsorted" },
  { id: "favorites", name: "Favorites" },
];
let spmQueuePromptDepth = 0;
const KEYS = {
  next: "n",
  previous: "p",
  accept: "y",
  close: "Escape",
};
const PANEL_MIN_WIDTH = 420;
const PANEL_DEFAULT_WIDTH = 520;
const PANEL_MIN_HEIGHT = 340;
const PANEL_DEFAULT_HEIGHT = 500;
const NODE_CHROME_HEIGHT = 220;
const PANEL_HORIZONTAL_GUTTER = 0;
const PANEL_BOTTOM_GUTTER = 8;
const ICON_PATHS = {
  add: "M12 5v14M5 12h14",
  check: "M20 6 9 17l-5-5",
  close: "M18 6 6 18M6 6l12 12",
  copy: "M8 8h10v10H8zM6 16H4V4h10v2",
  delete: "M3 6h18M8 6V4h8v2M6 6l1 14h10l1-14M10 10v6M14 10v6",
  duplicate: "M8 8h10v10H8zM6 16H4V4h10v2",
  export: "M12 3v12M7 8l5-5 5 5M5 21h14",
  folder: "M3 6h7l2 2h9v10H3z",
  importMerge: "M12 21V9M7 14l5 5 5-5M4 5h7l2 2h7",
  importReplace: "M12 21V9M7 14l5 5 5-5M6 5h12",
  json: "M9 5H6v14h3M15 5h3v14h-3",
  paste: "M9 5h6M9 3h6v4H9zM7 5H5v16h14V5h-2",
  prompts: "M5 4h14v16H5zM8 8h8M8 12h8M8 16h5",
  reroll: "M4 4v6h6M20 20v-6h-6M20 9a7 7 0 0 0-12-4L4 10M4 15a7 7 0 0 0 12 4l4-5",
  select: "M8 12h8M13 7l5 5-5 5",
  selected: "M20 6 9 17l-5-5",
  variable: "M8 4c-2 3-2 13 0 16M16 4c2 3 2 13 0 16M10 9h4M10 15h4",
};

function nowIso() {
  return new Date().toISOString().replace(/\.\d{3}Z$/, "Z");
}

function makeId(prefix) {
  if (crypto?.randomUUID) return `${prefix}_${crypto.randomUUID().replaceAll("-", "").slice(0, 12)}`;
  return `${prefix}_${Math.random().toString(16).slice(2, 14)}`;
}

function randomUnit53() {
  if (globalThis.crypto?.getRandomValues) {
    const values = new Uint32Array(2);
    globalThis.crypto.getRandomValues(values);
    return (((values[0] & 0x1fffff) * 0x100000000) + values[1]) / 0x20000000000000;
  }
  return Math.random();
}

function randomSeed() {
  return Math.floor(randomUnit53() * SEED_MAX) + 1;
}

function widgetByName(node, name) {
  return node?.widgets?.find((widget) => widget?.name === name) || null;
}

function isSmartPromptManagerNode(node) {
  return (
    node?.type === NODE_CLASS ||
    node?.comfyClass === NODE_CLASS ||
    node?.constructor?.type === NODE_CLASS ||
    node?.constructor?.comfyClass === NODE_CLASS ||
    node?.title === "Smart Prompt Manager"
  );
}

function defaultGraph() {
  return app.rootGraph || app.graph;
}

function graphNodes(graph = defaultGraph()) {
  const nodes = [];
  const seenNodes = new Set();
  const seenGraphs = new Set();

  function visit(currentGraph) {
    if (!currentGraph || seenGraphs.has(currentGraph)) return;
    seenGraphs.add(currentGraph);
    for (const node of currentGraph.nodes || currentGraph._nodes || []) {
      if (!node || seenNodes.has(node)) continue;
      seenNodes.add(node);
      nodes.push(node);
      if (node.subgraph) visit(node.subgraph);
    }
    for (const subgraph of currentGraph.subgraphs?.values?.() || []) {
      visit(subgraph);
    }
  }

  visit(graph);
  return nodes;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function iconSvg(name) {
  const path = ICON_PATHS[name] || ICON_PATHS.check;
  return `<svg class="spm-icon" viewBox="0 0 24 24" aria-hidden="true"><path d="${path}"></path></svg>`;
}

function iconButton(icon, label, attrs = "", className = "") {
  return `<button class="spm-btn ${className}" title="${escapeHtml(label)}" aria-label="${escapeHtml(label)}" ${attrs}>${iconSvg(icon)}<span class="spm-sr-only">${escapeHtml(label)}</span></button>`;
}

function privacySwitch({ checked = false, disabled = false } = {}) {
  const title = "Encrypt prompt library JSON in saved workflows";
  return `<label class="spm-privacy-toggle" title="${title}"><span>Privacy mode</span><span class="spm-switch"><input type="checkbox" aria-label="Privacy mode" title="${title}" data-privacy-mode ${checked ? "checked" : ""} ${disabled ? "disabled" : ""}><span class="spm-switch-slider"></span></span></label>`;
}

function stableHash(text) {
  let value = 2166136261;
  for (let i = 0; i < text.length; i += 1) {
    value ^= text.charCodeAt(i);
    value = Math.imul(value, 16777619) >>> 0;
  }
  return value >>> 0;
}

function bytesToHex(bytes) {
  return [...bytes].map((byte) => byte.toString(16).padStart(2, "0")).join("");
}

async function sha256Hex(text) {
  if (globalThis.crypto?.subtle && globalThis.TextEncoder) {
    const data = new TextEncoder().encode(String(text ?? ""));
    const digest = await globalThis.crypto.subtle.digest("SHA-256", data);
    return bytesToHex(new Uint8Array(digest));
  }
  return stableHash(String(text ?? "")).toString(16).padStart(8, "0");
}

function defaultState() {
  const folderId = makeId("folder");
  const promptId = makeId("prompt");
  const created = nowIso();
  return {
    version: 1,
    selectedFolderId: "all",
    selectedPromptId: promptId,
    search: "",
    privacyMode: false,
    folders: [{ id: folderId, name: "Portraits", hidden: false }],
    prompts: [
      {
        id: promptId,
        title: "Cinematic portrait",
        text: "A {{mood}} cinematic portrait of {{character}} in {{lighting}}.",
        description: "Starter prompt showing Smart Prompt Manager variables.",
        folderId,
        tags: ["portrait", "cinematic"],
        favorite: false,
        locked: false,
        hidden: false,
        createdAt: created,
        updatedAt: created,
      },
    ],
    variables: {
      mood: {
        mode: "random",
        values: ["dreamy", "melancholic", "dramatic"],
        fixedValue: null,
        fallback: "dreamy",
        description: "Overall emotional tone.",
      },
      character: {
        mode: "random",
        values: ["cyberpunk detective", "medieval knight", "astronaut"],
        fixedValue: null,
        fallback: "astronaut",
        description: "Main subject.",
      },
      lighting: {
        mode: "random",
        values: ["golden hour", "neon rim light", "soft studio light"],
        fixedValue: null,
        fallback: "soft studio light",
        description: "Lighting setup.",
      },
    },
    cycleState: {},
    ui: { collapsedSections: {} },
  };
}

function normalizeValues(value) {
  if (Array.isArray(value)) return value.map((item) => String(item ?? "").trim()).filter(Boolean);
  if (typeof value === "string") return value.split(/\r?\n/).map((item) => item.trim()).filter(Boolean);
  return [];
}

function normalizeTags(value) {
  const parts = Array.isArray(value) ? value : String(value ?? "").split(/[,#\n]/);
  const seen = new Set();
  const tags = [];
  for (const part of parts) {
    const tag = String(part ?? "").trim();
    if (tag && !seen.has(tag.toLowerCase())) {
      seen.add(tag.toLowerCase());
      tags.push(tag);
    }
  }
  return tags;
}

function tagsFromDraft(value) {
  return String(value ?? "").split(",");
}

function tagsForInput(value) {
  if (!Array.isArray(value)) return String(value ?? "");
  return value.join(",");
}

function parseState(value) {
  let parsed = {};
  if (value && typeof value === "object") parsed = value;
  if (typeof value === "string" && value.trim()) {
    try {
      parsed = JSON.parse(value);
    } catch {
      parsed = {};
    }
  }
  return normalizeState(parsed);
}

function parseJsonObject(value) {
  if (value && typeof value === "object") return value;
  if (typeof value !== "string" || !value.trim()) return {};
  try {
    const parsed = JSON.parse(value);
    return parsed && typeof parsed === "object" ? parsed : {};
  } catch {
    return {};
  }
}

function isEncryptedStateValue(value) {
  const parsed = parseJsonObject(value);
  return parsed.encrypted === true && parsed.schema === "comfyui-helto-prompts.smart-prompt-manager";
}

// ---- Privacy envelope memo helpers ----
const SPM_PRIVACY_MEMOS = new WeakMap();

function stableCanonicalValue(value) {
  if (Array.isArray(value)) return value.map((item) => stableCanonicalValue(item));
  if (value && typeof value === "object") {
    const result = {};
    for (const key of Object.keys(value).sort()) {
      result[key] = stableCanonicalValue(value[key]);
    }
    return result;
  }
  return value;
}

function canonicalPrivacyPlaintext(value) {
  const canonical = JSON.stringify(stableCanonicalValue(value));
  return canonical === undefined ? "null" : canonical;
}

function isPrivacyEnvelopeValue(value) {
  const parsed = parseJsonObject(value);
  return parsed.encrypted === true && parsed.schema === "comfyui-helto-prompts.smart-prompt-manager";
}

export function encryptedPrivacyEnvelopeString(value) {
  if (!isPrivacyEnvelopeValue(value)) return "";
  return typeof value === "string" ? value : JSON.stringify(value, null, 2);
}

function privacyMemoBucket(owner, create = false) {
  if (!owner || (typeof owner !== "object" && typeof owner !== "function")) return null;
  let bucket = SPM_PRIVACY_MEMOS.get(owner);
  if (!bucket && create) {
    bucket = new Map();
    SPM_PRIVACY_MEMOS.set(owner, bucket);
  }
  return bucket || null;
}

export function rememberPrivacyEnvelope(owner, fieldName, plaintext, envelope) {
  const envelopeString = encryptedPrivacyEnvelopeString(envelope);
  if (!envelopeString) return "";
  const bucket = privacyMemoBucket(owner, true);
  if (!bucket) return envelopeString;
  bucket.set(String(fieldName), {
    canonicalPlaintext: canonicalPrivacyPlaintext(plaintext),
    envelopeString,
    pending: null,
  });
  return envelopeString;
}

export function rememberedPrivacyEnvelope(owner, fieldName, plaintext) {
  const bucket = privacyMemoBucket(owner, false);
  const memo = bucket?.get(String(fieldName));
  if (!memo) return "";
  return memo.canonicalPlaintext === canonicalPrivacyPlaintext(plaintext) ? memo.envelopeString : "";
}

export function forgetPrivacyEnvelope(owner, fieldName) {
  const bucket = privacyMemoBucket(owner, false);
  if (!bucket) return;
  bucket.delete(String(fieldName));
}

export async function encryptedOrReusePrivacyValue(owner, fieldName, currentValue, encryptFn) {
  const currentEnvelope = encryptedPrivacyEnvelopeString(currentValue);
  if (currentEnvelope) return currentEnvelope;

  const canonicalPlaintext = canonicalPrivacyPlaintext(currentValue);
  const bucket = privacyMemoBucket(owner, true);
  if (!bucket) return encryptedPrivacyEnvelopeString(await encryptFn(JSON.parse(canonicalPlaintext)));

  const key = String(fieldName);
  let memo = bucket.get(key);
  if (memo?.canonicalPlaintext === canonicalPlaintext && memo.envelopeString) {
    return memo.envelopeString;
  }
  if (memo?.pending?.canonicalPlaintext === canonicalPlaintext) {
    return memo.pending.promise;
  }

  if (!memo) {
    memo = { canonicalPlaintext: "", envelopeString: "", pending: null };
    bucket.set(key, memo);
  }
  const plaintextSnapshot = JSON.parse(canonicalPlaintext);
  const pending = {
    canonicalPlaintext,
    promise: null,
  };
  pending.promise = Promise.resolve(encryptFn(plaintextSnapshot))
    .then((envelope) => {
      const envelopeString = encryptedPrivacyEnvelopeString(envelope);
      if (!envelopeString) throw new Error("Privacy encryption did not return an encrypted Smart Prompt Manager envelope.");
      const latest = bucket.get(key);
      if (latest?.pending === pending) {
        latest.canonicalPlaintext = canonicalPlaintext;
        latest.envelopeString = envelopeString;
        latest.pending = null;
      }
      return envelopeString;
    })
    .catch((error) => {
      const latest = bucket.get(key);
      if (latest?.pending === pending) latest.pending = null;
      throw error;
    });
  memo.pending = pending;
  return pending.promise;
}
// ---- End privacy envelope memo helpers ----

function normalizeState(data) {
  if (!data || typeof data !== "object") return defaultState();
  const state = defaultState();
  const folders = [];
  const folderIds = new Set();
  for (const folder of Array.isArray(data.folders) ? data.folders : []) {
    if (!folder || typeof folder !== "object") continue;
    let id = String(folder.id || "").trim();
    if (!id || folderIds.has(id) || ["all", "unsorted", "favorites"].includes(id)) id = makeId("folder");
    folderIds.add(id);
    const rawName = String(folder.name ?? "");
    folders.push({ id, name: rawName.trim() ? rawName : "Folder", hidden: Boolean(folder.hidden) });
  }
  const prompts = [];
  const promptIds = new Set();
  for (const prompt of Array.isArray(data.prompts) ? data.prompts : []) {
    if (!prompt || typeof prompt !== "object") continue;
    let id = String(prompt.id || "").trim();
    if (!id || promptIds.has(id)) id = makeId("prompt");
    promptIds.add(id);
    const folderId = folderIds.has(prompt.folderId) ? prompt.folderId : "";
    const rawTitle = String(prompt.title ?? "");
    prompts.push({
      id,
      title: rawTitle.trim() ? rawTitle : "Untitled prompt",
      text: String(prompt.text ?? ""),
      description: String(prompt.description ?? ""),
      folderId,
      tags: normalizeTags(prompt.tags),
      favorite: Boolean(prompt.favorite),
      locked: Boolean(prompt.locked),
      hidden: Boolean(prompt.hidden),
      createdAt: String(prompt.createdAt || nowIso()),
      updatedAt: String(prompt.updatedAt || nowIso()),
    });
  }
  const variables = {};
  const rawVariables = data.variables && typeof data.variables === "object" ? data.variables : {};
  for (const [name, rawDefinition] of Object.entries(rawVariables)) {
    if (!VALID_NAME_RE.test(name)) continue;
    const definition = rawDefinition && typeof rawDefinition === "object" ? rawDefinition : {};
    const mode = MODES.includes(String(definition.mode || "").toLowerCase())
      ? String(definition.mode).toLowerCase()
      : "random";
    variables[name] = {
      mode,
      values: normalizeValues(definition.values),
      fixedValue: definition.fixedValue == null ? null : String(definition.fixedValue),
      fallback: String(definition.fallback ?? ""),
      description: String(definition.description ?? ""),
    };
  }
  const selectedFolderId =
    ["all", "unsorted", "favorites"].includes(data.selectedFolderId) || folderIds.has(data.selectedFolderId)
      ? data.selectedFolderId
      : "all";
  const selectedPromptId = promptIds.has(data.selectedPromptId)
    ? data.selectedPromptId
    : prompts[0]?.id || "";
  return {
    version: 1,
    selectedFolderId,
    selectedPromptId,
    search: String(data.search ?? ""),
    privacyMode: Boolean(data.privacyMode),
    folders,
    prompts,
    variables,
    cycleState: data.cycleState && typeof data.cycleState === "object" ? { ...data.cycleState } : {},
    ui:
      data.ui && typeof data.ui === "object"
        ? { collapsedSections: { ...(data.ui.collapsedSections || {}) } }
        : state.ui,
  };
}

function selectedPrompt(state) {
  return state.prompts.find((prompt) => prompt.id === state.selectedPromptId) || state.prompts[0] || null;
}

function folderName(state, folderId) {
  if (!folderId) return "Unsorted";
  return state.folders.find((folder) => folder.id === folderId)?.name || "Missing folder";
}

function folderById(state, folderId) {
  if (!folderId) return null;
  return state.folders.find((folder) => folder.id === folderId) || null;
}

function isPreviewHidden(state, prompt) {
  if (!prompt) return false;
  return Boolean(prompt.hidden || folderById(state, prompt.folderId)?.hidden);
}

function hasHiddenPreviews(state) {
  return state.prompts.some((prompt) => isPreviewHidden(state, prompt));
}

function variablesUsed(text) {
  TOKEN_RE.lastIndex = 0;
  const used = [];
  const seen = new Set();
  let match;
  while ((match = TOKEN_RE.exec(String(text ?? "")))) {
    const name = match[1].trim();
    if (VALID_NAME_RE.test(name) && !seen.has(name)) {
      seen.add(name);
      used.push(name);
    }
  }
  return used;
}

function selectVariableValue(name, definition, seed, reroll, cycleState, warnings) {
  const mode = MODES.includes(definition?.mode) ? definition.mode : "random";
  const values = normalizeValues(definition?.values);
  const fallback = String(definition?.fallback || "").trim();
  const candidates = values.length ? values : fallback ? [fallback] : [];
  if (!values.length) warnings.push(`Variable '${name}' has no values.`);
  if (mode === "fixed") {
    const fixed = String(definition?.fixedValue || "").trim();
    if (fixed) return fixed;
    if (fallback) return fallback;
    return values[0] || "";
  }
  if (!candidates.length) return "";
  if (mode === "cycle") {
    const base = Number.parseInt(cycleState?.[name] || 0, 10) || 0;
    return candidates[(base + (Number.parseInt(reroll, 10) || 0)) % candidates.length];
  }
  const index = stableHash(`${Number.parseInt(seed, 10) || 0}:${Number.parseInt(reroll, 10) || 0}:${name}`) % candidates.length;
  return candidates[index];
}

function resolvePrompt(text, variables, seed, reroll, cycleState) {
  const warnings = [];
  const selected = {};
  const missing = [];
  const used = [];
  const resolved = String(text ?? "").replace(TOKEN_RE, (token, rawName) => {
    const name = rawName.trim();
    if (!name || !VALID_NAME_RE.test(name)) {
      warnings.push(`Invalid variable token ${token}.`);
      return token;
    }
    if (!used.includes(name)) used.push(name);
    const definition = variables?.[name];
    if (!definition) {
      if (!missing.includes(name)) missing.push(name);
      warnings.push(`Variable '${name}' is referenced but not defined.`);
      return token;
    }
    if (!(name in selected)) selected[name] = selectVariableValue(name, definition, seed, reroll, cycleState, warnings);
    return selected[name] || token;
  });
  return { resolved_prompt: resolved, selected_values: selected, missing_variables: missing, variables_used: used, warnings };
}

function validateState(state) {
  const warnings = [];
  const titleCounts = new Map();
  for (const prompt of state.prompts) {
    const title = prompt.title.trim().toLowerCase();
    if (title) titleCounts.set(title, (titleCounts.get(title) || 0) + 1);
    for (const name of variablesUsed(prompt.text)) {
      if (!state.variables[name]) warnings.push(`Prompt '${prompt.title}' references undefined variable '${name}'.`);
    }
  }
  for (const [title, count] of titleCounts) {
    if (count > 1) warnings.push(`Duplicate prompt name: ${title}.`);
  }
  const used = new Set(state.prompts.flatMap((prompt) => variablesUsed(prompt.text)));
  for (const [name, definition] of Object.entries(state.variables)) {
    if (!VALID_NAME_RE.test(name)) warnings.push(`Invalid variable name: ${name}.`);
    if (!normalizeValues(definition.values).length && !String(definition.fallback || "").trim()) {
      warnings.push(`Variable '${name}' has no values.`);
    }
    if (!used.has(name)) warnings.push(`Variable '${name}' is not used by any prompt.`);
  }
  if (state.selectedPromptId && !state.prompts.some((prompt) => prompt.id === state.selectedPromptId)) warnings.push("Selected prompt is missing.");
  return warnings;
}

function suffixName(name, existing) {
  const existingLower = new Set(existing.map((value) => String(value).toLowerCase()));
  const base = String(name || "Untitled prompt").trim() || "Untitled prompt";
  let candidate = `${base} copy`;
  let index = 2;
  while (existingLower.has(candidate.toLowerCase())) {
    candidate = `${base} copy ${index}`;
    index += 1;
  }
  return candidate;
}

function setWidgetValue(node, widget, state) {
  if (!widget) return;
  widget.value = JSON.stringify(state, null, 2);
  writeSerializedWidgetValue(node, widget, widget.value);
  markNodeDirty(node);
}

function setWidgetRawValue(node, widget, value) {
  if (!widget) return;
  widget.value = value;
  writeSerializedWidgetValue(node, widget, value);
  markNodeDirty(node);
}

function markNodeDirty(node) {
  if (typeof node?.setDirtyCanvas === "function") {
    node.setDirtyCanvas(true, true);
  } else {
    app.graph?.setDirtyCanvas?.(true, true);
  }
  node?.graph?.setDirtyCanvas?.(true, true);
  app.canvas?.setDirty?.(true, true);
}

function validSeedControlMode(value) {
  return SEED_CONTROL_MODES.includes(value) ? value : null;
}

function isSeedControlWidget(widget, seedWidget = null) {
  const values = widget?.options?.values;
  const seedName = String(seedWidget?.name || "seed");
  return (
    widget?.name === "control_after_generate" ||
    widget?.name === `${seedName}.control_after_generate` ||
    widget?.name === `${seedName}_control_after_generate` ||
    (Array.isArray(values) && SEED_CONTROL_MODES.every((value) => values.includes(value)))
  );
}

function seedControlWidget(node, seedWidget = widgetByName(node, "seed")) {
  for (const widget of seedWidget?.linkedWidgets || []) {
    if (isSeedControlWidget(widget, seedWidget)) {
      return widget;
    }
  }
  return node?.widgets?.find((widget) => widget !== seedWidget && isSeedControlWidget(widget, seedWidget)) || null;
}

function liveSeedControlMode(node) {
  const seedWidget = widgetByName(node, "seed");
  const controlWidget = seedControlWidget(node, seedWidget);
  return (
    validSeedControlMode(controlWidget?.value) ??
    validSeedControlMode(seedWidget?.control_after_generate) ??
    validSeedControlMode(seedWidget?.options?.control_after_generate)
  );
}

function writeWidgetValue(node, widget, value) {
  if (!node || !widget) return false;
  const previousValue = widget.value;
  widget.value = value;
  widget.callback?.(value, app.canvas, node, widget);
  node.onWidgetChanged?.(widget.name ?? "", value, previousValue, widget);
  node.graph?.incrementVersion?.();
  markNodeDirty(node);
  return true;
}

function widgetSerializesToWorkflow(widget) {
  return Boolean(widget) && widget.serialize !== false && widget.options?.serialize !== false;
}

function serializedWidgetIndex(node, targetWidget) {
  let serializedIndex = 0;
  for (const widget of node?.widgets || []) {
    if (widget === targetWidget) {
      return widgetSerializesToWorkflow(widget) ? serializedIndex : -1;
    }
    if (widgetSerializesToWorkflow(widget)) {
      serializedIndex += 1;
    }
  }
  return -1;
}

function writeSerializedWidgetValue(node, widget, value) {
  const index = serializedWidgetIndex(node, widget);
  for (const values of [node?.widgets_values, node?.last_serialization?.widgets_values]) {
    if (Array.isArray(values) && index >= 0 && index < values.length) {
      values[index] = value;
    }
  }
}

function writeSpmSeedValue(node, seed) {
  const seedWidget = widgetByName(node, "seed");
  if (!writeWidgetValue(node, seedWidget, seed)) {
    return false;
  }
  writeSerializedWidgetValue(node, seedWidget, seed);
  return true;
}

function suspendSeedControlCallbacks(controlWidget) {
  if (!controlWidget) return null;
  const beforeQueued = controlWidget.beforeQueued;
  const afterQueued = controlWidget.afterQueued;
  const beforeQueuedNoop = () => {};
  const afterQueuedNoop = () => {};
  controlWidget.beforeQueued = beforeQueuedNoop;
  controlWidget.afterQueued = afterQueuedNoop;
  return {
    controlWidget,
    beforeQueued,
    afterQueued,
    beforeQueuedNoop,
    afterQueuedNoop,
  };
}

function restoreSeedControlCallbacks(suspended) {
  for (const item of suspended) {
    if (item.controlWidget.beforeQueued === item.beforeQueuedNoop) {
      item.controlWidget.beforeQueued = item.beforeQueued;
    }
    if (item.controlWidget.afterQueued === item.afterQueuedNoop) {
      item.controlWidget.afterQueued = item.afterQueued;
    }
  }
}

function randomizeSpmSeedsBeforeQueue() {
  const queuedSeeds = [];
  for (const node of graphNodes()) {
    if (!isSmartPromptManagerNode(node) || liveSeedControlMode(node) !== "randomize") {
      continue;
    }
    const seedWidget = widgetByName(node, "seed");
    const controlWidget = seedControlWidget(node, seedWidget);
    const seed = randomSeed();
    if (!writeSpmSeedValue(node, seed)) {
      continue;
    }
    node._spmQueuedSeed = { seed, at: Date.now() };
    queuedSeeds.push({
      node,
      seed,
      suspended: suspendSeedControlCallbacks(controlWidget),
    });
  }
  return queuedSeeds;
}

function restoreQueuedSpmSeeds(queuedSeeds) {
  restoreSeedControlCallbacks(queuedSeeds.map((item) => item.suspended).filter(Boolean));
  for (const { node, seed } of queuedSeeds) {
    const queuedSeed = node?._spmQueuedSeed;
    if (!queuedSeed || queuedSeed.seed !== seed || Date.now() - queuedSeed.at > 10000) {
      continue;
    }
    if (Number(widgetByName(node, "seed")?.value) !== Number(seed)) {
      writeSpmSeedValue(node, seed);
    }
  }
}

function installSpmSeedQueuePatch(source = "install") {
  if (typeof app.queuePrompt !== "function") {
    return false;
  }
  if (app.queuePrompt[SPM_SEED_QUEUE_WRAPPER_KEY]) {
    return true;
  }

  const originalQueuePrompt = app.queuePrompt;
  const wrappedQueuePrompt = async function (...args) {
    const queuedSeeds = randomizeSpmSeedsBeforeQueue();
    spmQueuePromptDepth += 1;
    try {
      return await originalQueuePrompt.apply(this, args);
    } finally {
      spmQueuePromptDepth = Math.max(0, spmQueuePromptDepth - 1);
      restoreQueuedSpmSeeds(queuedSeeds);
    }
  };
  Object.defineProperty(wrappedQueuePrompt, SPM_SEED_QUEUE_WRAPPER_KEY, {
    value: true,
    configurable: true,
  });
  app.queuePrompt = wrappedQueuePrompt;
  return true;
}

function scheduleSpmSeedQueuePatch(source = "top-level") {
  if (globalThis[SPM_SEED_QUEUE_INSTALL_KEY]) {
    installSpmSeedQueuePatch(`${source}:resync`);
    return;
  }
  globalThis[SPM_SEED_QUEUE_INSTALL_KEY] = true;

  let attempts = 0;
  function attempt() {
    attempts += 1;
    installSpmSeedQueuePatch(`${source}:${attempts}`);
    if (attempts < SPM_SEED_QUEUE_INSTALL_ATTEMPT_LIMIT) {
      setTimeout(attempt, 250);
    }
  }
  attempt();
}

function liveSpmExecutionState(node, outputNode = null) {
  const exposed = node?._spmExecutionState;
  if (exposed && typeof exposed === "object") {
    return normalizeState(exposed);
  }
  const rawValue = widgetByName(node, SPM_PRIVACY_FIELD)?.value ?? outputNode?.inputs?.spm_data;
  if (rawValue == null || rawValue === "" || (typeof rawValue === "string" && rawValue.startsWith(SPM_CACHE_TOKEN_PREFIX))) {
    return null;
  }
  if (isEncryptedStateValue(rawValue)) {
    return null;
  }
  return parseState(rawValue);
}

async function spmCacheTokenForNode(node, outputNode = null) {
  const state = liveSpmExecutionState(node, outputNode);
  let tokenSource = "";
  if (state) {
    const seed = Number.parseInt(widgetByName(node, "seed")?.value ?? outputNode?.inputs?.seed ?? 0, 10) || 0;
    const reroll = Number.parseInt(widgetByName(node, "reroll")?.value ?? outputNode?.inputs?.reroll ?? 0, 10) || 0;
    const prompt = selectedPrompt(state);
    tokenSource = resolvePrompt(prompt?.text || "", state.variables, seed, reroll, state.cycleState).resolved_prompt;
  } else {
    const encryptedValue = widgetByName(node, SPM_PRIVACY_FIELD)?.value ?? outputNode?.inputs?.spm_data;
    if (!encryptedValue) return null;
    tokenSource = `encrypted:${String(encryptedValue)}`;
  }
  return `${SPM_CACHE_TOKEN_PREFIX}${await sha256Hex(tokenSource)}`;
}

async function applySpmCacheTokensToPrompt(prompt, graph = defaultGraph()) {
  const output = prompt?.output;
  if (!output || typeof output !== "object") return prompt;
  const nodesById = new Map(graphNodes(graph).map((node) => [String(node.id), node]));
  for (const [nodeId, outputNode] of Object.entries(output)) {
    if (!outputNode || typeof outputNode !== "object" || outputNode.class_type !== NODE_CLASS) continue;
    const node = nodesById.get(String(nodeId)) || null;
    const token = await spmCacheTokenForNode(node, outputNode);
    if (!token) continue;
    outputNode.inputs ||= {};
    outputNode.inputs.spm_data = token;
    outputNode.is_changed = token;
  }
  return prompt;
}

function prepareSpmPrivacyForSerialization(graph = defaultGraph()) {
  return graphNodes(graph)
    .map((node) => node?._spmPreparePrivacySerialization?.())
    .filter(Boolean);
}

async function waitForSpmPrivacySaves(graph = defaultGraph()) {
  const pending = [
    ...prepareSpmPrivacyForSerialization(graph),
    ...graphNodes(graph)
      .map((node) => node?._spmPendingPrivacySave)
      .filter(Boolean),
  ];
  if (pending.length) {
    await Promise.all(pending.map((promise) => Promise.resolve(promise).catch(() => {})));
  }
}

function installSpmGraphToPromptPatch(source = "install") {
  if (typeof app.graphToPrompt !== "function") {
    return false;
  }
  if (app.graphToPrompt[SPM_GRAPH_TO_PROMPT_WRAPPER_KEY]) {
    return true;
  }

  const originalGraphToPrompt = app.graphToPrompt;
  const wrappedGraphToPrompt = async function (...args) {
    const graph = args[0] || this?.graph || defaultGraph();
    await waitForSpmPrivacySaves(graph);
    const prompt = await originalGraphToPrompt.apply(this, args);
    if (spmQueuePromptDepth > 0) {
      return await applySpmCacheTokensToPrompt(prompt, graph);
    }
    return prompt;
  };
  Object.defineProperty(wrappedGraphToPrompt, SPM_GRAPH_TO_PROMPT_WRAPPER_KEY, {
    value: true,
    configurable: true,
  });
  app.graphToPrompt = wrappedGraphToPrompt;
  return true;
}

function scheduleSpmGraphToPromptPatch(source = "top-level") {
  if (globalThis[SPM_GRAPH_TO_PROMPT_INSTALL_KEY]) {
    installSpmGraphToPromptPatch(`${source}:resync`);
    return;
  }
  globalThis[SPM_GRAPH_TO_PROMPT_INSTALL_KEY] = true;

  let attempts = 0;
  function attempt() {
    attempts += 1;
    installSpmGraphToPromptPatch(`${source}:${attempts}`);
    if (attempts < SPM_SEED_QUEUE_INSTALL_ATTEMPT_LIMIT) {
      setTimeout(attempt, 250);
    }
  }
  attempt();
}

function hideWidget(widget) {
  if (!widget) return;
  widget.hidden = true;
  widget.computeSize = () => [0, -4];
  widget.draw = () => {};
}

function setWidgetHeight(widget, height) {
  if (!widget || widget.height === height) return;
  try {
    widget.height = height;
  } catch {
    Object.defineProperty(widget, "height", {
      value: height,
      writable: true,
      configurable: true,
    });
  }
}

function createElement(tag, className, html = "") {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (html) element.innerHTML = html;
  return element;
}

function isEditableField(target) {
  return Boolean(target?.closest?.("input, textarea, select, button"));
}

function getComfySetting(name) {
  const setting = app.extensionManager?.setting?.get?.(name) ?? app.ui?.settings?.getSettingValue?.(name);
  if (typeof setting === "object" && setting !== null) return setting.value ?? setting.id ?? setting.name ?? setting.text;
  return setting;
}

function getRendererMode() {
  const renderer = String(getComfySetting("Comfy.Graph.Renderer") ?? "").toLowerCase();
  if (renderer) {
    if (renderer.includes("litegraph") || renderer.includes("canvas") || renderer.includes("classic") || renderer.includes("legacy")) return "legacy";
    if (renderer.includes("vue") || renderer.includes("dom") || renderer.includes("modern") || /nodes?\s*2|2\.0/.test(renderer)) return "vue";
  }

  const vueNodesEnabled = getComfySetting("Comfy.VueNodes.Enabled");
  const vueNodesValue = String(vueNodesEnabled ?? "").toLowerCase();
  if (vueNodesEnabled === true || vueNodesValue === "true" || vueNodesValue === "enabled") return "vue";
  if (vueNodesEnabled === false || vueNodesValue === "false" || vueNodesValue === "disabled") return "legacy";

  if (document.querySelector(".lg-node")) return "vue";
  return "legacy";
}

function injectStyles() {
  if (document.getElementById("spm-styles")) return;
  const style = document.createElement("style");
  style.id = "spm-styles";
  style.textContent = `
    /* ---- Helto Design System tokens (inlined :root, canonical values) ---- */
    :root{
      --helto-bg:#0d1320;--helto-surface:#151c2a;--helto-surface-2:#1b2333;--helto-surface-3:#232d3f;--helto-surface-hover:#2c3850;
      --helto-border:#2a3346;--helto-border-strong:#3a465c;--helto-border-hover:#4c5970;
      --helto-text:#e7ebf3;--helto-text-dim:#9aa6bd;--helto-text-faint:#6f7c95;
      --helto-accent:#f1c75c;--helto-accent-strong:#ffd873;--helto-accent-bg:rgba(241,199,92,.16);--helto-accent-border:rgba(241,199,92,.55);
      --helto-focus:#5e9bff;--helto-focus-ring:0 0 0 2px rgba(94,155,255,.5);
      --helto-danger:#ec5a6b;--helto-danger-bg:#3a1a22;--helto-danger-border:#8f3a44;
      --helto-warn:#ffe3a3;
      --helto-radius-sm:5px;--helto-radius:6px;--helto-radius-lg:10px;
      --helto-font-sans:system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
      --helto-font-mono:ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,"Roboto Mono",monospace;
      --helto-shadow:0 1px 2px rgba(0,0,0,.35);--helto-shadow-pop:0 14px 36px rgba(0,0,0,.55);--helto-shadow-glow:0 0 10px rgba(241,199,92,.35);
      --helto-transition:.12s ease;--helto-ease-spring:cubic-bezier(.34,1.56,.64,1);
    }

    /* ---- Root / layout ---- */
    .spm-widget-frame{box-sizing:border-box;margin:0;width:100%;height:100%;overflow:visible}
    .spm-root{font:12px/1.4 var(--helto-font-sans);color:var(--helto-text);background:var(--helto-surface);border:1px solid var(--helto-border);border-radius:var(--helto-radius);box-shadow:var(--helto-shadow);padding:9px;width:100%;height:100%;overflow:auto;box-sizing:border-box;overscroll-behavior:contain;-webkit-font-smoothing:antialiased}
    .spm-root *,.spm-root *::before,.spm-root *::after{box-sizing:border-box}
    .spm-row{display:flex;gap:6px;align-items:center;margin:6px 0}.spm-row-wrap{display:flex;gap:6px;align-items:center;flex-wrap:wrap;margin:6px 0}
    .spm-spacer{flex:1 1 auto}

    /* ---- Inputs ---- */
    .spm-root input,.spm-root textarea,.spm-root select{background:var(--helto-surface-2);color:var(--helto-text);border:1px solid var(--helto-border-strong);border-radius:var(--helto-radius-sm);padding:5px 8px;font:inherit;box-sizing:border-box;transition:border-color var(--helto-transition),box-shadow var(--helto-transition)}
    .spm-root textarea{width:100%;resize:vertical;min-height:54px;line-height:1.4}.spm-root input[type=text],.spm-root select{min-width:0}
    .spm-root select{cursor:pointer}
    .spm-root input::placeholder,.spm-root textarea::placeholder{color:var(--helto-text-faint)}
    .spm-root input:focus,.spm-root textarea:focus,.spm-root select:focus,.spm-modal input:focus,.spm-modal textarea:focus,.spm-modal select:focus,.spm-btn:focus-visible{outline:none;border-color:var(--helto-focus);box-shadow:var(--helto-focus-ring)}

    /* ---- Buttons (icon-only, raised gradient; gold=active/primary, red=danger) ---- */
    .spm-btn{background:linear-gradient(180deg,var(--helto-surface-3),var(--helto-surface-2));color:var(--helto-text);border:1px solid var(--helto-border-strong);border-radius:var(--helto-radius-sm);padding:0;cursor:pointer;font:inherit;white-space:nowrap;width:28px;height:28px;display:inline-flex;align-items:center;justify-content:center;flex:0 0 auto;transition:background var(--helto-transition),border-color var(--helto-transition),color var(--helto-transition),box-shadow var(--helto-transition),transform .03s ease}
    .spm-btn:hover{background:linear-gradient(180deg,var(--helto-surface-hover),var(--helto-surface-3));border-color:var(--helto-border-hover);color:#fff}
    .spm-btn:active{transform:translateY(1px)}.spm-btn:disabled{opacity:.4;cursor:not-allowed}
    .spm-btn-primary{border-color:var(--helto-accent-border);background:linear-gradient(180deg,#4f4322,#3c3318);color:var(--helto-accent-strong)}
    .spm-btn-primary:hover{background:linear-gradient(180deg,#5b4d27,#46391b);color:#fff3cf}
    .spm-btn-danger{border-color:var(--helto-danger-border);background:linear-gradient(180deg,#5a2330,#471b25);color:#ffd6dc}
    .spm-btn-danger:hover{border-color:#d0505f;background:linear-gradient(180deg,#6e2937,#57212c);color:#fff3f5}
    .spm-btn-quiet{background:linear-gradient(180deg,var(--helto-surface-2),var(--helto-surface));color:var(--helto-text-dim)}
    .spm-btn-quiet:hover{background:linear-gradient(180deg,var(--helto-surface-hover),var(--helto-surface-3));color:#fff}
    .spm-icon{width:16px;height:16px;fill:none;stroke:currentColor;stroke-width:1.8;stroke-linecap:round;stroke-linejoin:round;display:block}
    .spm-sr-only{position:absolute;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap;border:0}

    /* ---- Toolbar ---- */
    .spm-toolbar{min-height:34px;padding:5px;border-radius:var(--helto-radius);background:linear-gradient(180deg,var(--helto-surface-2),var(--helto-surface));box-shadow:inset 0 0 0 1px var(--helto-border)}

    /* ---- Toggle switch (privacy) ---- */
    .spm-privacy-toggle{display:inline-flex;align-items:center;gap:8px;margin:0 2px 0 auto;color:var(--helto-text-faint);font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.06em;line-height:1}
    .spm-switch{position:relative;display:inline-block;width:36px;height:20px;flex:0 0 auto}
    .spm-switch input{position:absolute;opacity:0;width:0;height:0;margin:0}
    .spm-switch-slider{position:absolute;inset:0;border-radius:20px;background:var(--helto-surface-2);border:1px solid var(--helto-border-strong);cursor:pointer;transition:.25s ease}
    .spm-switch-slider::before{content:"";position:absolute;left:3px;bottom:3px;width:12px;height:12px;border-radius:50%;background:var(--helto-text-dim);transition:.25s ease}
    .spm-switch input:checked+.spm-switch-slider{background:var(--helto-accent-bg);border-color:var(--helto-accent-border)}
    .spm-switch input:checked+.spm-switch-slider::before{transform:translateX(16px);background:var(--helto-accent)}
    .spm-switch input:focus-visible+.spm-switch-slider{box-shadow:var(--helto-focus-ring)}
    .spm-switch input:disabled+.spm-switch-slider{opacity:.5;cursor:not-allowed}

    /* ---- Sections ---- */
    .spm-section{border-top:1px solid var(--helto-border);margin-top:9px;padding-top:8px}
    .spm-section summary{cursor:pointer;font-size:12px;font-weight:600;letter-spacing:.02em;color:var(--helto-text);list-style:none;display:flex;align-items:center;gap:6px}
    .spm-section summary::-webkit-details-marker{display:none}
    .spm-section summary::before{content:"";width:0;height:0;border-left:5px solid var(--helto-text-faint);border-top:4px solid transparent;border-bottom:4px solid transparent;transition:transform var(--helto-transition)}
    .spm-section[open] summary::before{transform:rotate(90deg)}
    .spm-section summary:hover{color:var(--helto-accent-strong)}

    /* ---- Prompt list (inset well; selected=gold) ---- */
    .spm-prompt-list{max-height:96px;overflow:auto;border:1px solid var(--helto-border);border-radius:var(--helto-radius);background:var(--helto-bg);box-shadow:inset 0 1px 0 rgba(255,255,255,.02)}
    .spm-prompt-item{display:flex;align-items:center;gap:6px;padding:5px 8px;border-bottom:1px solid var(--helto-border);cursor:pointer;color:var(--helto-text);transition:background var(--helto-transition),color var(--helto-transition)}
    .spm-prompt-item:last-child{border-bottom:0}
    .spm-prompt-item:hover{background:var(--helto-surface-hover);color:#fff}
    .spm-prompt-item.is-selected{background:var(--helto-accent-bg);color:var(--helto-accent-strong);box-shadow:inset 2px 0 0 var(--helto-accent)}
    .spm-prompt-title{flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
    .spm-muted{color:var(--helto-text-dim)}.spm-mini{font-size:11px;color:var(--helto-text-faint)}

    /* ---- Preview wells ---- */
    .spm-preview{white-space:pre-wrap;line-height:1.45;font-family:var(--helto-font-mono);background:var(--helto-bg);border:1px solid var(--helto-border);border-radius:var(--helto-radius-sm);padding:7px 9px;min-height:28px;max-height:76px;overflow:auto;box-shadow:inset 0 1px 0 rgba(255,255,255,.02)}
    .spm-var{background:var(--helto-accent-bg);color:var(--helto-accent-strong);border:1px solid var(--helto-accent-border);border-radius:var(--helto-radius-sm);padding:0 3px}
    .spm-var-warn{background:var(--helto-danger-bg);color:#ffd6dc;border-color:var(--helto-danger-border)}

    /* ---- Grids / warnings ---- */
    .spm-grid{display:grid;grid-template-columns:1fr 76px 1.2fr 1fr 1fr 1.2fr 28px;gap:5px;align-items:start}.spm-grid-head{font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.06em;color:var(--helto-text-faint)}
    .spm-grid textarea{min-height:34px}
    .spm-warn{background:#332711;border:1px solid #7a5e28;color:var(--helto-warn);border-radius:var(--helto-radius);padding:7px 10px;margin-top:6px}

    /* ---- Autocomplete / tooltip (pop surfaces) ---- */
    .spm-autocomplete{position:absolute;z-index:10000;background:var(--helto-surface);border:1px solid var(--helto-border-strong);border-radius:var(--helto-radius);box-shadow:var(--helto-shadow-pop);max-height:150px;overflow:auto;min-width:210px;padding:5px;animation:spm-pop .15s var(--helto-ease-spring)}
    .spm-suggestion{display:flex;gap:8px;justify-content:space-between;align-items:center;padding:5px 8px;border-radius:var(--helto-radius-sm);cursor:pointer;color:var(--helto-text)}
    .spm-suggestion:hover{background:var(--helto-surface-hover);color:#fff}
    .spm-suggestion.is-active{background:var(--helto-surface-hover);color:#fff;box-shadow:inset 2px 0 0 var(--helto-accent)}
    .spm-suggestion-name{font-weight:600;color:inherit}
    .spm-copybox{width:100%;min-height:54px;font-family:var(--helto-font-mono)}
    .spm-tooltip{position:absolute;z-index:10001;max-width:320px;background:var(--helto-surface);border:1px solid var(--helto-border-strong);border-radius:var(--helto-radius);padding:8px 10px;color:var(--helto-text);box-shadow:var(--helto-shadow-pop);pointer-events:none;font:12px/1.4 var(--helto-font-sans)}
    @keyframes spm-pop{from{opacity:0;transform:translateY(-4px)}to{opacity:1;transform:translateY(0)}}
    @keyframes spm-fade{from{opacity:0}to{opacity:1}}
    @keyframes spm-rise{from{opacity:0;transform:translateY(16px)}to{opacity:1;transform:translateY(0)}}

    /* ---- Modal / overlay ---- */
    .spm-modal-backdrop{position:fixed;inset:0;z-index:9999;background:rgba(6,9,15,.72);backdrop-filter:blur(4px);display:flex;align-items:center;justify-content:center;padding:24px;box-sizing:border-box;animation:spm-fade .2s ease}
    .spm-modal{width:min(960px,calc(100vw - 48px));max-height:calc(100vh - 48px);overflow:auto;background:linear-gradient(135deg,rgba(27,35,51,.92),rgba(13,19,32,.96));color:var(--helto-text);border:1px solid var(--helto-border-strong);border-radius:var(--helto-radius-lg);box-shadow:var(--helto-shadow-pop);backdrop-filter:blur(15px);padding:14px;box-sizing:border-box;font:13px/1.4 var(--helto-font-sans);animation:spm-rise .2s var(--helto-ease-spring)}
    .spm-modal *,.spm-modal *::before,.spm-modal *::after{box-sizing:border-box}
    .spm-modal-header{display:flex;align-items:center;justify-content:space-between;gap:12px;border-bottom:1px solid var(--helto-border);padding-bottom:10px;margin-bottom:12px}.spm-modal-title{font-weight:700;font-size:14px;letter-spacing:.02em}
    .spm-modal input,.spm-modal textarea,.spm-modal select{background:var(--helto-surface-2);color:var(--helto-text);border:1px solid var(--helto-border-strong);border-radius:var(--helto-radius-sm);padding:6px 8px;font:inherit;box-sizing:border-box}
    .spm-modal select{cursor:pointer}.spm-modal input::placeholder,.spm-modal textarea::placeholder{color:var(--helto-text-faint)}
    .spm-modal textarea{width:100%;resize:vertical}.spm-dialog-editor{min-height:220px;font-family:var(--helto-font-mono)}.spm-dialog-description{min-height:70px}
    .spm-modal .spm-row,.spm-modal .spm-row-wrap{margin:8px 0}.spm-modal .spm-preview{max-height:170px}
    .spm-modal-field{display:flex;flex-direction:column;gap:5px;flex:1}.spm-modal-field label{font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.06em;color:var(--helto-text-faint)}
    .spm-modal-grid{display:grid;grid-template-columns:minmax(110px,1fr) 92px minmax(170px,1.4fr) minmax(110px,1fr) minmax(110px,1fr) minmax(150px,1.2fr) 34px;gap:6px;align-items:start}.spm-modal-grid textarea{min-height:54px}
    .spm-node-summary{background:var(--helto-bg);border:1px solid var(--helto-border);border-radius:var(--helto-radius-sm);padding:7px 9px;line-height:1.35;box-shadow:inset 0 1px 0 rgba(255,255,255,.02)}.spm-node-summary-title{font-weight:600;color:var(--helto-text);overflow-wrap:anywhere}

    /* ---- Thin scrollbars ---- */
    .spm-root,.spm-modal,.spm-prompt-list,.spm-preview,.spm-autocomplete{scrollbar-width:thin;scrollbar-color:var(--helto-border-strong) transparent}
    .spm-root::-webkit-scrollbar,.spm-modal::-webkit-scrollbar,.spm-prompt-list::-webkit-scrollbar,.spm-preview::-webkit-scrollbar,.spm-autocomplete::-webkit-scrollbar{width:6px;height:6px}
    .spm-root::-webkit-scrollbar-track,.spm-modal::-webkit-scrollbar-track,.spm-prompt-list::-webkit-scrollbar-track,.spm-preview::-webkit-scrollbar-track,.spm-autocomplete::-webkit-scrollbar-track{background:transparent}
    .spm-root::-webkit-scrollbar-thumb,.spm-modal::-webkit-scrollbar-thumb,.spm-prompt-list::-webkit-scrollbar-thumb,.spm-preview::-webkit-scrollbar-thumb,.spm-autocomplete::-webkit-scrollbar-thumb{background:var(--helto-border-strong);border-radius:3px}
    .spm-root::-webkit-scrollbar-thumb:hover,.spm-modal::-webkit-scrollbar-thumb:hover,.spm-prompt-list::-webkit-scrollbar-thumb:hover,.spm-preview::-webkit-scrollbar-thumb:hover,.spm-autocomplete::-webkit-scrollbar-thumb:hover{background:var(--helto-text-faint)}
  `;
  document.head.appendChild(style);
}

function enhanceNode(node) {
  injectStyles();
  const dataWidget = node.widgets?.find((widget) => widget.name === SPM_PRIVACY_FIELD);
  if (!dataWidget || node.__spmEnhanced) return;
  node.__spmEnhanced = true;
  hideWidget(dataWidget);

  const originalOnSerialize = node.onSerialize;
  const originalSerializeValue = dataWidget.serializeValue;
  const initialEncryptedValue = encryptedPrivacyEnvelopeString(dataWidget.value);
  let state = initialEncryptedValue ? defaultState() : parseState(dataWidget.value);
  let status = initialEncryptedValue ? "Decrypting private prompt library..." : "";
  let autocomplete = { open: false, items: [], active: 0, start: 0, end: 0, partial: "" };
  let tooltip = null;
  let lastThemeKey = "";
  let previewRevealActive = false;
  let privacyLocked = Boolean(initialEncryptedValue);
  let privacyBusy = false;
  let encryptSequence = 0;
  const widgetFrame = createElement("div", "spm-widget-frame");
  const root = createElement("div", "spm-root");
  widgetFrame.appendChild(root);
  let uiWidget = null;

  const seedWidget = node.widgets?.find((widget) => widget.name === "seed");
  const rerollWidget = node.widgets?.find((widget) => widget.name === "reroll");
  const getSeed = () => Number.parseInt(seedWidget?.value || 0, 10) || 0;
  const getReroll = () => Number.parseInt(rerollWidget?.value || 0, 10) || 0;

  function applyNodeTheme() {
    // The Helto design system uses a fixed dark-navy palette (see the inlined
    // :root tokens in injectStyles), so the node colour no longer drives the UI.
    // Kept as a no-op hook so theme-refresh callers stay valid.
  }

  function refreshNodeTheme(force = false) {
    const themeKey = `${node.color || ""}|${node.bgcolor || ""}`;
    if (!force && themeKey === lastThemeKey) return;
    lastThemeKey = themeKey;
    applyNodeTheme(root);
    document.querySelectorAll(".spm-modal-backdrop").forEach((element) => applyNodeTheme(element));
  }

  function panelWidth() {
    return Math.max(PANEL_MIN_WIDTH, Math.floor((node.size?.[0] || PANEL_DEFAULT_WIDTH + PANEL_HORIZONTAL_GUTTER * 2) - PANEL_HORIZONTAL_GUTTER * 2));
  }

  function panelHeight() {
    return Math.max(PANEL_MIN_HEIGHT, Math.floor((node.size?.[1] || PANEL_DEFAULT_HEIGHT + NODE_CHROME_HEIGHT) - NODE_CHROME_HEIGHT));
  }

  function shouldUseVueLayout() {
    return getRendererMode() === "vue" || Boolean(root.closest(".lg-node"));
  }

  function syncWidgetSizingCallbacks() {
    if (!uiWidget) return;
    if (shouldUseVueLayout()) {
      uiWidget.computeLayoutSize = undefined;
      uiWidget.computeSize = undefined;
      uiWidget.getMinHeight = () => panelHeight();
      uiWidget.getMaxHeight = () => panelHeight();
      uiWidget.getHeight = () => panelHeight();
      if (uiWidget.options) {
        uiWidget.options.getMinHeight = uiWidget.getMinHeight;
        uiWidget.options.getMaxHeight = uiWidget.getMaxHeight;
        uiWidget.options.getHeight = uiWidget.getHeight;
      }
      return;
    }

    delete uiWidget.computeLayoutSize;
    uiWidget.computeSize = () => [Math.max(PANEL_MIN_WIDTH + PANEL_HORIZONTAL_GUTTER * 2, node.size?.[0] || PANEL_DEFAULT_WIDTH + PANEL_HORIZONTAL_GUTTER * 2), panelHeight() + PANEL_BOTTOM_GUTTER];
  }

  function syncLegacyWidgetBounds() {
    if (!uiWidget || shouldUseVueLayout()) return;
    const widgetWidth = Math.max(PANEL_MIN_WIDTH + PANEL_HORIZONTAL_GUTTER * 2, node.size?.[0] || PANEL_DEFAULT_WIDTH + PANEL_HORIZONTAL_GUTTER * 2);
    const widgetHeight = panelHeight() + PANEL_BOTTOM_GUTTER;
    uiWidget.x = 0;
    uiWidget.width = widgetWidth;
    uiWidget.computedHeight = widgetHeight;
    setWidgetHeight(uiWidget, widgetHeight);
    widgetFrame.style.height = `${widgetHeight}px`;
    widgetFrame.style.minHeight = `${widgetHeight}px`;
    widgetFrame.style.maxHeight = `${widgetHeight}px`;
  }

  function syncPanelSize({ dirty = true } = {}) {
    refreshNodeTheme();
    syncWidgetSizingCallbacks();
    const legacyLayout = uiWidget && !shouldUseVueLayout();
    widgetFrame.style.boxSizing = "border-box";
    widgetFrame.style.margin = "0";
    widgetFrame.style.width = "100%";
    widgetFrame.style.height = `${panelHeight()}px`;
    widgetFrame.style.minHeight = `${panelHeight()}px`;
    widgetFrame.style.maxHeight = `${panelHeight()}px`;
    // Fill the widget area edge-to-edge and let the root's symmetric padding
    // form the gap to the node body, so left/right/bottom margins all match.
    // (Forcing a pixel width here left-aligned the panel and pushed the slack
    // onto the right side.)
    root.style.width = legacyLayout ? `calc(100% - ${PANEL_HORIZONTAL_GUTTER * 2}px)` : "100%";
    root.style.margin = legacyLayout ? `0 ${PANEL_HORIZONTAL_GUTTER}px` : "0";
    root.style.height = `${panelHeight()}px`;
    root.style.maxHeight = `${panelHeight()}px`;
    syncLegacyWidgetBounds();
    if (dirty) node.graph?.setDirtyCanvas(true, true);
  }

  function ensureMinimumNodeSize() {
    const minWidth = PANEL_MIN_WIDTH + 28;
    const minHeight = PANEL_MIN_HEIGHT + NODE_CHROME_HEIGHT;
    const currentWidth = node.size?.[0] || 0;
    const currentHeight = node.size?.[1] || 0;
    if (currentWidth < minWidth || currentHeight < minHeight) {
      node.setSize?.([Math.max(currentWidth, minWidth), Math.max(currentHeight, minHeight)]);
    }
  }

  function clearTooltip() {
    if (!tooltip) return;
    tooltip.remove();
    tooltip = null;
  }

  function setPreviewReveal(active, { render = true } = {}) {
    const next = Boolean(active);
    if (previewRevealActive === next) return;
    previewRevealActive = next;
    if (!previewRevealActive) clearTooltip();
    if (render && hasHiddenPreviews(state)) renderUi();
  }

  function resetPreviewReveal() {
    setPreviewReveal(false, { render: false });
  }

  async function privacyPost(endpoint, payload) {
    const response = await fetch(`/helto_spm/privacy/${endpoint}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const result = await response.json().catch(() => ({}));
    if (!response.ok || result.ok === false) throw new Error(result.error || `Privacy ${endpoint} failed.`);
    return result;
  }

  function cloneState(value) {
    return JSON.parse(JSON.stringify(value));
  }

  function normalizedSnapshot(value = state) {
    return cloneState(normalizeState(value));
  }

  function exposeExecutionState() {
    if (privacyLocked) return;
    node._spmExecutionState = normalizedSnapshot(state);
  }

  function trackPrivacySave(promise) {
    const tracked = Promise.resolve(promise).finally(() => {
      if (node._spmPendingPrivacySave === tracked) {
        node._spmPendingPrivacySave = null;
      }
    });
    node._spmPendingPrivacySave = tracked;
    return tracked;
  }

  async function encryptedSnapshotValue(snapshot) {
    const normalized = normalizedSnapshot(snapshot);
    return await encryptedOrReusePrivacyValue(node, SPM_PRIVACY_FIELD, normalized, async (plaintext) => {
      const result = await privacyPost("encrypt", { state: plaintext });
      return result.envelope;
    });
  }

  async function encryptAndSetWidget(snapshot, { allowClearOnFailure = false, renderAfter = false } = {}) {
    const sequence = ++encryptSequence;
    privacyBusy = true;
    try {
      const envelopeString = await encryptedSnapshotValue(snapshot);
      if (sequence !== encryptSequence) return envelopeString;
      setWidgetRawValue(node, dataWidget, envelopeString);
      status = "Privacy mode enabled.";
      return envelopeString;
    } catch (error) {
      if (sequence !== encryptSequence) return;
      if (allowClearOnFailure) {
        state.privacyMode = false;
        forgetPrivacyEnvelope(node, SPM_PRIVACY_FIELD);
        setWidgetValue(node, dataWidget, state);
      }
      status = `Privacy error: ${error.message}`;
      return encryptedPrivacyEnvelopeString(dataWidget.value) || dataWidget.value;
    } finally {
      if (sequence === encryptSequence) {
        privacyBusy = false;
        if (renderAfter) renderUi();
      }
    }
  }

  async function decryptInitialState() {
    privacyBusy = true;
    try {
      const result = await privacyPost("decrypt", { payload: parseJsonObject(initialEncryptedValue) });
      state = normalizeState(result.state);
      state.privacyMode = true;
      rememberPrivacyEnvelope(node, SPM_PRIVACY_FIELD, state, initialEncryptedValue);
      privacyLocked = false;
      status = result.warnings?.length ? `Privacy mode unlocked with ${result.warnings.length} warning(s).` : "Privacy mode unlocked.";
      saveWithoutRender();
    } catch (error) {
      privacyLocked = true;
      status = `Privacy error: ${error.message}`;
    } finally {
      privacyBusy = false;
      renderUi();
    }
  }

  async function setPrivacyMode(enabled) {
    if (privacyLocked || privacyBusy) return;
    if (enabled === Boolean(state.privacyMode)) return;
    if (enabled) {
      state.privacyMode = true;
      status = "Encrypting prompt library...";
      privacyBusy = true;
      renderUi();
      await trackPrivacySave(encryptAndSetWidget(cloneState(normalizeState(state)), { allowClearOnFailure: true, renderAfter: true }));
      return;
    }
    if (!confirm("Disable Privacy mode? This will save the prompt library in clear text inside the workflow.")) {
      renderUi();
      return;
    }
    encryptSequence += 1;
    privacyBusy = false;
    state.privacyMode = false;
    status = "Privacy mode disabled. Workflow data is clear text.";
    save();
  }

  function currentSerializedSpmData() {
    if (privacyLocked) {
      return encryptedPrivacyEnvelopeString(dataWidget.value) || dataWidget.value;
    }
    if (!state.privacyMode) {
      return dataWidget.value;
    }
    const snapshot = normalizedSnapshot(state);
    return rememberedPrivacyEnvelope(node, SPM_PRIVACY_FIELD, snapshot) || encryptedPrivacyEnvelopeString(dataWidget.value) || dataWidget.value;
  }

  function writeSerializedSpmData(info, value) {
    const index = serializedWidgetIndex(node, dataWidget);
    if (Array.isArray(info?.widgets_values) && index >= 0) {
      info.widgets_values[index] = value;
    }
  }

  function preparePrivacySerialization() {
    if (privacyLocked) {
      return Promise.resolve(encryptedPrivacyEnvelopeString(dataWidget.value) || dataWidget.value);
    }
    exposeExecutionState();
    if (!state.privacyMode) {
      return Promise.resolve(dataWidget.value);
    }
    return trackPrivacySave(encryptAndSetWidget(normalizedSnapshot(state), { renderAfter: false }));
  }

  node._spmPreparePrivacySerialization = preparePrivacySerialization;
  dataWidget.serializeValue = async function (...args) {
    if (privacyLocked || state.privacyMode) {
      return await preparePrivacySerialization();
    }
    if (typeof originalSerializeValue === "function") {
      return await originalSerializeValue.apply(this, args);
    }
    return dataWidget.value;
  };
  node.onSerialize = function (info) {
    const result = originalOnSerialize?.call(this, info);
    writeSerializedSpmData(info, currentSerializedSpmData());
    return result;
  };

  function save(render = true) {
    state = normalizeState(state);
    exposeExecutionState();
    if (state.privacyMode) {
      void trackPrivacySave(encryptAndSetWidget(normalizedSnapshot(state), { renderAfter: false }));
    } else {
      setWidgetValue(node, dataWidget, state);
    }
    if (render) renderUi();
  }

  function selectorForFocus(target) {
    if (target.dataset.promptField) return `[data-prompt-field="${target.dataset.promptField}"]`;
    if (target.dataset.field) return `[data-field="${target.dataset.field}"]`;
    if (target.dataset.varMode) return `[data-var-mode="${target.dataset.varMode}"]`;
    if (target.dataset.varValues) return `[data-var-values="${target.dataset.varValues}"]`;
    if (target.dataset.varFixed) return `[data-var-fixed="${target.dataset.varFixed}"]`;
    if (target.dataset.varFallback) return `[data-var-fallback="${target.dataset.varFallback}"]`;
    if (target.dataset.varDescription) return `[data-var-description="${target.dataset.varDescription}"]`;
    if (target.dataset.varName) return `[data-var-name="${target.value.trim() || target.dataset.varName}"]`;
    return "";
  }

  function savePreservingFocus(target) {
    const selector = selectorForFocus(target);
    const start = typeof target.selectionStart === "number" ? target.selectionStart : null;
    const end = typeof target.selectionEnd === "number" ? target.selectionEnd : null;
    save(true);
    if (!selector) return;
    const next = root.querySelector(selector);
    if (!next || next.disabled) return;
    next.focus();
    if (start !== null && typeof next.setSelectionRange === "function") {
      const max = String(next.value || "").length;
      next.setSelectionRange(Math.min(start, max), Math.min(end ?? start, max));
    }
  }

  function saveWithoutRender() {
    exposeExecutionState();
    if (state.privacyMode) {
      void trackPrivacySave(encryptAndSetWidget(normalizedSnapshot(state), { renderAfter: false }));
    } else {
      setWidgetValue(node, dataWidget, state);
    }
  }

  function stopComfyShortcuts(container) {
    for (const type of ["pointerdown", "pointerup", "wheel"]) {
      container.addEventListener(
        type,
        (event) => {
          event.stopPropagation();
        },
        true,
      );
    }
    for (const type of ["keydown", "keyup"]) {
      container.addEventListener(type, (event) => {
        if (isEditableField(event.target)) event.stopPropagation();
      });
    }
  }

  function currentResolution(prompt = selectedPrompt(state)) {
    return resolvePrompt(prompt?.text || "", state.variables, getSeed(), getReroll(), state.cycleState);
  }

  function visiblePrompts() {
    const query = state.search.trim().toLowerCase();
    return state.prompts.filter((prompt) => {
      const inFolder =
        state.selectedFolderId === "all" ||
        (state.selectedFolderId === "unsorted" && !prompt.folderId) ||
        (state.selectedFolderId === "favorites" && prompt.favorite) ||
        prompt.folderId === state.selectedFolderId;
      if (!inFolder) return false;
      if (!query) return true;
      const haystack = [
        prompt.title,
        prompt.text,
        prompt.description,
        Array.isArray(prompt.tags) ? prompt.tags.join(" ") : String(prompt.tags || ""),
        folderName(state, prompt.folderId),
      ]
        .join(" ")
        .toLowerCase();
      return haystack.includes(query);
    });
  }

  function renderPreview(text, resolution) {
    let index = 0;
    TOKEN_RE.lastIndex = 0;
    let html = "";
    let match;
    while ((match = TOKEN_RE.exec(String(text ?? "")))) {
      html += escapeHtml(String(text).slice(index, match.index));
      const name = match[1].trim();
      const defined = Boolean(state.variables[name]);
      const warning = !VALID_NAME_RE.test(name) || !defined;
      html += `<span class="spm-var ${warning ? "spm-var-warn" : ""}" data-var="${escapeHtml(name)}">${escapeHtml(match[0])}</span>`;
      index = match.index + match[0].length;
    }
    html += escapeHtml(String(text ?? "").slice(index));
    return html || '<span class="spm-muted">No prompt text.</span>';
  }

  function variableTooltip(name) {
    const definition = state.variables[name];
    if (!definition) return `<b>${escapeHtml(name)}</b><br><span class="spm-muted">Undefined variable.</span>`;
    const resolution = currentResolution();
    return `
      <b>{{${escapeHtml(name)}}}</b><br>
      mode: ${escapeHtml(definition.mode)}<br>
      values: ${escapeHtml(normalizeValues(definition.values).join(", ") || "none")}<br>
      selected: ${escapeHtml(resolution.selected_values[name] || "none")}<br>
      fallback: ${escapeHtml(definition.fallback || "none")}<br>
      ${definition.description ? `<span class="spm-muted">${escapeHtml(definition.description)}</span>` : ""}
    `;
  }

  function promptHoverPreview(prompt) {
    const resolution = currentResolution(prompt);
    const used = resolution.variables_used;
    const variableLines = used
      .map((name) => `${name}: ${normalizeValues(state.variables[name]?.values).join(", ") || "undefined"}`)
      .join("\n");
    return `${prompt.title || "Untitled prompt"}\n\n${prompt.text}\n\nVariables:\n${variableLines || "none"}\n\nResolved:\n${resolution.resolved_prompt}\n${resolution.warnings.length ? `\nWarnings:\n${resolution.warnings.join("\n")}` : ""}`;
  }

  async function copyText(text, fallbackSelector) {
    try {
      await navigator.clipboard.writeText(text);
      status = "Copied to clipboard.";
    } catch {
      const fallback = root.querySelector(fallbackSelector);
      if (fallback) fallback.value = text;
      status = "Clipboard unavailable. Use the fallback textbox.";
    }
    renderUi();
  }

  function promptJson(prompt) {
    if (!prompt) return "";
    const vars = {};
    for (const name of variablesUsed(prompt.text)) {
      if (state.variables[name]) vars[name] = state.variables[name];
    }
    return JSON.stringify(
      {
        version: 1,
        prompt: { ...prompt, folderName: folderName(state, prompt.folderId) },
        variablesUsed: variablesUsed(prompt.text),
        variables: vars,
      },
      null,
      2,
    );
  }

  function selectedPromptJson() {
    return promptJson(selectedPrompt(state));
  }

  function addPromptFromJson(raw) {
    const parsed = JSON.parse(raw);
    const incoming = parsed.prompt || parsed;
    if (!incoming || typeof incoming !== "object" || !incoming.text) throw new Error("Prompt JSON must contain a prompt with text.");
    const prompt = normalizeState({ prompts: [incoming], folders: [], variables: {} }).prompts[0];
    prompt.id = makeId("prompt");
    prompt.title = state.prompts.some((item) => item.title.toLowerCase() === prompt.title.toLowerCase())
      ? suffixName(prompt.title, state.prompts.map((item) => item.title))
      : prompt.title;
    prompt.folderId = "";
    prompt.createdAt = nowIso();
    prompt.updatedAt = prompt.createdAt;
    const variableRename = {};
    for (const [name, definition] of Object.entries(parsed.variables || {})) {
      if (!state.variables[name]) {
        state.variables[name] = normalizeState({ variables: { [name]: definition } }).variables[name];
      } else if (JSON.stringify(state.variables[name]) !== JSON.stringify(definition)) {
        let renamed = `${name}_copy`;
        let index = 2;
        while (state.variables[renamed]) {
          renamed = `${name}_copy${index}`;
          index += 1;
        }
        variableRename[name] = renamed;
        state.variables[renamed] = normalizeState({ variables: { [renamed]: definition } }).variables[renamed];
      }
    }
    for (const [oldName, newName] of Object.entries(variableRename)) {
      prompt.text = prompt.text.replace(new RegExp(`\\{\\{\\s*${oldName.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}\\s*\\}\\}`, "g"), `{{${newName}}}`);
    }
    state.prompts.push(prompt);
    state.selectedPromptId = prompt.id;
    status = "Pasted prompt JSON.";
    save();
  }

  function mergeLibrary(raw, replace) {
    const incoming = normalizeState(JSON.parse(raw));
    if (replace) {
      state = incoming;
      status = "Imported library.";
      save();
      return;
    }
    const folderMap = {};
    for (const folder of incoming.folders) {
      const copy = { ...folder };
      const existingNames = state.folders.map((item) => item.name);
      if (state.folders.some((item) => item.id === copy.id)) copy.id = makeId("folder");
      if (existingNames.some((name) => name.toLowerCase() === copy.name.toLowerCase())) copy.name = suffixName(copy.name, existingNames);
      folderMap[folder.id] = copy.id;
      state.folders.push(copy);
    }
    for (const prompt of incoming.prompts) {
      const copy = { ...prompt, id: makeId("prompt"), folderId: folderMap[prompt.folderId] || "" };
      if (state.prompts.some((item) => item.title.toLowerCase() === copy.title.toLowerCase())) {
        copy.title = suffixName(copy.title, state.prompts.map((item) => item.title));
      }
      state.prompts.push(copy);
    }
    for (const [name, definition] of Object.entries(incoming.variables)) {
      if (!state.variables[name]) state.variables[name] = definition;
    }
    status = "Merged library JSON.";
    save();
  }

  function updateAutocomplete(textarea) {
    const cursor = textarea.selectionStart;
    const before = textarea.value.slice(0, cursor);
    const start = before.lastIndexOf("{{");
    const close = before.lastIndexOf("}}");
    if (start < 0 || close > start) {
      autocomplete.open = false;
      return;
    }
    const partial = before.slice(start + 2);
    if (/\s|[^A-Za-z0-9_-]/.test(partial)) {
      autocomplete.open = false;
      return;
    }
    const lower = partial.toLowerCase();
    const names = Object.keys(state.variables).sort((a, b) => a.localeCompare(b));
    const prefix = names.filter((name) => name.toLowerCase().startsWith(lower));
    const contains = names.filter((name) => !prefix.includes(name) && name.toLowerCase().includes(lower));
    autocomplete = { open: prefix.length + contains.length > 0, items: [...prefix, ...contains], active: 0, start, end: cursor, partial };
  }

  function acceptAutocomplete(textarea) {
    if (!autocomplete.open || !autocomplete.items.length) return;
    const name = autocomplete.items[autocomplete.active];
    textarea.value = `${textarea.value.slice(0, autocomplete.start)}{{${name}}}${textarea.value.slice(autocomplete.end)}`;
    textarea.selectionStart = textarea.selectionEnd = autocomplete.start + name.length + 4;
    const prompt = selectedPrompt(state);
    if (prompt && !prompt.locked) {
      prompt.text = textarea.value;
      prompt.updatedAt = nowIso();
    }
    autocomplete.open = false;
    save();
  }

  function renderAutocomplete() {
    if (!autocomplete.open) return "";
    return `<div class="spm-autocomplete" style="left:10px;top:258px">
      ${autocomplete.items
        .map((name, index) => {
          const definition = state.variables[name];
          const extra = `${definition.mode} · ${normalizeValues(definition.values).length} values${definition.fixedValue ? ` · ${definition.fixedValue}` : ""}`;
          return `<div class="spm-suggestion ${index === autocomplete.active ? "is-active" : ""}" data-suggest="${escapeHtml(name)}"><span class="spm-suggestion-name">${escapeHtml(name)}</span><span class="spm-mini">${escapeHtml(extra)}</span></div>`;
        })
        .join("")}
    </div>`;
  }

  function renderAutocompleteInto(popup) {
    if (!autocomplete.open || !autocomplete.items.length) {
      popup.innerHTML = "";
      popup.style.display = "none";
      return;
    }
    popup.style.display = "block";
    popup.innerHTML = autocomplete.items
      .map((name, index) => {
        const definition = state.variables[name];
        const extra = `${definition.mode} · ${normalizeValues(definition.values).length} values${definition.fixedValue ? ` · ${definition.fixedValue}` : ""}`;
        return `<div class="spm-suggestion ${index === autocomplete.active ? "is-active" : ""}" data-suggest="${escapeHtml(name)}"><span class="spm-suggestion-name">${escapeHtml(name)}</span><span class="spm-mini">${escapeHtml(extra)}</span></div>`;
      })
      .join("");
  }

  function acceptAutocompleteInPromptDialog(textarea, popup, updatePreview, prompt, persistImmediately) {
    if (!autocomplete.open || !autocomplete.items.length) return;
    const name = autocomplete.items[autocomplete.active];
    textarea.value = `${textarea.value.slice(0, autocomplete.start)}{{${name}}}${textarea.value.slice(autocomplete.end)}`;
    textarea.selectionStart = textarea.selectionEnd = autocomplete.start + name.length + 4;
    if (prompt && !prompt.locked) {
      prompt.text = textarea.value;
      prompt.updatedAt = nowIso();
    }
    autocomplete.open = false;
    if (persistImmediately) saveWithoutRender();
    updatePreview();
    renderAutocompleteInto(popup);
  }

  function openPromptDialog() {
    let prompt = selectedPrompt(state);
    if (!prompt && state.prompts.length) prompt = state.prompts[0];
    if (!prompt) {
      const created = nowIso();
      prompt = {
        id: makeId("prompt"),
        title: "Untitled prompt",
        text: "",
        description: "",
        folderId: "",
        tags: [],
        favorite: false,
        locked: false,
        hidden: false,
        createdAt: created,
        updatedAt: created,
      };
    }
    let isDraft = !state.prompts.some((item) => item.id === prompt.id);
    const backdrop = createElement("div", "spm-modal-backdrop");
    const modal = createElement("div", "spm-modal");
    applyNodeTheme(backdrop);
    backdrop.appendChild(modal);
    document.body.appendChild(backdrop);
    stopComfyShortcuts(backdrop);
    let dialogSearch = "";
    let dialogFolderFilter = state.selectedFolderId || "all";

    const activePrompt = () => {
      if (isDraft) return prompt;
      return state.prompts.find((item) => item.id === prompt.id) || prompt;
    };

    const commitDraft = () => {
      if (!isDraft) return;
      if (!String(prompt.title || "").trim()) prompt.title = "Untitled prompt";
      const existingNames = state.prompts.map((item) => item.title);
      if (state.prompts.some((item) => item.title.toLowerCase() === prompt.title.toLowerCase())) {
        prompt.title = suffixName(prompt.title, existingNames);
      }
      state.prompts.push(prompt);
      state.selectedPromptId = prompt.id;
      isDraft = false;
    };

    const updatePreview = () => {
      const nextResolution = currentResolution(prompt);
      modal.querySelector("[data-dialog-highlight]").innerHTML = renderPreview(prompt.text || "", nextResolution);
      modal.querySelector("[data-dialog-resolved]").textContent = nextResolution.resolved_prompt;
    };

    const renderPromptDialog = (focus = {}) => {
      const resolution = currentResolution(prompt);
      const query = dialogSearch.trim().toLowerCase();
      const filterOptions = [...VIRTUAL_FOLDERS, ...state.folders]
        .map((folder) => `<option value="${escapeHtml(folder.id)}" ${folder.id === dialogFolderFilter ? "selected" : ""}>${escapeHtml(folder.name)}</option>`)
        .join("");
      const folderOptions = [`<option value="">Unsorted</option>`]
        .concat(state.folders.map((folder) => `<option value="${escapeHtml(folder.id)}" ${folder.id === prompt.folderId ? "selected" : ""}>${escapeHtml(folder.name)}</option>`))
        .join("");
      const promptList = state.prompts
        .filter((item) => {
          const inFolder =
            dialogFolderFilter === "all" ||
            (dialogFolderFilter === "unsorted" && !item.folderId) ||
            (dialogFolderFilter === "favorites" && item.favorite) ||
            item.folderId === dialogFolderFilter;
          if (!inFolder) return false;
          if (!query) return true;
          const haystack = [
            item.title,
            item.text,
            item.description,
            Array.isArray(item.tags) ? item.tags.join(" ") : String(item.tags || ""),
            folderName(state, item.folderId),
          ]
            .join(" ")
            .toLowerCase();
          return haystack.includes(query);
        })
        .map((item) => `<div class="spm-prompt-item ${item.id === prompt.id && !isDraft ? "is-selected" : ""}" data-dialog-prompt-id="${escapeHtml(item.id)}" title="${escapeHtml(promptHoverPreview(item))}"><span>${item.favorite ? "★" : "☆"}</span><span class="spm-prompt-title">${escapeHtml(item.title)}</span><span class="spm-mini">${escapeHtml(folderName(state, item.folderId))}</span></div>`)
        .join("");
      modal.innerHTML = `
        <div class="spm-modal-header">
          <div class="spm-modal-title">Edit Prompts${isDraft ? " · new draft" : ""}</div>
          <div class="spm-row-wrap">
            ${iconButton("check", "Done", 'data-dialog-action="save-close"', "spm-btn-primary")}
            ${iconButton("close", "Close", 'data-dialog-action="close"', "spm-btn-quiet")}
          </div>
        </div>
        <div class="spm-row" style="align-items:stretch">
          <div style="width:260px;min-width:220px">
            <div class="spm-row-wrap">
              ${iconButton("add", "Add prompt", 'data-dialog-action="add-prompt"', "spm-btn-primary")}
              ${iconButton("duplicate", "Duplicate prompt", 'data-dialog-action="duplicate-prompt"')}
              ${iconButton("delete", "Delete prompt", `data-dialog-action="delete-prompt" ${isDraft ? "disabled" : ""}`, "spm-btn-danger")}
            </div>
            <select data-dialog-folder-filter style="width:100%;margin:4px 0 6px">${filterOptions}</select>
            <input type="text" data-dialog-search value="${escapeHtml(dialogSearch)}" placeholder="Search prompts" style="width:100%;margin:4px 0 6px">
            <div class="spm-prompt-list" style="max-height:446px">${isDraft ? `<div class="spm-prompt-item is-selected" title="${escapeHtml(promptHoverPreview(prompt))}"><span>☆</span><span class="spm-prompt-title">${escapeHtml(prompt.title || "Untitled prompt")}</span><span class="spm-mini">draft</span></div>` : ""}${promptList || '<div class="spm-muted" style="padding:6px">No matching prompts.</div>'}</div>
          </div>
          <div style="flex:1;min-width:0">
            <div class="spm-row">
              <div class="spm-modal-field"><label>Title</label><input type="text" data-dialog-prompt-field="title" value="${escapeHtml(prompt.title || "")}" ${prompt.locked ? "disabled" : ""}></div>
            </div>
            <div class="spm-row">
              <div class="spm-modal-field"><label>Folder</label><select data-dialog-prompt-field="folderId" ${prompt.locked ? "disabled" : ""}>${folderOptions}</select></div>
              <div class="spm-modal-field"><label>Tags</label><input type="text" data-dialog-prompt-field="tags" value="${escapeHtml(tagsForInput(prompt.tags))}" placeholder="portrait, cinematic" ${prompt.locked ? "disabled" : ""}></div>
            </div>
            <div class="spm-row-wrap">
              <label title="Mark this prompt as a favorite"><input type="checkbox" title="Mark this prompt as a favorite" data-dialog-prompt-bool="favorite" ${prompt.favorite ? "checked" : ""}> Favorite</label>
              <label title="Lock this prompt to prevent accidental edits"><input type="checkbox" title="Lock this prompt to prevent accidental edits" data-dialog-prompt-bool="locked" ${prompt.locked ? "checked" : ""}> Locked</label>
              <label title="Hide this prompt preview until the node is hovered"><input type="checkbox" title="Hide this prompt preview until the node is hovered" data-dialog-prompt-bool="hidden" ${prompt.hidden ? "checked" : ""}> Hidden preview</label>
            </div>
            <div class="spm-modal-field"><label>Description</label><textarea class="spm-dialog-description" data-dialog-prompt-field="description" ${prompt.locked ? "disabled" : ""}>${escapeHtml(prompt.description || "")}</textarea></div>
            <div class="spm-modal-field" style="position:relative"><label>Prompt text</label><textarea class="spm-dialog-editor" data-dialog-prompt-field="text" ${prompt.locked ? "disabled" : ""}>${escapeHtml(prompt.text || "")}</textarea><div class="spm-autocomplete" data-dialog-autocomplete style="display:none;left:8px;top:250px"></div></div>
            <div class="spm-row-wrap">
              ${iconButton("copy", "Copy resolved prompt", 'data-dialog-action="copy-resolved"')}
              ${iconButton("json", "Copy prompt JSON", 'data-dialog-action="copy-prompt-json"')}
            </div>
            <div class="spm-mini">Highlighted preview</div>
            <div class="spm-preview" data-dialog-highlight>${renderPreview(prompt.text || "", resolution)}</div>
            <div class="spm-mini">Resolved preview</div>
            <div class="spm-preview" data-dialog-resolved>${escapeHtml(resolution.resolved_prompt)}</div>
          </div>
        </div>
      `;
      const target = focus.selector ? modal.querySelector(focus.selector) : modal.querySelector("[data-dialog-prompt-field='title']");
      target?.focus();
      if (focus.cursor !== undefined && typeof target?.setSelectionRange === "function") {
        const cursor = Math.min(focus.cursor, String(target.value || "").length);
        target.setSelectionRange(cursor, cursor);
      } else if (focus.select && typeof target?.select === "function") {
        target.select();
      }
    };

    const close = (commit = false) => {
      autocomplete.open = false;
      const targetPrompt = activePrompt();
      if (!targetPrompt.locked) {
        modal.querySelectorAll("[data-dialog-prompt-field]").forEach((fieldElement) => {
          const field = fieldElement.dataset.dialogPromptField;
          targetPrompt[field] = field === "tags" ? normalizeTags(fieldElement.value) : fieldElement.value;
        });
        modal.querySelectorAll("[data-dialog-prompt-bool]").forEach((boolElement) => {
          const field = boolElement.dataset.dialogPromptBool;
          targetPrompt[field] = boolElement.checked;
          if (field === "hidden" && boolElement.checked) resetPreviewReveal();
        });
        targetPrompt.updatedAt = nowIso();
        prompt = targetPrompt;
      }
      backdrop.remove();
      if (commit) commitDraft();
      save();
    };

    modal.addEventListener("input", (event) => {
      if (event.target.matches("[data-dialog-search]")) {
        const cursor = event.target.selectionStart;
        dialogSearch = event.target.value;
        renderPromptDialog({ selector: "[data-dialog-search]", cursor });
        return;
      }
      if (event.target.dataset.dialogPromptBool) {
        const field = event.target.dataset.dialogPromptBool;
        prompt[field] = event.target.checked;
        if (field === "hidden" && event.target.checked) resetPreviewReveal();
        prompt.updatedAt = nowIso();
        if (!isDraft) saveWithoutRender();
        return;
      }
      if (!event.target.dataset.dialogPromptField || prompt.locked) return;
      const field = event.target.dataset.dialogPromptField;
      prompt[field] = field === "tags" ? tagsFromDraft(event.target.value) : event.target.value;
      prompt.updatedAt = nowIso();
      if (field === "text") {
        updateAutocomplete(event.target);
        renderAutocompleteInto(modal.querySelector("[data-dialog-autocomplete]"));
        updatePreview();
      }
      if (!isDraft) saveWithoutRender();
    });
    modal.addEventListener("change", (event) => {
      if (event.target.matches("[data-dialog-folder-filter]")) {
        dialogFolderFilter = event.target.value;
        renderPromptDialog({ selector: "[data-dialog-folder-filter]" });
        return;
      }
      if (event.target.dataset.dialogPromptField && !prompt.locked) {
        const field = event.target.dataset.dialogPromptField;
        prompt[field] = field === "tags" ? normalizeTags(event.target.value) : event.target.value;
        if (field === "tags") event.target.value = tagsForInput(prompt.tags);
        prompt.updatedAt = nowIso();
        updatePreview();
        if (!isDraft) saveWithoutRender();
      }
      if (event.target.dataset.dialogPromptBool) {
        const field = event.target.dataset.dialogPromptBool;
        prompt[field] = event.target.checked;
        if (field === "hidden" && event.target.checked) resetPreviewReveal();
        prompt.updatedAt = nowIso();
        if (!isDraft) saveWithoutRender();
      }
    });
    modal.addEventListener("click", async (event) => {
      const suggestion = event.target.closest?.("[data-suggest]");
      if (suggestion) {
        autocomplete.active = autocomplete.items.indexOf(suggestion.dataset.suggest);
        acceptAutocompleteInPromptDialog(modal.querySelector(".spm-dialog-editor"), modal.querySelector("[data-dialog-autocomplete]"), updatePreview, prompt, !isDraft);
        return;
      }
      const promptItem = event.target.closest?.("[data-dialog-prompt-id]");
      if (promptItem) {
        if (isDraft && !confirm("Discard the unsaved draft prompt?")) return;
        prompt = state.prompts.find((item) => item.id === promptItem.dataset.dialogPromptId) || prompt;
        state.selectedPromptId = prompt.id;
        isDraft = false;
        saveWithoutRender();
        renderPromptDialog();
        return;
      }
      const action = event.target.closest?.("[data-dialog-action]")?.dataset.dialogAction;
      if (action === "close") close(false);
      if (action === "save-close") close(true);
      if (action === "add-prompt") {
        const created = nowIso();
        const folderId = state.folders.some((folder) => folder.id === dialogFolderFilter)
          ? dialogFolderFilter
          : dialogFolderFilter === "unsorted"
            ? ""
            : "";
        prompt = { id: makeId("prompt"), title: "", text: "", description: "", folderId, tags: [], favorite: false, locked: false, hidden: false, createdAt: created, updatedAt: created };
        isDraft = true;
        autocomplete.open = false;
        renderPromptDialog({ selector: "[data-dialog-prompt-field='title']", select: true });
      }
      if (action === "duplicate-prompt") {
        const created = nowIso();
        prompt = { ...prompt, id: makeId("prompt"), title: suffixName(prompt.title, state.prompts.map((item) => item.title)), locked: false, createdAt: created, updatedAt: created };
        isDraft = true;
        autocomplete.open = false;
        renderPromptDialog();
      }
      if (action === "delete-prompt" && !isDraft && confirm(`Delete prompt "${prompt.title}"?`)) {
        state.prompts = state.prompts.filter((item) => item.id !== prompt.id);
        prompt = state.prompts[0] || { id: makeId("prompt"), title: "Untitled prompt", text: "", description: "", folderId: "", tags: [], favorite: false, locked: false, hidden: false, createdAt: nowIso(), updatedAt: nowIso() };
        isDraft = !state.prompts.length;
        state.selectedPromptId = isDraft ? "" : prompt.id;
        saveWithoutRender();
        renderPromptDialog();
      }
      if (action === "copy-resolved") await copyText(currentResolution(prompt).resolved_prompt, "[data-role='json-box']");
      if (action === "copy-prompt-json") await copyText(promptJson(prompt), "[data-role='json-box']");
    });
    modal.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && !autocomplete.open) {
        event.preventDefault();
        close(false);
        return;
      }
      if (event.target !== editor) return;
      if (event.key === KEYS.close && autocomplete.open) {
        autocomplete.open = false;
        event.preventDefault();
        renderAutocompleteInto(popup);
        return;
      }
      if (event.ctrlKey && autocomplete.open && event.key.toLowerCase() === KEYS.next) {
        autocomplete.active = (autocomplete.active + 1) % autocomplete.items.length;
        event.preventDefault();
        renderAutocompleteInto(popup);
        return;
      }
      if (event.ctrlKey && autocomplete.open && event.key.toLowerCase() === KEYS.previous) {
        autocomplete.active = (autocomplete.active + autocomplete.items.length - 1) % autocomplete.items.length;
        event.preventDefault();
        renderAutocompleteInto(popup);
        return;
      }
      if (event.ctrlKey && autocomplete.open && event.key.toLowerCase() === KEYS.accept) {
        event.preventDefault();
        acceptAutocompleteInPromptDialog(modal.querySelector(".spm-dialog-editor"), modal.querySelector("[data-dialog-autocomplete]"), updatePreview, prompt, !isDraft);
      }
    });
    renderPromptDialog();
  }

  function openVariablesDialog() {
    const backdrop = createElement("div", "spm-modal-backdrop");
    const modal = createElement("div", "spm-modal");
    applyNodeTheme(backdrop);
    backdrop.appendChild(modal);
    document.body.appendChild(backdrop);
    stopComfyShortcuts(backdrop);

    const renderVariables = () => {
      const variableRows = Object.entries(state.variables)
        .sort(([a], [b]) => a.localeCompare(b))
        .map(
          ([name, definition]) => `<div class="spm-modal-grid" data-var-row="${escapeHtml(name)}">
            <input data-var-name="${escapeHtml(name)}" value="${escapeHtml(name)}">
            <select data-var-mode="${escapeHtml(name)}">${MODES.map((mode) => `<option value="${mode}" ${mode === definition.mode ? "selected" : ""}>${mode}</option>`).join("")}</select>
            <textarea data-var-values="${escapeHtml(name)}">${escapeHtml(normalizeValues(definition.values).join("\n"))}</textarea>
            <input data-var-fixed="${escapeHtml(name)}" value="${escapeHtml(definition.fixedValue || "")}">
            <input data-var-fallback="${escapeHtml(name)}" value="${escapeHtml(definition.fallback || "")}">
            <input data-var-description="${escapeHtml(name)}" value="${escapeHtml(definition.description || "")}">
            ${iconButton("delete", "Remove variable", `data-dialog-action="remove-variable" data-var="${escapeHtml(name)}"`, "spm-btn-danger")}
          </div>`,
        )
        .join("");
      modal.innerHTML = `
        <div class="spm-modal-header">
          <div class="spm-modal-title">Edit Variables</div>
          <div class="spm-row-wrap">
            ${iconButton("add", "Add variable", 'data-dialog-action="add-variable"', "spm-btn-primary")}
            ${iconButton("check", "Done", 'data-dialog-action="save-close"', "spm-btn-primary")}
          </div>
        </div>
        <div class="spm-modal-grid spm-grid-head"><span>Name</span><span>Mode</span><span>Values</span><span>Fixed</span><span>Fallback</span><span>Description</span><span></span></div>
        ${variableRows || '<div class="spm-muted">No variables yet.</div>'}
      `;
    };
    renderVariables();

    function replaceVariableTokens(oldName, newName) {
      if (oldName === newName) return;
      const tokenPattern = new RegExp(`\\{\\{\\s*${oldName.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}\\s*\\}\\}`, "g");
      state.prompts.forEach((item) => {
        item.text = item.text.replace(tokenPattern, `{{${newName}}}`);
      });
    }

    function syncVariableRowBindings(row, name) {
      if (!row || !name) return;
      row.dataset.varRow = name;
      const bindings = [
        ["[data-var-name]", "varName"],
        ["[data-var-mode]", "varMode"],
        ["[data-var-values]", "varValues"],
        ["[data-var-fixed]", "varFixed"],
        ["[data-var-fallback]", "varFallback"],
        ["[data-var-description]", "varDescription"],
      ];
      for (const [selector, key] of bindings) {
        const element = row.querySelector(selector);
        if (element) element.dataset[key] = name;
      }
      const removeButton = row.querySelector("[data-dialog-action='remove-variable']");
      if (removeButton) removeButton.dataset.var = name;
    }

    function readVariableRow(row) {
      const currentName = row?.dataset.varRow || row?.querySelector("[data-var-name]")?.dataset.varName || "";
      const nameElement = row?.querySelector("[data-var-name]");
      const modeElement = row?.querySelector("[data-var-mode]");
      const valuesElement = row?.querySelector("[data-var-values]");
      const fixedElement = row?.querySelector("[data-var-fixed]");
      const fallbackElement = row?.querySelector("[data-var-fallback]");
      const descriptionElement = row?.querySelector("[data-var-description]");
      return {
        currentName,
        requestedName: String(nameElement?.value || "").trim(),
        mode: MODES.includes(modeElement?.value) ? modeElement.value : "random",
        values: normalizeValues(valuesElement?.value || ""),
        fixedValue: fixedElement?.value || null,
        fallback: fallbackElement?.value || "",
        description: descriptionElement?.value || "",
      };
    }

    function commitVariableRow(row) {
      const draft = readVariableRow(row);
      if (!draft.currentName || !state.variables[draft.currentName]) return "";
      const requestedNameIsAvailable = draft.requestedName === draft.currentName || !state.variables[draft.requestedName];
      const nextName = VALID_NAME_RE.test(draft.requestedName) && requestedNameIsAvailable ? draft.requestedName : draft.currentName;
      if (nextName !== draft.currentName) {
        state.variables[nextName] = state.variables[draft.currentName];
        delete state.variables[draft.currentName];
        replaceVariableTokens(draft.currentName, nextName);
      }
      state.variables[nextName] = {
        mode: draft.mode,
        values: draft.values,
        fixedValue: draft.fixedValue,
        fallback: draft.fallback,
        description: draft.description,
      };
      syncVariableRowBindings(row, nextName);
      return nextName;
    }

    function commitVariableRows() {
      for (const row of modal.querySelectorAll("[data-var-row]")) {
        commitVariableRow(row);
      }
    }

    const close = () => {
      commitVariableRows();
      state.folders.forEach((folder) => {
        if (!String(folder.name || "").trim()) folder.name = "Folder";
      });
      backdrop.remove();
      save();
    };
    modal.addEventListener("input", (event) => {
      const row = event.target.closest?.("[data-var-row]");
      if (!row) return;
      commitVariableRow(row);
      saveWithoutRender();
    });
    modal.addEventListener("change", (event) => {
      const row = event.target.closest?.("[data-var-row]");
      if (!row) return;
      commitVariableRow(row);
      saveWithoutRender();
    });
    modal.addEventListener("click", (event) => {
      const actionButton = event.target.closest?.("[data-dialog-action]");
      const action = actionButton?.dataset.dialogAction;
      if (action === "save-close") close();
      if (action === "add-variable") {
        commitVariableRows();
        let name = "variable";
        let index = 2;
        while (state.variables[name]) {
          name = `variable${index}`;
          index += 1;
        }
        state.variables[name] = { mode: "random", values: ["value"], fixedValue: null, fallback: "", description: "" };
        saveWithoutRender();
        renderVariables();
      }
      if (action === "remove-variable") {
        const removeRow = actionButton.closest?.("[data-var-row]");
        commitVariableRows();
        const removeName = removeRow?.dataset.varRow || actionButton.dataset.var;
        delete state.variables[removeName];
        saveWithoutRender();
        renderVariables();
      }
    });
    modal.addEventListener("keydown", (event) => {
      if (event.key === "Escape") {
        event.preventDefault();
        close();
      }
    });
  }

  function openFoldersDialog() {
    const backdrop = createElement("div", "spm-modal-backdrop");
    const modal = createElement("div", "spm-modal");
    applyNodeTheme(backdrop);
    backdrop.appendChild(modal);
    document.body.appendChild(backdrop);
    stopComfyShortcuts(backdrop);

    const renderFolders = (focusFolderId = "") => {
      const virtualRows = VIRTUAL_FOLDERS.map(
        (folder) => `<div class="spm-prompt-item ${state.selectedFolderId === folder.id ? "is-selected" : ""}" data-dialog-folder-select="${escapeHtml(folder.id)}">
          <span class="spm-prompt-title">${escapeHtml(folder.name)}</span><span class="spm-mini">virtual</span>
        </div>`,
      ).join("");
      const folderRows = state.folders
        .map((folder) => {
          const count = state.prompts.filter((prompt) => prompt.folderId === folder.id).length;
          return `<div class="spm-row" data-folder-row="${escapeHtml(folder.id)}">
            ${iconButton(state.selectedFolderId === folder.id ? "selected" : "select", state.selectedFolderId === folder.id ? "Selected folder" : "Select folder", `data-dialog-folder-select="${escapeHtml(folder.id)}"`, "spm-btn-quiet")}
            <input type="text" data-dialog-folder-name="${escapeHtml(folder.id)}" value="${escapeHtml(folder.name)}" style="flex:1">
            <label class="spm-mini" title="Hide previews for prompts in this folder until the node is hovered"><input type="checkbox" title="Hide previews for prompts in this folder until the node is hovered" data-dialog-folder-hidden="${escapeHtml(folder.id)}" ${folder.hidden ? "checked" : ""}> Hidden</label>
            <span class="spm-mini">${count} prompts</span>
            ${iconButton("delete", "Delete folder", `data-dialog-action="delete-folder" data-folder="${escapeHtml(folder.id)}"`, "spm-btn-danger")}
          </div>`;
        })
        .join("");
      modal.innerHTML = `
        <div class="spm-modal-header">
          <div class="spm-modal-title">Edit Folders</div>
          <div class="spm-row-wrap">
            ${iconButton("add", "Add folder", 'data-dialog-action="add-folder"', "spm-btn-primary")}
            ${iconButton("check", "Done", 'data-dialog-action="save-close"', "spm-btn-primary")}
          </div>
        </div>
        <div class="spm-mini">Filter folders</div>
        <div class="spm-prompt-list" style="max-height:128px;margin-bottom:10px">${virtualRows}</div>
        <div class="spm-mini">Editable folders</div>
        ${folderRows || '<div class="spm-muted">No custom folders yet.</div>'}
      `;
      if (focusFolderId) {
        const input = modal.querySelector(`[data-dialog-folder-name="${CSS.escape(focusFolderId)}"]`);
        input?.focus();
        input?.select?.();
      }
    };

    const close = () => {
      backdrop.remove();
      save();
    };

    renderFolders();
    modal.addEventListener("input", (event) => {
      const hiddenFolderId = event.target.dataset.dialogFolderHidden;
      if (hiddenFolderId) {
        const folder = state.folders.find((item) => item.id === hiddenFolderId);
        if (!folder) return;
        folder.hidden = event.target.checked;
        if (event.target.checked) resetPreviewReveal();
        saveWithoutRender();
        return;
      }
      const folderId = event.target.dataset.dialogFolderName;
      if (!folderId) return;
      const folder = state.folders.find((item) => item.id === folderId);
      if (!folder) return;
      folder.name = event.target.value;
      saveWithoutRender();
    });
    modal.addEventListener("click", (event) => {
      const folderSelect = event.target.closest?.("[data-dialog-folder-select]");
      if (folderSelect) {
        state.selectedFolderId = folderSelect.dataset.dialogFolderSelect;
        saveWithoutRender();
        renderFolders();
        return;
      }
      const action = event.target.closest?.("[data-dialog-action]")?.dataset.dialogAction;
      if (action === "save-close") close();
      if (action === "add-folder") {
        const folder = { id: makeId("folder"), name: "", hidden: false };
        state.folders.push(folder);
        state.selectedFolderId = folder.id;
        saveWithoutRender();
        renderFolders(folder.id);
      }
      if (action === "delete-folder") {
        const folderId = event.target.dataset.folder;
        const folder = state.folders.find((item) => item.id === folderId);
        if (!folder || !confirm(`Delete folder "${folder.name}"? Prompts will move to Unsorted.`)) return;
        state.prompts.forEach((prompt) => {
          if (prompt.folderId === folder.id) prompt.folderId = "";
        });
        state.folders = state.folders.filter((item) => item.id !== folder.id);
        if (state.selectedFolderId === folder.id) state.selectedFolderId = "all";
        saveWithoutRender();
        renderFolders();
      }
    });
    modal.addEventListener("change", (event) => {
      const folderId = event.target.dataset.dialogFolderHidden;
      if (!folderId) return;
      const folder = state.folders.find((item) => item.id === folderId);
      if (!folder) return;
      folder.hidden = event.target.checked;
      if (event.target.checked) resetPreviewReveal();
      saveWithoutRender();
    });
    modal.addEventListener("keydown", (event) => {
      if (event.key === "Enter" && event.target.matches("[data-dialog-folder-name]")) {
        event.preventDefault();
        close();
        return;
      }
      if (event.key === "Escape") {
        event.preventDefault();
        close();
      }
    });
  }

  function renderUi() {
    if (privacyLocked) {
      root.innerHTML = `
        <div class="spm-row-wrap">
          ${privacySwitch({ checked: true, disabled: true })}
          ${iconButton("delete", "Reset encrypted prompt data", 'data-action="reset-private-data"', "spm-btn-danger")}
          <span class="spm-muted">${escapeHtml(privacyBusy ? "Decrypting..." : status)}</span>
        </div>
        <details class="spm-section" open><summary>Private Library Locked</summary>
          <div class="spm-warn">This workflow contains encrypted Smart Prompt Manager data, but it could not be decrypted with the local key file.</div>
          <div class="spm-muted">Restore the matching <code>config/privacy_key.json</code> file and refresh ComfyUI. Resetting discards the encrypted prompt library for this node.</div>
        </details>
      `;
      setTimeout(() => {
        syncPanelSize();
        ensureMinimumNodeSize();
      }, 0);
      return;
    }
    const prompt = selectedPrompt(state);
    const resolution = currentResolution(prompt);
    const warnings = [...validateState(state), ...resolution.warnings];
    const allFolders = [...VIRTUAL_FOLDERS, ...state.folders];
    const folderOptions = allFolders
      .map((folder) => `<option value="${escapeHtml(folder.id)}" ${folder.id === state.selectedFolderId ? "selected" : ""}>${escapeHtml(folder.name)}</option>`)
      .join("");
    const selectedPreviewHidden = isPreviewHidden(state, prompt);
    const revealSelectedPreview = !selectedPreviewHidden || previewRevealActive;
    const previewPlaceholder = '<span class="spm-muted">Preview hidden. Hover over the node to reveal it.</span>';
    const selectedTitle = revealSelectedPreview ? prompt?.title || "No prompt selected" : "Hidden prompt";
    const list = visiblePrompts()
      .map(
        (item) => {
          const itemHidden = isPreviewHidden(state, item);
          const revealItem = !itemHidden || previewRevealActive;
          return `<div class="spm-prompt-item ${item.id === state.selectedPromptId ? "is-selected" : ""}" data-prompt-id="${escapeHtml(item.id)}" title="${escapeHtml(revealItem ? promptHoverPreview(item) : "Hidden prompt. Hover over the node to reveal it.")}">
            <span>${item.favorite ? "★" : "☆"}</span><span class="spm-prompt-title">${escapeHtml(revealItem ? item.title : "Hidden prompt")}</span><span class="spm-mini">${revealItem ? escapeHtml(folderName(state, item.folderId)) : "hidden"}</span>
          </div>`;
        },
      )
      .join("");
    root.innerHTML = `
      <div class="spm-row-wrap spm-toolbar">
        ${iconButton("prompts", "Edit prompts", 'data-action="open-prompt-editor"')}
        ${iconButton("folder", "Edit folders", 'data-action="open-folders-editor"')}
        ${iconButton("variable", "Edit variables", 'data-action="open-variables-editor"')}
        ${iconButton("reroll", "Reroll variables", 'data-action="reroll"')}
        ${privacySwitch({ checked: state.privacyMode, disabled: privacyBusy })}
      </div>
      <details class="spm-section" open><summary>Prompt Library</summary>
        <div class="spm-row">
          <select data-field="selectedFolderId">${folderOptions}</select>
          <input type="text" data-field="search" value="${escapeHtml(state.search)}" placeholder="Search">
        </div>
        <div class="spm-prompt-list">${list || '<div class="spm-muted" style="padding:6px">No prompts match.</div>'}</div>
      </details>
      <details class="spm-section" open><summary>Selected Prompt</summary>
        <div class="spm-node-summary">
          <div class="spm-node-summary-title" title="${escapeHtml(selectedTitle)}">${escapeHtml(selectedTitle)}</div>
          <div class="spm-mini">${revealSelectedPreview ? escapeHtml(folderName(state, prompt?.folderId || "")) : "hidden"}${revealSelectedPreview && prompt?.tags?.length ? ` · ${escapeHtml(prompt.tags.join(", "))}` : ""}${revealSelectedPreview && prompt?.locked ? " · locked" : ""}${selectedPreviewHidden ? " · hidden" : ""}</div>
          ${prompt?.description && revealSelectedPreview ? `<div class="spm-muted">${escapeHtml(prompt.description)}</div>` : ""}
        </div>
        <div class="spm-row-wrap">
          <label title="Mark this prompt as a favorite"><input type="checkbox" title="Mark this prompt as a favorite" data-prompt-bool="favorite" ${prompt?.favorite ? "checked" : ""}> Favorite</label>
          <label title="Lock this prompt to prevent accidental edits"><input type="checkbox" title="Lock this prompt to prevent accidental edits" data-prompt-bool="locked" ${prompt?.locked ? "checked" : ""}> Locked</label>
          <label title="Hide this prompt preview until the node is hovered"><input type="checkbox" title="Hide this prompt preview until the node is hovered" data-prompt-bool="hidden" ${prompt?.hidden ? "checked" : ""}> Hidden preview</label>
          ${iconButton("copy", "Copy resolved prompt", 'data-action="copy-resolved"')}
          ${iconButton("json", "Copy prompt JSON", 'data-action="copy-prompt-json"')}
        </div>
        <div class="spm-mini">Highlighted preview</div>
        <div class="spm-preview">${revealSelectedPreview ? renderPreview(prompt?.text || "", resolution) : previewPlaceholder}</div>
        <div class="spm-mini">Resolved preview</div>
        <div class="spm-preview">${revealSelectedPreview ? escapeHtml(resolution.resolved_prompt) : previewPlaceholder}</div>
      </details>
      <details class="spm-section"><summary>Import / Export</summary>
        <div class="spm-row-wrap">
          ${iconButton("export", "Export library", 'data-action="export-library"')}
          ${iconButton("importMerge", "Import and merge library", 'data-action="import-merge"')}
          ${iconButton("importReplace", "Import and replace library", 'data-action="import-replace"')}
          ${iconButton("paste", "Paste prompt JSON", 'data-action="paste-prompt-json"')}
        </div>
        <textarea class="spm-copybox" data-role="json-box" placeholder="Import/export/copy fallback JSON"></textarea>
      </details>
      <details class="spm-section"><summary>Debug / Preview</summary>
        ${warnings.length ? warnings.map((warning) => `<div class="spm-warn">${escapeHtml(warning)}</div>`).join("") : '<div class="spm-muted">No warnings.</div>'}
      </details>
    `;
    setTimeout(() => {
      syncPanelSize();
      ensureMinimumNodeSize();
    }, 0);
  }

  root.addEventListener("pointerenter", () => {
    setPreviewReveal(true);
  });
  root.addEventListener("pointerleave", () => {
    setPreviewReveal(false);
  });

  root.addEventListener("mouseover", (event) => {
    const target = event.target.closest?.(".spm-var");
    if (!target) return;
    tooltip = createElement("div", "spm-tooltip", variableTooltip(target.dataset.var));
    document.body.appendChild(tooltip);
    tooltip.style.left = `${event.clientX + 12}px`;
    tooltip.style.top = `${event.clientY + 12}px`;
  });
  root.addEventListener("mousemove", (event) => {
    if (tooltip) {
      tooltip.style.left = `${event.clientX + 12}px`;
      tooltip.style.top = `${event.clientY + 12}px`;
    }
  });
  root.addEventListener("mouseout", (event) => {
    if (event.target.closest?.(".spm-var") && tooltip) {
      tooltip.remove();
      tooltip = null;
    }
  });

  root.addEventListener("click", async (event) => {
    const privacyToggle = event.target.closest?.("[data-privacy-mode]");
    if (privacyToggle) {
      event.stopPropagation();
      await setPrivacyMode(privacyToggle.checked);
      return;
    }
    const actionButton = event.target.closest?.("[data-action]");
    const action = actionButton?.dataset.action;
    if (action === "reset-private-data") {
      if (!confirm("Reset encrypted prompt data for this node? This discards the encrypted library if the local key cannot be restored.")) return;
      privacyLocked = false;
      privacyBusy = false;
      forgetPrivacyEnvelope(node, SPM_PRIVACY_FIELD);
      state = defaultState();
      state.privacyMode = false;
      status = "Encrypted prompt data reset.";
      save();
      return;
    }
    if (privacyLocked) return;
    const promptItem = event.target.closest?.("[data-prompt-id]");
    if (promptItem) {
      state.selectedPromptId = promptItem.dataset.promptId;
      save();
      return;
    }
    const suggestion = event.target.closest?.("[data-suggest]");
    if (suggestion) {
      const textarea = root.querySelector(".spm-editor");
      autocomplete.active = autocomplete.items.indexOf(suggestion.dataset.suggest);
      acceptAutocomplete(textarea);
      return;
    }
    if (!action) return;
    try {
      if (action === "reroll") {
        if (rerollWidget) rerollWidget.value = (Number.parseInt(rerollWidget.value || 0, 10) || 0) + 1;
      } else if (action === "open-prompt-editor") {
        openPromptDialog();
        return;
      } else if (action === "open-folders-editor") {
        openFoldersDialog();
        return;
      } else if (action === "open-variables-editor") {
        openVariablesDialog();
        return;
      } else if (action === "add-variable") {
        let name = "variable";
        let index = 2;
        while (state.variables[name]) {
          name = `variable${index}`;
          index += 1;
        }
        state.variables[name] = { mode: "random", values: ["value"], fixedValue: null, fallback: "", description: "" };
      } else if (action === "remove-variable") {
        delete state.variables[actionButton.dataset.var];
      } else if (action === "copy-resolved") {
        await copyText(currentResolution().resolved_prompt, "[data-role='json-box']");
        return;
      } else if (action === "copy-prompt-json") {
        await copyText(selectedPromptJson(), "[data-role='json-box']");
        return;
      } else if (action === "export-library") {
        const text = JSON.stringify(state, null, 2);
        root.querySelector("[data-role='json-box']").value = text;
        await copyText(text, "[data-role='json-box']");
        return;
      } else if (action === "paste-prompt-json") {
        addPromptFromJson(root.querySelector("[data-role='json-box']").value);
        return;
      } else if (action === "import-merge" || action === "import-replace") {
        mergeLibrary(root.querySelector("[data-role='json-box']").value, action === "import-replace");
        return;
      }
      save();
    } catch (error) {
      status = `Error: ${error.message}`;
      renderUi();
    }
  });

  root.addEventListener("input", (event) => {
    const prompt = selectedPrompt(state);
    if (event.target.matches("[data-privacy-mode]")) return;
    if (event.target.dataset.promptBool && prompt) {
      const field = event.target.dataset.promptBool;
      prompt[field] = event.target.checked;
      if (field === "hidden" && event.target.checked) resetPreviewReveal();
      prompt.updatedAt = nowIso();
      save();
      return;
    }
    if (event.target.type === "checkbox") return;
    if (event.target.matches("[data-field='search']")) {
      state.search = event.target.value;
      savePreservingFocus(event.target);
      return;
    }
    if (event.target.matches("[data-field='selectedFolderId']")) {
      state.selectedFolderId = event.target.value;
      savePreservingFocus(event.target);
      return;
    }
    if (prompt && !prompt.locked && event.target.dataset.promptField) {
      const field = event.target.dataset.promptField;
      prompt[field] = field === "tags" ? tagsFromDraft(event.target.value) : event.target.value;
      prompt.updatedAt = nowIso();
      if (field === "text") updateAutocomplete(event.target);
      if (field === "title" || field === "tags" || field === "description") {
        saveWithoutRender();
        return;
      }
    }
    if (event.target.dataset.varMode) state.variables[event.target.dataset.varMode].mode = event.target.value;
    if (event.target.dataset.varValues) state.variables[event.target.dataset.varValues].values = normalizeValues(event.target.value);
    if (event.target.dataset.varFixed) state.variables[event.target.dataset.varFixed].fixedValue = event.target.value || null;
    if (event.target.dataset.varFallback) state.variables[event.target.dataset.varFallback].fallback = event.target.value;
    if (event.target.dataset.varDescription) state.variables[event.target.dataset.varDescription].description = event.target.value;
    if (event.target.dataset.varName) {
      const oldName = event.target.dataset.varName;
      const newName = event.target.value.trim();
      if (VALID_NAME_RE.test(newName) && !state.variables[newName]) {
        state.variables[newName] = state.variables[oldName];
        delete state.variables[oldName];
        const tokenPattern = new RegExp(`\\{\\{\\s*${oldName.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}\\s*\\}\\}`, "g");
        state.prompts.forEach((item) => {
          item.text = item.text.replace(tokenPattern, `{{${newName}}}`);
        });
      }
    }
    savePreservingFocus(event.target);
  });

  root.addEventListener("change", async (event) => {
    if (privacyLocked) return;
    if (event.target.matches("[data-privacy-mode]")) {
      await setPrivacyMode(event.target.checked);
      return;
    }
    const prompt = selectedPrompt(state);
    if (event.target.dataset.promptField && prompt && !prompt.locked) {
      const field = event.target.dataset.promptField;
      prompt[field] = field === "tags" ? normalizeTags(event.target.value) : event.target.value;
      prompt.updatedAt = nowIso();
      savePreservingFocus(event.target);
      return;
    }
    if (event.target.dataset.varMode) {
      state.variables[event.target.dataset.varMode].mode = event.target.value;
      savePreservingFocus(event.target);
      return;
    }
    if (event.target.dataset.promptBool && prompt) {
      const field = event.target.dataset.promptBool;
      prompt[field] = event.target.checked;
      if (field === "hidden" && event.target.checked) resetPreviewReveal();
      prompt.updatedAt = nowIso();
      save();
    }
    if (event.target.matches("[data-field='selectedFolderId']")) {
      state.selectedFolderId = event.target.value;
      save();
    }
  });

  root.addEventListener("keydown", (event) => {
    if (isEditableField(event.target)) {
      // ComfyUI binds graph shortcuts such as Space at the canvas/document level.
      // Keep normal typing inside the embedded manager from reaching those handlers.
      event.stopPropagation();
    }
    const textarea = event.target.closest?.(".spm-editor");
    if (!textarea) return;
    if (event.key === KEYS.close && autocomplete.open) {
      autocomplete.open = false;
      event.preventDefault();
      renderUi();
      return;
    }
    if (event.ctrlKey && autocomplete.open && event.key.toLowerCase() === KEYS.next) {
      autocomplete.active = (autocomplete.active + 1) % autocomplete.items.length;
      event.preventDefault();
      renderUi();
      return;
    }
    if (event.ctrlKey && autocomplete.open && event.key.toLowerCase() === KEYS.previous) {
      autocomplete.active = (autocomplete.active + autocomplete.items.length - 1) % autocomplete.items.length;
      event.preventDefault();
      renderUi();
      return;
    }
    if (event.ctrlKey && autocomplete.open && event.key.toLowerCase() === KEYS.accept) {
      event.preventDefault();
      acceptAutocomplete(textarea);
    }
  });

  root.addEventListener("keyup", (event) => {
    if (isEditableField(event.target)) event.stopPropagation();
  });

  stopComfyShortcuts(root);

  const originalOnResize = node.onResize;
  node.onResize = function onResize(size) {
    const result = originalOnResize?.apply(this, arguments);
    syncPanelSize();
    return result;
  };

  const originalSetSize = node.setSize;
  node.setSize = function setSize(size) {
    const result = originalSetSize ? originalSetSize.apply(this, arguments) : undefined;
    if (!originalSetSize && Array.isArray(size)) this.size = size;
    syncPanelSize();
    return result;
  };

  const originalOnDrawForeground = node.onDrawForeground;
  node.onDrawForeground = function onDrawForeground(ctx) {
    const result = originalOnDrawForeground?.apply(this, arguments);
    refreshNodeTheme();
    syncPanelSize({ dirty: false });
    return result;
  };

  if (node.addDOMWidget) {
    uiWidget = node.addDOMWidget("smart_prompt_manager_ui", "SmartPromptManager", widgetFrame, {
      serialize: false,
      hideOnZoom: false,
      getMinHeight: () => panelHeight(),
      getMaxHeight: () => panelHeight(),
      getHeight: () => panelHeight(),
      onDraw: () => syncPanelSize({ dirty: false }),
    });
    syncWidgetSizingCallbacks();
    requestAnimationFrame(() => syncPanelSize());
  } else {
    node.addWidget("button", "Smart Prompt Manager UI unavailable", null, () => {});
  }
  if (!privacyLocked) save(false);
  ensureMinimumNodeSize();
  refreshNodeTheme(true);
  syncPanelSize();
  renderUi();
  if (initialEncryptedValue) void decryptInitialState();
}

scheduleSpmSeedQueuePatch();
scheduleSpmGraphToPromptPatch();

app.registerExtension({
  name: EXTENSION_NAME,
  setup() {
    scheduleSpmSeedQueuePatch("setup");
    scheduleSpmGraphToPromptPatch("setup");
  },
  async beforeRegisterNodeDef(nodeType, nodeData) {
    if (nodeData.name !== NODE_CLASS) return;
    const original = nodeType.prototype.onNodeCreated;
    nodeType.prototype.onNodeCreated = function onNodeCreated() {
      original?.apply(this, arguments);
      requestAnimationFrame(() => enhanceNode(this));
    };
  },
});
