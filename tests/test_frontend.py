from pathlib import Path
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]


class SmartPromptManagerFrontendTests(unittest.TestCase):
    def test_seed_frontend_randomizes_live_seed_before_queue(self):
        source = (ROOT / "web/js/smart_prompt_manager.js").read_text(encoding="utf-8")

        self.assertIn("const SEED_MAX = Number.MAX_SAFE_INTEGER;", source)
        self.assertIn("// ---- Seed queue helpers ----", source)
        self.assertIn("function randomizeSpmSeedsBeforeQueue()", source)
        self.assertIn('liveSeedControlMode(node) !== "randomize"', source)
        self.assertIn("writeSpmSeedValue(node, seed)", source)
        self.assertIn("suspendSeedControlCallbacks(controlWidget)", source)
        self.assertIn("restoreQueuedSpmSeeds(queuedSeeds)", source)
        self.assertIn("app.queuePrompt = wrappedQueuePrompt", source)
        self.assertIn('scheduleSpmSeedQueuePatch("setup")', source)
        self.assertIn("spmQueuePromptDepth += 1;", source)
        self.assertIn("spmQueuePromptDepth = Math.max(0, spmQueuePromptDepth - 1);", source)

    def test_seed_queue_helpers_only_randomize_explicit_randomize_mode(self):
        helper_path = ROOT / "web/js/smart_prompt_manager.js"
        script = r"""
import assert from "node:assert/strict";
import fs from "node:fs";

const source = fs.readFileSync(process.argv.at(-1), "utf8");
const start = source.indexOf("// ---- Seed queue helpers ----");
const end = source.indexOf("// ---- End seed queue helpers ----");
assert.notEqual(start, -1);
assert.notEqual(end, -1);
const helperSource = source.slice(start, end);

const factory = new Function(`
const app = {
  canvas: { setDirty() {} },
  graph: { setDirtyCanvas() {} },
};
const NODE_CLASS = "SmartPromptManager";
const SPM_PRIVACY_FIELD = "spm_data";
const SEED_CONTROL_MODES = ["fixed", "increment", "decrement", "randomize"];
let graphNodesForTest = [];

function graphNodes() {
  return graphNodesForTest;
}

function isSmartPromptManagerNode(node) {
  return node?.type === NODE_CLASS;
}

function widgetByName(node, name) {
  return node?.widgets?.find((widget) => widget?.name === name) || null;
}

function randomSeed() {
  return 987654321;
}

${helperSource}
const SEED_CONTROL_MODES_FOR_TESTS = SEED_CONTROL_MODES;
return {
  SEED_CONTROL_MODES_FOR_TESTS,
  installSpmSeedSerializedSync,
  installSpmSeedControlPersistence,
  liveSeedControlMode,
  normalizeSpmWidgetsValuesForConfigure,
  randomizeSpmSeedsBeforeQueue,
  restoreQueuedSpmSeeds,
  spmSerializedWidgetValues,
  syncSpmSeedSerializedValue,
  syncSpmSerializedWidgetValues,
  setGraphNodesForTest(nodes) { graphNodesForTest = nodes; },
};`);

const SEED_CONTROL_MODES = ["fixed", "increment", "decrement", "randomize"];
const NODE_CLASS = "SmartPromptManager";

const {
  SEED_CONTROL_MODES_FOR_TESTS,
  installSpmSeedSerializedSync,
  installSpmSeedControlPersistence,
  liveSeedControlMode,
  normalizeSpmWidgetsValuesForConfigure,
  randomizeSpmSeedsBeforeQueue,
  restoreQueuedSpmSeeds,
  spmSerializedWidgetValues,
  syncSpmSeedSerializedValue,
  syncSpmSerializedWidgetValues,
  setGraphNodesForTest,
} = factory();

assert.deepEqual(SEED_CONTROL_MODES_FOR_TESTS, SEED_CONTROL_MODES);

function makeNode(mode, options = {}) {
  const seed = options.seed ?? 1234;
  const serializedSeed = options.serializedSeed ?? seed;
  const dataWidget = { name: "spm_data", value: "{}", options: {} };
  const seedWidget = {
    name: "seed",
    value: seed,
    options: {},
    callbackCalls: 0,
    callback(value) {
      this.callbackCalls += 1;
      this.lastCallbackValue = value;
    },
  };
  const rerollWidget = { name: "reroll", value: 0, options: {} };
  const controlWidget = {
    name: options.controlName ?? "control_after_generate",
    value: mode,
    options: {
      values: options.controlValues ?? SEED_CONTROL_MODES,
      serialize: false,
    },
    beforeQueued() {},
    afterQueued() {},
  };
  seedWidget.linkedWidgets = options.linkedWidgets ?? [controlWidget];
  const node = {
    type: NODE_CLASS,
    widgets: [dataWidget, seedWidget, rerollWidget, controlWidget],
    widgets_values: ["{}", serializedSeed, 0],
    last_serialization: { widgets_values: ["{}", serializedSeed, 0] },
    graph: {
      incrementVersion() {},
      setDirtyCanvas() {},
    },
  };
  return { node, seedWidget, controlWidget, seed };
}

{
  const info = { widgets_values: ["{}", 2222, "fixed", 7] };
  normalizeSpmWidgetsValuesForConfigure(info);
  assert.deepEqual(info.widgets_values, ["{}", 2222, 7]);
}

{
  const info = { widgets_values: ["{}", 2222, null, 7] };
  normalizeSpmWidgetsValuesForConfigure(info);
  assert.deepEqual(info.widgets_values, ["{}", 2222, 7]);
}

for (const mode of ["fixed", "increment", "decrement", "bogus", undefined]) {
  const { node, seedWidget, controlWidget, seed } = makeNode(mode, { seed: 2222, serializedSeed: 1111 });
  setGraphNodesForTest([node]);
  const queued = randomizeSpmSeedsBeforeQueue();
  assert.equal(queued.length, 0, `${mode} must not queue an SPM random seed`);
  assert.equal(seedWidget.value, seed, `${mode} must leave the live seed unchanged`);
  assert.equal(node.widgets_values[1], seed, `${mode} must sync serialized seed to live seed`);
  assert.equal(node.last_serialization.widgets_values[1], seed, `${mode} must sync last serialized seed to live seed`);
  assert.equal(controlWidget.serialize, false, `${mode} control must be workflow-runtime only`);
  assert.deepEqual(node.widgets_values, ["{}", seed, 0], `${mode} must use compact SPM widget serialization`);
}

{
  const { node, seedWidget, controlWidget, seed } = makeNode("fixed", { controlName: "fixed", seed: 3333, serializedSeed: 1111 });
  setGraphNodesForTest([node]);
  assert.equal(liveSeedControlMode(node), "fixed");
  assert.equal(randomizeSpmSeedsBeforeQueue().length, 0);
  assert.equal(seedWidget.value, seed);
  assert.equal(node.widgets_values[1], seed);
  assert.equal(node.last_serialization.widgets_values[1], seed);
  assert.equal(controlWidget.serialize, false);
}

{
  const { node, seedWidget } = makeNode("fixed", { seed: 4444, serializedSeed: 1111 });
  assert.equal(syncSpmSeedSerializedValue(node), true);
  assert.equal(node.widgets_values[1], 4444);
  assert.equal(node.last_serialization.widgets_values[1], 4444);
  installSpmSeedSerializedSync(node);
  seedWidget.value = 5555;
  seedWidget.callback(5555);
  assert.equal(seedWidget.callbackCalls, 1);
  assert.equal(node.widgets_values[1], 5555);
  assert.equal(node.last_serialization.widgets_values[1], 5555);
}

{
  const { node, controlWidget } = makeNode("fixed");
  assert.equal(controlWidget.serialize, undefined);
  assert.equal(installSpmSeedControlPersistence(node), controlWidget);
  assert.equal(controlWidget.serialize, false);
  assert.deepEqual(spmSerializedWidgetValues(node, "state"), ["state", 1234, 0]);
  assert.equal(syncSpmSerializedWidgetValues(node), true);
  assert.deepEqual(node.widgets_values, ["{}", 1234, 0]);
}

{
  const { node, seedWidget, controlWidget } = makeNode("randomize");
  const originalBeforeQueued = controlWidget.beforeQueued;
  const originalAfterQueued = controlWidget.afterQueued;
  setGraphNodesForTest([node]);
  const queued = randomizeSpmSeedsBeforeQueue();
  assert.equal(queued.length, 1);
  assert.equal(seedWidget.value, 987654321);
  assert.equal(seedWidget.callbackCalls, 1);
  assert.equal(node.widgets_values[1], 987654321);
  assert.equal(node.last_serialization.widgets_values[1], 987654321);
  assert.equal(node._spmQueuedSeed.seed, 987654321);
  assert.notEqual(controlWidget.beforeQueued, originalBeforeQueued);
  assert.notEqual(controlWidget.afterQueued, originalAfterQueued);
  restoreQueuedSpmSeeds(queued);
  assert.equal(controlWidget.beforeQueued, originalBeforeQueued);
  assert.equal(controlWidget.afterQueued, originalAfterQueued);
}
"""
        subprocess.run(["node", "--input-type=module", "-", str(helper_path)], input=script, text=True, check=True)

    def test_variable_editor_commits_live_rows_before_actions(self):
        source = (ROOT / "web/js/smart_prompt_manager.js").read_text(encoding="utf-8")

        self.assertIn("function readVariableRow(row)", source)
        self.assertIn("function syncVariableRowBindings(row, name)", source)
        self.assertIn("function replaceVariableTokens(oldName, newName)", source)
        self.assertIn("function commitVariableRow(row)", source)
        self.assertIn("function commitVariableRows()", source)
        self.assertIn("const close = () => {\n      commitVariableRows();", source)
        self.assertIn('if (action === "add-variable") {\n        commitVariableRows();', source)
        self.assertIn("const removeName = removeRow?.dataset.varRow || actionButton.dataset.var;", source)
        self.assertNotIn("delete state.variables[event.target.dataset.var]", source)

    def test_graph_to_prompt_replaces_execution_spm_data_with_cache_token(self):
        source = (ROOT / "web/js/smart_prompt_manager.js").read_text(encoding="utf-8")

        self.assertIn('const SPM_CACHE_TOKEN_PREFIX = "spm-cache-v1:";', source)
        self.assertIn("async function sha256Hex(text)", source)
        self.assertIn("function liveSpmExecutionState(node, outputNode = null)", source)
        self.assertIn("async function spmCacheTokenForNode(node, outputNode = null)", source)
        self.assertIn("resolvePrompt(prompt?.text || \"\", state.variables, seed, reroll, state.cycleState).resolved_prompt", source)
        self.assertIn("async function applySpmCacheTokensToPrompt(prompt, graph = defaultGraph())", source)
        self.assertIn("function prepareSpmPrivacyForSerialization(graph = defaultGraph())", source)
        self.assertIn("async function waitForSpmPrivacySaves(graph = defaultGraph())", source)
        self.assertIn("await waitForSpmPrivacySaves(graph);", source)
        self.assertIn("if (spmQueuePromptDepth > 0)", source)
        self.assertIn("node._spmPendingPrivacySave = tracked;", source)
        self.assertIn("const output = prompt?.output;", source)
        self.assertIn("outputNode.inputs.spm_data = token;", source)
        self.assertIn("outputNode.is_changed = token;", source)
        self.assertIn("app.graphToPrompt = wrappedGraphToPrompt", source)
        self.assertIn('scheduleSpmGraphToPromptPatch("setup")', source)
        self.assertNotIn("if (spmQueuePromptDepth <= 0)", source)
        self.assertNotIn("widgets_values[index] = token", source)
        self.assertNotIn("workflow.nodes", source)

    def test_privacy_serialization_hooks_use_stable_envelope_reuse(self):
        source = (ROOT / "web/js/smart_prompt_manager.js").read_text(encoding="utf-8")

        self.assertIn("rememberPrivacyEnvelope(node, SPM_PRIVACY_FIELD, state, initialEncryptedValue)", source)
        self.assertIn("encryptedOrReusePrivacyValue(node, SPM_PRIVACY_FIELD", source)
        self.assertIn("node.onSerialize = function (info)", source)
        self.assertIn("writeSerializedSpmData(info, currentSerializedSpmData())", source)
        self.assertIn("dataWidget.serializeValue = async function", source)
        self.assertIn("node._spmPreparePrivacySerialization = preparePrivacySerialization", source)
        self.assertIn("forgetPrivacyEnvelope(node, SPM_PRIVACY_FIELD)", source)
        self.assertIn("if (!state.privacyMode) {\n      return dataWidget.value;\n    }", source)
        self.assertIn("if (!state.privacyMode) {\n      return Promise.resolve(dataWidget.value);\n    }", source)

    def test_import_export_helpers_package_privacy_and_merge_behaviour(self):
        helper_path = ROOT / "web/js/smart_prompt_manager.js"
        source = helper_path.read_text(encoding="utf-8")
        import_start = source.index("async function importLibraryText(raw, replace)")
        import_end = source.index("async function importLibraryFile(file, replace)", import_start)
        import_library = source[import_start:import_end]

        self.assertIn('const result = await privacyPost("decrypt", { payload: parseJsonObject(imported.spmData) });', import_library)
        self.assertIn("privacyLocked = false;", import_library)
        self.assertIn("rememberPrivacyEnvelope(node, SPM_PRIVACY_FIELD, state, imported.spmData)", import_library)
        self.assertIn("setWidgetRawValue(node, dataWidget, imported.spmData)", import_library)
        self.assertIn("syncSpmSerializedWidgetValues(node, { spmDataValue: imported.spmData, dirty: true })", import_library)
        self.assertIn('status = importStatus("Imported encrypted library", result.warnings);', import_library)
        self.assertIn("Imported encrypted library, but could not decrypt it with the local privacy key", import_library)
        self.assertIn('status = `Error: ${error.message}`;', source)
        self.assertIn('const input = document.createElement("input");', source)
        self.assertIn('input.type = "file";', source)
        self.assertIn('await importLibraryFile(input.files?.[0], replace);', source)
        self.assertNotIn('data-role="import-file"', source)
        self.assertIn('data-library-action="export"', source)
        self.assertIn('data-library-action="merge"', source)
        self.assertIn('data-library-action="replace"', source)
        self.assertNotIn('data-action="export-library"', source)
        self.assertIn("if (isLibraryImportText(raw))", source)
        library_handler_start = source.index("const libraryButton = event.target.closest?.(\"[data-library-action]\");")
        library_handler_end = source.index("const actionButton = event.target.closest?.(\"[data-action]\");", library_handler_start)
        library_handler = source[library_handler_start:library_handler_end]
        self.assertIn("await exportLibraryFile();", library_handler)
        self.assertNotIn("selectedPromptJson", library_handler)
        self.assertNotIn("promptJson", library_handler)

        script = r"""
import assert from "node:assert/strict";
import fs from "node:fs";

const source = fs.readFileSync(process.argv.at(-1), "utf8");
const helperStart = source.indexOf("function nowIso()");
const helperEnd = source.indexOf("// ---- End import/export helpers ----");
const suffixStart = source.indexOf("function suffixName(");
const suffixEnd = source.indexOf("function setWidgetValue", suffixStart);
assert.notEqual(helperStart, -1);
assert.notEqual(helperEnd, -1);
assert.notEqual(suffixStart, -1);
assert.notEqual(suffixEnd, -1);
const helperSource = `${source.slice(helperStart, helperEnd).replace(/^export /gm, "")}\n${source.slice(suffixStart, suffixEnd)}`;

const factory = new Function(`
const VALID_NAME_RE = /^[A-Za-z0-9_-]+$/;
const MODES = ["random", "fixed", "cycle"];
const VIRTUAL_FOLDERS = [
  { id: "all", name: "All" },
  { id: "unsorted", name: "Unsorted" },
  { id: "favorites", name: "Favorites" },
];
const SPM_EXPORT_FORMAT = "comfyui-helto-prompts.smart-prompt-manager.export";
const SPM_EXPORT_VERSION = 1;
let uuidCounter = 0;
const crypto = {
  randomUUID() {
    uuidCounter += 1;
    return \`00000000-0000-0000-0000-\${String(uuidCounter).padStart(12, "0")}\`;
  },
};
${helperSource}
return {
  buildSpmExportPackage,
  isLibraryImportText,
  parseSpmImport,
  mergeImportedLibraryState,
  spmExportFileName,
};`);

const {
  buildSpmExportPackage,
  isLibraryImportText,
  parseSpmImport,
  mergeImportedLibraryState,
  spmExportFileName,
} = factory();

function prompt(id, title, folderId = "folder_current") {
  return {
    id,
    title,
    text: `Prompt ${title}`,
    description: "",
    folderId,
    tags: [],
    favorite: false,
    locked: false,
    hidden: false,
    createdAt: "2026-07-01T00:00:00Z",
    updatedAt: "2026-07-01T00:00:00Z",
  };
}

function variable(values) {
  return { mode: "random", values, fixedValue: null, fallback: "", description: "" };
}

function state(prompts, variables = { mood: variable(["calm"]) }) {
  return {
    version: 1,
    selectedFolderId: "all",
    selectedPromptId: prompts[0]?.id || "",
    search: "",
    privacyMode: false,
    folders: [{ id: "folder_current", name: "Portraits", hidden: false }],
    prompts,
    variables,
    cycleState: { mood: 1 },
    ui: { collapsedSections: {} },
  };
}

function envelope(id) {
  return JSON.stringify({
    version: 1,
    schema: "comfyui-helto-prompts.smart-prompt-manager",
    encrypted: true,
    algorithm: "AES-256-GCM",
    keyId: "test-key",
    nonce: `nonce-${id}`,
    ciphertext: `ciphertext-${id}`,
  }, null, 2);
}

const exportedAt = "2026-07-01T12:34:56Z";
const plaintextState = state([
  prompt("prompt_current", "Cinematic portrait"),
  prompt("prompt_second", "Wide landscape"),
]);
const plaintextPackage = buildSpmExportPackage(plaintextState, false, exportedAt);
assert.equal(plaintextPackage.format, "comfyui-helto-prompts.smart-prompt-manager.export");
assert.equal(plaintextPackage.version, 1);
assert.equal(plaintextPackage.encrypted, false);
assert.equal(plaintextPackage.exportedAt, exportedAt);
assert.equal(plaintextPackage.spm_data.prompts[0].title, "Cinematic portrait");
assert.equal(plaintextPackage.spm_data.prompts[1].title, "Wide landscape");
assert.equal(plaintextPackage.spm_data.prompts.length, 2);
assert.equal(spmExportFileName(exportedAt), "smart-prompt-manager-library-2026-07-01T12-34-56Z.json");

const parsedPlaintext = parseSpmImport(JSON.stringify(plaintextPackage));
assert.equal(parsedPlaintext.encrypted, false);
assert.equal(parsedPlaintext.state.prompts[0].title, "Cinematic portrait");
assert.equal(parsedPlaintext.state.prompts[1].title, "Wide landscape");
assert.equal(parsedPlaintext.state.prompts.length, 2);
assert.equal(isLibraryImportText(JSON.stringify(plaintextPackage)), true);
assert.equal(isLibraryImportText(JSON.stringify(plaintextState)), true);

const singlePromptJson = JSON.stringify({
  version: 1,
  prompt: prompt("prompt_only", "Only one"),
  variables: { mood: variable(["calm"]) },
});
assert.equal(isLibraryImportText(singlePromptJson), false);
assert.equal(isLibraryImportText("not json"), false);
assert.throws(
  () => parseSpmImport(singlePromptJson),
  /single-prompt JSON/,
);

const encryptedEnvelope = envelope("private");
const privatePackage = buildSpmExportPackage(encryptedEnvelope, true, exportedAt);
assert.equal(privatePackage.encrypted, true);
assert.equal(privatePackage.spm_data, encryptedEnvelope);
assert.equal(privatePackage.spm_data.includes("Cinematic portrait"), false);

const parsedEncrypted = parseSpmImport(JSON.stringify(privatePackage));
assert.equal(parsedEncrypted.encrypted, true);
assert.equal(parsedEncrypted.spmData, encryptedEnvelope);
assert.equal(parsedEncrypted.state, null);

const current = state([
  prompt("prompt_current", "Same"),
  prompt("prompt_imported", "Same - imported"),
], { mood: variable(["calm"]) });
const incoming = state([prompt("prompt_incoming", "Same")], {
  mood: variable(["dramatic"]),
  weather: variable(["rain"]),
});
incoming.cycleState.weather = 3;
const merged = mergeImportedLibraryState(current, incoming);
assert.equal(merged.state.prompts.length, 3);
assert.equal(merged.state.prompts[2].title, "Same - imported 2");
assert.notEqual(merged.state.prompts[2].id, "prompt_incoming");
assert.equal(merged.state.prompts[2].folderId, merged.state.folders[1].id);
assert.deepEqual(merged.state.variables.weather.values, ["rain"]);
assert.equal(merged.state.cycleState.weather, 3);
assert.deepEqual(merged.state.variables.mood.values, ["calm"]);
assert.equal(merged.warnings.length, 1);
assert.match(merged.warnings[0], /not overwritten/);
"""
        subprocess.run(["node", "--input-type=module", "-", str(helper_path)], input=script, text=True, check=True)

    def test_privacy_envelope_memo_helper_behaviour(self):
        helper_path = ROOT / "web/js/smart_prompt_manager.js"
        script = r"""
import assert from "node:assert/strict";
import fs from "node:fs";

const source = fs.readFileSync(process.argv[1], "utf8");
const start = source.indexOf("// ---- Privacy envelope memo helpers ----");
const end = source.indexOf("// ---- End privacy envelope memo helpers ----");
assert.notEqual(start, -1);
assert.notEqual(end, -1);
const helperSource = source.slice(start, end).replace(/^export /gm, "");

for (const forbidden of ["localStorage", "sessionStorage", "indexedDB", "caches.open", "document.cookie"]) {
  assert.equal(helperSource.includes(forbidden), false, `${forbidden} must not be used by privacy memo helpers`);
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

const factory = new Function("parseJsonObject", `${helperSource}
return {
  rememberPrivacyEnvelope,
  rememberedPrivacyEnvelope,
  encryptedOrReusePrivacyValue,
  encryptedPrivacyEnvelopeString,
  forgetPrivacyEnvelope,
};`);
const {
  rememberPrivacyEnvelope,
  rememberedPrivacyEnvelope,
  encryptedOrReusePrivacyValue,
  encryptedPrivacyEnvelopeString,
  forgetPrivacyEnvelope,
} = factory(parseJsonObject);

function envelope(id) {
  return JSON.stringify({
    version: 1,
    schema: "comfyui-helto-prompts.smart-prompt-manager",
    encrypted: true,
    algorithm: "AES-256-GCM",
    keyId: "test-key",
    nonce: `nonce-${id}`,
    ciphertext: `ciphertext-${id}`,
  }, null, 2);
}

const owner = {};
const originalEnvelope = envelope("original");
rememberPrivacyEnvelope(owner, "spm_data", { b: 2, a: 1 }, originalEnvelope);
assert.equal(rememberedPrivacyEnvelope(owner, "spm_data", { a: 1, b: 2 }), originalEnvelope);

let calls = 0;
const reused = await encryptedOrReusePrivacyValue(owner, "spm_data", { a: 1, b: 2 }, async () => {
  calls += 1;
  return envelope("unexpected");
});
assert.equal(reused, originalEnvelope);
assert.equal(calls, 0);

const changedEnvelope = envelope("changed");
const changed = await encryptedOrReusePrivacyValue(owner, "spm_data", { a: 1, b: 3 }, async () => {
  calls += 1;
  return changedEnvelope;
});
assert.equal(changed, changedEnvelope);
assert.equal(calls, 1);

const changedAgain = await encryptedOrReusePrivacyValue(owner, "spm_data", { b: 3, a: 1 }, async () => {
  calls += 1;
  return envelope("changed-again");
});
assert.equal(changedAgain, changedEnvelope);
assert.equal(calls, 1);

const concurrentOwner = {};
calls = 0;
const [one, two] = await Promise.all([
  encryptedOrReusePrivacyValue(concurrentOwner, "spm_data", { value: "same" }, async () => {
    calls += 1;
    await new Promise((resolve) => setTimeout(resolve, 5));
    return envelope("concurrent");
  }),
  encryptedOrReusePrivacyValue(concurrentOwner, "spm_data", { value: "same" }, async () => {
    calls += 1;
    return envelope("concurrent-other");
  }),
]);
assert.equal(one, envelope("concurrent"));
assert.equal(two, envelope("concurrent"));
assert.equal(calls, 1);

calls = 0;
const currentEnvelope = envelope("current");
const passthrough = await encryptedOrReusePrivacyValue({}, "spm_data", currentEnvelope, async () => {
  calls += 1;
  return envelope("bad");
});
assert.equal(passthrough, currentEnvelope);
assert.equal(calls, 0);
assert.equal(encryptedPrivacyEnvelopeString(JSON.parse(currentEnvelope)), currentEnvelope);

forgetPrivacyEnvelope(owner, "spm_data");
const afterForget = await encryptedOrReusePrivacyValue(owner, "spm_data", { a: 1, b: 3 }, async () => {
  calls += 1;
  return envelope("after-forget");
});
assert.equal(afterForget, envelope("after-forget"));
assert.equal(calls, 1);
"""
        subprocess.run(
            ["node", "--input-type=module", "-e", script, str(helper_path)],
            check=True,
            cwd=ROOT,
            text=True,
            capture_output=True,
        )


if __name__ == "__main__":
    unittest.main()
