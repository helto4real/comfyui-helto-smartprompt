import { app } from "../../scripts/app.js";

const NODE_CLASS = "SmartPromptManager";
const EXTENSION_NAME = "helto.smartPromptManager";
const VALID_NAME_RE = /^[A-Za-z0-9_-]+$/;
const TOKEN_RE = /\{\{([^{}]*)\}\}/g;
const MODES = ["random", "fixed", "cycle"];
const VIRTUAL_FOLDERS = [
  { id: "all", name: "All" },
  { id: "unsorted", name: "Unsorted" },
  { id: "favorites", name: "Favorites" },
];
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

function nowIso() {
  return new Date().toISOString().replace(/\.\d{3}Z$/, "Z");
}

function makeId(prefix) {
  if (crypto?.randomUUID) return `${prefix}_${crypto.randomUUID().replaceAll("-", "").slice(0, 12)}`;
  return `${prefix}_${Math.random().toString(16).slice(2, 14)}`;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function stableHash(text) {
  let value = 2166136261;
  for (let i = 0; i < text.length; i += 1) {
    value ^= text.charCodeAt(i);
    value = Math.imul(value, 16777619) >>> 0;
  }
  return value >>> 0;
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
    folders: [{ id: folderId, name: "Portraits" }],
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
    folders.push({ id, name: rawName.trim() ? rawName : "Folder" });
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
  widget.value = JSON.stringify(state, null, 2);
  if (node.graph) node.graph.setDirtyCanvas(true, true);
}

function hideWidget(widget) {
  if (!widget) return;
  widget.hidden = true;
  widget.computeSize = () => [0, -4];
  widget.draw = () => {};
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

function injectStyles() {
  if (document.getElementById("spm-styles")) return;
  const style = document.createElement("style");
  style.id = "spm-styles";
  style.textContent = `
    .spm-root{font:12px system-ui, sans-serif;color:#e8edf2;background:#1b2028;border:1px solid #394251;border-radius:6px;padding:8px;width:100%;height:100%;overflow:auto;box-sizing:border-box;overscroll-behavior:contain}
    .spm-row{display:flex;gap:6px;align-items:center;margin:5px 0}.spm-row-wrap{display:flex;gap:6px;align-items:center;flex-wrap:wrap;margin:5px 0}
    .spm-root input,.spm-root textarea,.spm-root select{background:#11161d;color:#edf2f7;border:1px solid #3c4655;border-radius:4px;padding:4px;font:12px system-ui, sans-serif;box-sizing:border-box}
    .spm-root textarea{width:100%;resize:vertical;min-height:54px}.spm-root input[type=text],.spm-root select{min-width:0}
    .spm-btn{background:#263241;color:#f5f7fa;border:1px solid #4c5b70;border-radius:4px;padding:4px 7px;cursor:pointer;font:12px system-ui, sans-serif;white-space:nowrap}
    .spm-btn:hover{background:#314155}.spm-btn-danger{border-color:#7e3d45;color:#ffdce0}.spm-btn-quiet{background:#1d2530;color:#cbd5e1}
    .spm-section{border-top:1px solid #333d4b;margin-top:8px;padding-top:7px}.spm-section summary{cursor:pointer;font-weight:700;color:#f8fafc}
    .spm-prompt-list{max-height:92px;overflow:auto;border:1px solid #313b49;border-radius:4px;background:#121821}
    .spm-prompt-item{display:flex;align-items:center;gap:5px;padding:4px 6px;border-bottom:1px solid #222b36;cursor:pointer}
    .spm-prompt-item:last-child{border-bottom:0}.spm-prompt-item.is-selected{background:#244463}.spm-prompt-item:hover{background:#293647}
    .spm-prompt-title{flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.spm-muted{color:#96a3b5}.spm-mini{font-size:11px;color:#aeb8c6}
    .spm-preview{white-space:pre-wrap;line-height:1.45;background:#101820;border:1px solid #303a48;border-radius:4px;padding:6px;min-height:28px;max-height:76px;overflow:auto}
    .spm-var{background:#173c50;color:#b8efff;border:1px solid #287095;border-radius:3px;padding:0 2px}.spm-var-warn{background:#4a272c;color:#ffd2d6;border-color:#9a4954}
    .spm-grid{display:grid;grid-template-columns:1fr 76px 1.2fr 1fr 1fr 1.2fr 26px;gap:4px;align-items:start}.spm-grid-head{font-weight:700;color:#cbd5e1}
    .spm-grid textarea{min-height:34px}.spm-warn{background:#382f16;border:1px solid #856a22;color:#ffe5a3;border-radius:4px;padding:5px;margin-top:5px}
    .spm-autocomplete{position:absolute;z-index:10000;background:#101820;border:1px solid #53657a;border-radius:4px;box-shadow:0 8px 22px rgba(0,0,0,.35);max-height:150px;overflow:auto;min-width:210px}
    .spm-suggestion{display:flex;gap:8px;justify-content:space-between;padding:5px 7px;cursor:pointer}.spm-suggestion.is-active{background:#24537a}.spm-suggestion-name{font-weight:700;color:#dff7ff}
    .spm-copybox{width:100%;min-height:54px}.spm-tooltip{position:absolute;z-index:10001;max-width:320px;background:#0d131a;border:1px solid #526174;border-radius:5px;padding:7px;color:#f8fafc;box-shadow:0 8px 24px rgba(0,0,0,.4);pointer-events:none}
    .spm-modal-backdrop{position:fixed;inset:0;z-index:9999;background:rgba(0,0,0,.58);display:flex;align-items:center;justify-content:center;padding:24px;box-sizing:border-box}
    .spm-modal{width:min(960px,calc(100vw - 48px));max-height:calc(100vh - 48px);overflow:auto;background:#171d26;color:#e8edf2;border:1px solid #536174;border-radius:8px;box-shadow:0 22px 70px rgba(0,0,0,.55);padding:12px;box-sizing:border-box;font:13px system-ui,sans-serif}
    .spm-modal-header{display:flex;align-items:center;justify-content:space-between;gap:12px;border-bottom:1px solid #343e4c;padding-bottom:8px;margin-bottom:10px}.spm-modal-title{font-weight:700;font-size:15px}
    .spm-modal input,.spm-modal textarea,.spm-modal select{background:#0f151d;color:#edf2f7;border:1px solid #3c4655;border-radius:4px;padding:6px;font:13px system-ui,sans-serif;box-sizing:border-box}
    .spm-modal textarea{width:100%;resize:vertical}.spm-dialog-editor{min-height:220px}.spm-dialog-description{min-height:70px}
    .spm-modal .spm-row,.spm-modal .spm-row-wrap{margin:7px 0}.spm-modal .spm-preview{max-height:170px}.spm-modal-field{display:flex;flex-direction:column;gap:4px;flex:1}.spm-modal-field label{font-size:11px;color:#aeb8c6}
    .spm-modal-grid{display:grid;grid-template-columns:minmax(110px,1fr) 92px minmax(170px,1.4fr) minmax(110px,1fr) minmax(110px,1fr) minmax(150px,1.2fr) 34px;gap:5px;align-items:start}.spm-modal-grid textarea{min-height:54px}
    .spm-node-summary{background:#101820;border:1px solid #303a48;border-radius:4px;padding:6px;line-height:1.35}.spm-node-summary-title{font-weight:700;color:#f8fafc}
  `;
  document.head.appendChild(style);
}

function enhanceNode(node) {
  injectStyles();
  const dataWidget = node.widgets?.find((widget) => widget.name === "spm_data");
  if (!dataWidget || node.__spmEnhanced) return;
  node.__spmEnhanced = true;
  hideWidget(dataWidget);

  let state = parseState(dataWidget.value);
  let status = "";
  let autocomplete = { open: false, items: [], active: 0, start: 0, end: 0, partial: "" };
  let tooltip = null;
  const root = createElement("div", "spm-root");

  const seedWidget = node.widgets?.find((widget) => widget.name === "seed");
  const rerollWidget = node.widgets?.find((widget) => widget.name === "reroll");
  const getSeed = () => Number.parseInt(seedWidget?.value || 0, 10) || 0;
  const getReroll = () => Number.parseInt(rerollWidget?.value || 0, 10) || 0;

  function panelWidth() {
    return Math.max(PANEL_MIN_WIDTH, Math.floor((node.size?.[0] || PANEL_DEFAULT_WIDTH + 20) - 28));
  }

  function panelHeight() {
    return Math.max(PANEL_MIN_HEIGHT, Math.floor((node.size?.[1] || PANEL_DEFAULT_HEIGHT + NODE_CHROME_HEIGHT) - NODE_CHROME_HEIGHT));
  }

  function syncPanelSize() {
    root.style.width = `${panelWidth()}px`;
    root.style.height = `${panelHeight()}px`;
    root.style.maxHeight = `${panelHeight()}px`;
    node.graph?.setDirtyCanvas(true, true);
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

  function save(render = true) {
    state = normalizeState(state);
    setWidgetValue(node, dataWidget, state);
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
    setWidgetValue(node, dataWidget, state);
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
    return `${prompt.text}\n\nVariables:\n${variableLines || "none"}\n\nResolved:\n${resolution.resolved_prompt}\n${resolution.warnings.length ? `\nWarnings:\n${resolution.warnings.join("\n")}` : ""}`;
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

  function openPromptDialog(options = {}) {
    const isDraft = Boolean(options.draftPrompt);
    const prompt = options.draftPrompt || selectedPrompt(state);
    if (!prompt) return;
    const backdrop = createElement("div", "spm-modal-backdrop");
    const modal = createElement("div", "spm-modal");
    const resolution = currentResolution(prompt);
    const folderOptions = [`<option value="">Unsorted</option>`]
      .concat(state.folders.map((folder) => `<option value="${escapeHtml(folder.id)}" ${folder.id === prompt.folderId ? "selected" : ""}>${escapeHtml(folder.name)}</option>`))
      .join("");
    modal.innerHTML = `
      <div class="spm-modal-header">
        <div class="spm-modal-title">${isDraft ? "Add Prompt" : "Edit Prompt"}</div>
        <div class="spm-row-wrap">
          <button class="spm-btn" data-dialog-action="save-close">Done</button>
          <button class="spm-btn spm-btn-quiet" data-dialog-action="close">Close</button>
        </div>
      </div>
      <div class="spm-row">
        <div class="spm-modal-field"><label>Title</label><input type="text" data-dialog-prompt-field="title" value="${escapeHtml(prompt.title || "")}" ${prompt.locked ? "disabled" : ""}></div>
        <div class="spm-modal-field"><label>Folder</label><select data-dialog-prompt-field="folderId" ${prompt.locked ? "disabled" : ""}>${folderOptions}</select></div>
        <div class="spm-modal-field"><label>Tags</label><input type="text" data-dialog-prompt-field="tags" value="${escapeHtml(tagsForInput(prompt.tags))}" placeholder="portrait, cinematic" ${prompt.locked ? "disabled" : ""}></div>
      </div>
      <div class="spm-row-wrap">
        <label><input type="checkbox" data-dialog-prompt-bool="favorite" ${prompt.favorite ? "checked" : ""}> Favorite</label>
        <label><input type="checkbox" data-dialog-prompt-bool="locked" ${prompt.locked ? "checked" : ""}> Locked</label>
      </div>
      <div class="spm-modal-field"><label>Description</label><textarea class="spm-dialog-description" data-dialog-prompt-field="description" ${prompt.locked ? "disabled" : ""}>${escapeHtml(prompt.description || "")}</textarea></div>
      <div class="spm-modal-field" style="position:relative"><label>Prompt text</label><textarea class="spm-dialog-editor" data-dialog-prompt-field="text" ${prompt.locked ? "disabled" : ""}>${escapeHtml(prompt.text || "")}</textarea><div class="spm-autocomplete" data-dialog-autocomplete style="display:none;left:8px;top:250px"></div></div>
      <div class="spm-row-wrap">
        <button class="spm-btn" data-dialog-action="copy-resolved">Copy resolved</button>
        <button class="spm-btn" data-dialog-action="copy-prompt-json">Copy prompt JSON</button>
      </div>
      <div class="spm-mini">Highlighted preview</div>
      <div class="spm-preview" data-dialog-highlight>${renderPreview(prompt.text || "", resolution)}</div>
      <div class="spm-mini">Resolved preview</div>
      <div class="spm-preview" data-dialog-resolved>${escapeHtml(resolution.resolved_prompt)}</div>
    `;
    backdrop.appendChild(modal);
    document.body.appendChild(backdrop);
    stopComfyShortcuts(backdrop);

    const editor = modal.querySelector(".spm-dialog-editor");
    const popup = modal.querySelector("[data-dialog-autocomplete]");
    const updatePreview = () => {
      const nextResolution = currentResolution(prompt);
      modal.querySelector("[data-dialog-highlight]").innerHTML = renderPreview(prompt.text || "", nextResolution);
      modal.querySelector("[data-dialog-resolved]").textContent = nextResolution.resolved_prompt;
    };
    const close = (commit = false) => {
      autocomplete.open = false;
      const tagsInput = modal.querySelector("[data-dialog-prompt-field='tags']");
      if (tagsInput && !prompt.locked) prompt.tags = normalizeTags(tagsInput.value);
      backdrop.remove();
      if (isDraft) {
        if (commit) {
          const existingNames = state.prompts.map((item) => item.title);
          if (state.prompts.some((item) => item.title.toLowerCase() === prompt.title.toLowerCase())) {
            prompt.title = suffixName(prompt.title, existingNames);
          }
          state.prompts.push(prompt);
          state.selectedPromptId = prompt.id;
          save();
        }
        return;
      }
      save();
    };

    modal.addEventListener("input", (event) => {
      if (!event.target.dataset.dialogPromptField || prompt.locked) return;
      const field = event.target.dataset.dialogPromptField;
      prompt[field] = field === "tags" ? tagsFromDraft(event.target.value) : event.target.value;
      prompt.updatedAt = nowIso();
      if (field === "text") {
        updateAutocomplete(event.target);
        renderAutocompleteInto(popup);
        updatePreview();
      }
      if (!isDraft) saveWithoutRender();
    });
    modal.addEventListener("change", (event) => {
      if (event.target.dataset.dialogPromptField && !prompt.locked) {
        const field = event.target.dataset.dialogPromptField;
        prompt[field] = field === "tags" ? normalizeTags(event.target.value) : event.target.value;
        if (field === "tags") event.target.value = tagsForInput(prompt.tags);
        prompt.updatedAt = nowIso();
        updatePreview();
        if (!isDraft) saveWithoutRender();
      }
      if (event.target.dataset.dialogPromptBool) {
        prompt[event.target.dataset.dialogPromptBool] = event.target.checked;
        prompt.updatedAt = nowIso();
        if (!isDraft) saveWithoutRender();
      }
    });
    modal.addEventListener("click", async (event) => {
      const suggestion = event.target.closest?.("[data-suggest]");
      if (suggestion) {
        autocomplete.active = autocomplete.items.indexOf(suggestion.dataset.suggest);
        acceptAutocompleteInPromptDialog(editor, popup, updatePreview, prompt, !isDraft);
        return;
      }
      const action = event.target.closest?.("[data-dialog-action]")?.dataset.dialogAction;
      if (action === "close") close(false);
      if (action === "save-close") close(true);
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
        acceptAutocompleteInPromptDialog(editor, popup, updatePreview, prompt, !isDraft);
      }
    });
    modal.querySelector("[data-dialog-prompt-field='title']")?.focus();
  }

  function openVariablesDialog() {
    const backdrop = createElement("div", "spm-modal-backdrop");
    const modal = createElement("div", "spm-modal");
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
            <button class="spm-btn spm-btn-danger" data-dialog-action="remove-variable" data-var="${escapeHtml(name)}">×</button>
          </div>`,
        )
        .join("");
      modal.innerHTML = `
        <div class="spm-modal-header">
          <div class="spm-modal-title">Edit Variables</div>
          <div class="spm-row-wrap">
            <button class="spm-btn" data-dialog-action="add-variable">Add variable</button>
            <button class="spm-btn" data-dialog-action="save-close">Done</button>
          </div>
        </div>
        <div class="spm-modal-grid spm-grid-head"><span>Name</span><span>Mode</span><span>Values</span><span>Fixed</span><span>Fallback</span><span>Description</span><span></span></div>
        ${variableRows || '<div class="spm-muted">No variables yet.</div>'}
      `;
    };
    renderVariables();

    const close = () => {
      backdrop.remove();
      save();
    };
    modal.addEventListener("input", (event) => {
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
          event.target.dataset.varName = newName;
        }
      }
      saveWithoutRender();
    });
    modal.addEventListener("change", (event) => {
      if (event.target.dataset.varMode) {
        state.variables[event.target.dataset.varMode].mode = event.target.value;
        saveWithoutRender();
      }
    });
    modal.addEventListener("click", (event) => {
      const action = event.target.closest?.("[data-dialog-action]")?.dataset.dialogAction;
      if (action === "save-close") close();
      if (action === "add-variable") {
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
        delete state.variables[event.target.dataset.var];
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

  function renderUi() {
    const prompt = selectedPrompt(state);
    const resolution = currentResolution(prompt);
    const warnings = [...validateState(state), ...resolution.warnings];
    const allFolders = [...VIRTUAL_FOLDERS, ...state.folders];
    const folderOptions = allFolders
      .map((folder) => `<option value="${escapeHtml(folder.id)}" ${folder.id === state.selectedFolderId ? "selected" : ""}>${escapeHtml(folder.name)}</option>`)
      .join("");
    const list = visiblePrompts()
      .map(
        (item) => `<div class="spm-prompt-item ${item.id === state.selectedPromptId ? "is-selected" : ""}" data-prompt-id="${escapeHtml(item.id)}" title="${escapeHtml(promptHoverPreview(item))}">
          <span>${item.favorite ? "★" : "☆"}</span><span class="spm-prompt-title">${escapeHtml(item.title)}</span><span class="spm-mini">${escapeHtml(folderName(state, item.folderId))}</span>
        </div>`,
      )
      .join("");
    const usedVariables = prompt ? variablesUsed(prompt.text || "") : [];
    const variableSummary = Object.keys(state.variables).sort((a, b) => a.localeCompare(b));

    root.innerHTML = `
      <div class="spm-row-wrap">
        <button class="spm-btn" data-action="add-prompt">Add</button>
        <button class="spm-btn" data-action="duplicate-prompt" ${!prompt ? "disabled" : ""}>Duplicate</button>
        <button class="spm-btn spm-btn-danger" data-action="delete-prompt" ${!prompt ? "disabled" : ""}>Delete</button>
        <button class="spm-btn" data-action="reroll">Reroll</button>
        <span class="spm-muted">${escapeHtml(status)}</span>
      </div>
      <details class="spm-section" open><summary>Prompt Library</summary>
        <div class="spm-row">
          <select data-field="selectedFolderId">${folderOptions}</select>
          <input type="text" data-field="search" value="${escapeHtml(state.search)}" placeholder="Search">
        </div>
        <div class="spm-row-wrap">
          <button class="spm-btn spm-btn-quiet" data-action="add-folder">Add folder</button>
          <button class="spm-btn spm-btn-quiet" data-action="rename-folder">Rename</button>
          <button class="spm-btn spm-btn-danger" data-action="delete-folder">Delete folder</button>
        </div>
        <div class="spm-prompt-list">${list || '<div class="spm-muted" style="padding:6px">No prompts match.</div>'}</div>
      </details>
      <details class="spm-section" open><summary>Selected Prompt</summary>
        <div class="spm-node-summary">
          <div class="spm-node-summary-title">${escapeHtml(prompt?.title || "No prompt selected")}</div>
          <div class="spm-mini">${escapeHtml(folderName(state, prompt?.folderId || ""))}${prompt?.tags?.length ? ` · ${escapeHtml(prompt.tags.join(", "))}` : ""}${prompt?.locked ? " · locked" : ""}</div>
          ${prompt?.description ? `<div class="spm-muted">${escapeHtml(prompt.description)}</div>` : ""}
        </div>
        <div class="spm-row-wrap">
          <button class="spm-btn" data-action="open-prompt-editor" ${!prompt ? "disabled" : ""}>Edit prompt</button>
          <label><input type="checkbox" data-prompt-bool="favorite" ${prompt?.favorite ? "checked" : ""}> Favorite</label>
          <label><input type="checkbox" data-prompt-bool="locked" ${prompt?.locked ? "checked" : ""}> Locked</label>
          <button class="spm-btn" data-action="copy-resolved">Copy resolved</button>
          <button class="spm-btn" data-action="copy-prompt-json">Copy prompt JSON</button>
        </div>
        <div class="spm-mini">Highlighted preview</div>
        <div class="spm-preview">${renderPreview(prompt?.text || "", resolution)}</div>
        <div class="spm-mini">Resolved preview</div>
        <div class="spm-preview">${escapeHtml(resolution.resolved_prompt)}</div>
      </details>
      <details class="spm-section"><summary>Variables</summary>
        <div class="spm-node-summary">
          <div>${variableSummary.length ? escapeHtml(variableSummary.join(", ")) : '<span class="spm-muted">No variables defined.</span>'}</div>
          <div class="spm-mini">Used by selected prompt: ${usedVariables.length ? escapeHtml(usedVariables.join(", ")) : "none"}</div>
        </div>
        <button class="spm-btn" data-action="open-variables-editor">Edit variables</button>
      </details>
      <details class="spm-section"><summary>Import / Export</summary>
        <div class="spm-row-wrap">
          <button class="spm-btn" data-action="export-library">Export library</button>
          <button class="spm-btn" data-action="import-merge">Import merge</button>
          <button class="spm-btn" data-action="import-replace">Import replace</button>
          <button class="spm-btn" data-action="paste-prompt-json">Paste prompt JSON</button>
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
    const action = event.target.closest?.("[data-action]")?.dataset.action;
    if (!action) return;
    const currentPrompt = selectedPrompt(state);
    try {
      if (action === "add-prompt") {
        const created = nowIso();
        const id = makeId("prompt");
        openPromptDialog({
          draftPrompt: {
            id,
            title: "Untitled prompt",
            text: "",
            description: "",
            folderId: state.selectedFolderId && !VIRTUAL_FOLDERS.some((folder) => folder.id === state.selectedFolderId) ? state.selectedFolderId : "",
            tags: [],
            favorite: false,
            locked: false,
            createdAt: created,
            updatedAt: created,
          },
        });
        return;
      } else if (action === "duplicate-prompt" && currentPrompt) {
        const copy = { ...currentPrompt, id: makeId("prompt"), title: suffixName(currentPrompt.title, state.prompts.map((item) => item.title)), locked: false, createdAt: nowIso(), updatedAt: nowIso() };
        state.prompts.push(copy);
        state.selectedPromptId = copy.id;
      } else if (action === "delete-prompt" && currentPrompt && confirm(`Delete prompt "${currentPrompt.title}"?`)) {
        state.prompts = state.prompts.filter((item) => item.id !== currentPrompt.id);
        state.selectedPromptId = state.prompts[0]?.id || "";
      } else if (action === "reroll") {
        if (rerollWidget) rerollWidget.value = (Number.parseInt(rerollWidget.value || 0, 10) || 0) + 1;
      } else if (action === "open-prompt-editor") {
        openPromptDialog();
        return;
      } else if (action === "open-variables-editor") {
        openVariablesDialog();
        return;
      } else if (action === "add-folder") {
        const name = window.prompt("Folder name", "New folder");
        if (name) state.folders.push({ id: makeId("folder"), name: name.trim() || "New folder" });
      } else if (action === "rename-folder") {
        const folder = state.folders.find((item) => item.id === state.selectedFolderId);
        if (folder) folder.name = window.prompt("Folder name", folder.name) || folder.name;
      } else if (action === "delete-folder") {
        const folder = state.folders.find((item) => item.id === state.selectedFolderId);
        if (folder && confirm(`Delete folder "${folder.name}"? Prompts will move to Unsorted.`)) {
          state.prompts.forEach((item) => { if (item.folderId === folder.id) item.folderId = ""; });
          state.folders = state.folders.filter((item) => item.id !== folder.id);
          state.selectedFolderId = "all";
        }
      } else if (action === "add-variable") {
        let name = "variable";
        let index = 2;
        while (state.variables[name]) {
          name = `variable${index}`;
          index += 1;
        }
        state.variables[name] = { mode: "random", values: ["value"], fixedValue: null, fallback: "", description: "" };
      } else if (action === "remove-variable") {
        delete state.variables[event.target.dataset.var];
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

  root.addEventListener("change", (event) => {
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
      prompt[event.target.dataset.promptBool] = event.target.checked;
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

  const originalOnResize = node.onResize;
  node.onResize = function onResize(size) {
    const result = originalOnResize?.apply(this, arguments);
    syncPanelSize();
    return result;
  };

  if (node.addDOMWidget) {
    const uiWidget = node.addDOMWidget("smart_prompt_manager_ui", "SmartPromptManager", root, {
      serialize: false,
      hideOnZoom: false,
      getMinHeight: () => panelHeight(),
      getMaxHeight: () => panelHeight(),
    });
    uiWidget.computeSize = () => [panelWidth() + 12, panelHeight() + 8];
  } else {
    node.addWidget("button", "Smart Prompt Manager UI unavailable", null, () => {});
  }
  save(false);
  ensureMinimumNodeSize();
  syncPanelSize();
  renderUi();
}

app.registerExtension({
  name: EXTENSION_NAME,
  async beforeRegisterNodeDef(nodeType, nodeData) {
    if (nodeData.name !== NODE_CLASS) return;
    const original = nodeType.prototype.onNodeCreated;
    nodeType.prototype.onNodeCreated = function onNodeCreated() {
      original?.apply(this, arguments);
      requestAnimationFrame(() => enhanceNode(this));
    };
  },
});
