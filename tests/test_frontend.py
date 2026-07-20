from pathlib import Path
import subprocess
import tempfile
import unittest

import helto_privacy


ROOT = Path(__file__).resolve().parents[1]
HELTO_PRIVACY_UI = Path(helto_privacy.__file__).resolve().parent / "web" / "privacy_ui.js"
HELTO_PRIVACY_UI_SOURCE = HELTO_PRIVACY_UI.read_text(encoding="utf-8") if HELTO_PRIVACY_UI.is_file() else ""
HAS_PRIVACY_RECOVERY_UI = "registerPrivacyRecoveryDescriptors" in HELTO_PRIVACY_UI_SOURCE


def run_node_script(script, *paths):
    subprocess.run(
        ["node", "--input-type=module", "-", *(str(path) for path in paths)],
        input=script,
        text=True,
        check=True,
    )


class SmartPromptManagerFrontendTests(unittest.TestCase):
    def test_vue_widget_sizing_is_stable_and_does_not_feed_back_node_height(self):
        source = (ROOT / "web/js/smart_prompt_manager.js").read_text(encoding="utf-8")

        self.assertIn("delete uiWidget.computeLayoutSize;", source)
        self.assertIn("uiWidget.getMinHeight = () => PANEL_MIN_HEIGHT;", source)
        self.assertIn("uiWidget.getMaxHeight = undefined;", source)
        self.assertIn("uiWidget.getHeight = () => PANEL_DEFAULT_HEIGHT;", source)
        self.assertIn("delete uiWidget.options.getMaxHeight;", source)
        self.assertIn('widgetFrame.style.height = vueLayout ? "100%"', source)
        self.assertIn('widgetFrame.style.maxHeight = vueLayout ? "none"', source)
        self.assertIn('root.style.height = vueLayout ? "100%"', source)
        self.assertNotIn("uiWidget.getMinHeight = () => panelHeight();", source)
        self.assertNotIn("uiWidget.getMaxHeight = () => panelHeight();", source)

    def test_seed_frontend_randomizes_live_seed_before_queue(self):
        source = (ROOT / "web/js/smart_prompt_manager.js").read_text(encoding="utf-8")

        self.assertIn("const SEED_MAX = 1125899906842624;", source)
        self.assertIn("Math.floor(randomUnit53() * (SEED_MAX - 1)) + 1", source)
        self.assertIn("// ---- Seed queue helpers ----", source)
        self.assertIn("function installSpmSeedQueueLifecycle(node)", source)
        self.assertIn('liveSeedControlMode(node) !== "randomize"', source)
        self.assertIn("delete node._spmQueuedSeed;", source)
        self.assertIn("writeSpmSeedValue(node, seed)", source)
        self.assertIn("target.beforeQueued = function", source)
        self.assertIn("target.afterQueued = function", source)
        self.assertNotIn("app.queuePrompt = wrappedQueuePrompt", source)

    def test_seed_queue_helpers_only_randomize_explicit_randomize_mode(self):
        helper_path = ROOT / "web/js/smart_prompt_manager.js"
        script = r"""
import assert from "node:assert/strict";
import fs from "node:fs";

const source = fs.readFileSync(process.argv.at(-1), "utf8");
const randomStart = source.indexOf("function randomSeed()");
const randomEnd = source.indexOf("function widgetByName", randomStart);
assert.notEqual(randomStart, -1);
assert.notEqual(randomEnd, -1);
const randomSeedSource = source.slice(randomStart, randomEnd);
const randomFactory = new Function(`
const SEED_MAX = 1125899906842624;
let unit = 0;
function randomUnit53() {
  return unit;
}
${randomSeedSource}
return {
  randomSeed,
  setUnit(value) {
    unit = value;
  },
};`);
const random = randomFactory();
random.setUnit(0);
assert.equal(random.randomSeed(), 1);
random.setUnit(1 - Number.EPSILON);
assert.equal(random.randomSeed(), 1125899906842623);

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
const SPM_SEED_QUEUE_LIFECYCLE_KEY = "__smartPromptManagerSeedQueueLifecycle";
const SPM_SEED_QUEUE_ACTIVE_KEY = "__smartPromptManagerActiveQueuedSeed";
const SPM_SEED_QUEUE_MAX_AGE_MS = 10000;
let spmQueuePromptDepth = 0;
let spmQueuePromptDeadline = 0;
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
  clearQueuedSeedUnlessRandomize,
  installSpmSeedSerializedSync,
  installSpmSeedControlPersistence,
  installSpmSeedQueueLifecycle,
  liveSeedControlMode,
  normalizeSpmWidgetsValuesForConfigure,
  spmQueuePromptActive,
  spmSerializedWidgetValues,
  syncSpmSeedSerializedValue,
  syncSpmSerializedWidgetValues,
  setGraphNodesForTest(nodes) { graphNodesForTest = nodes; },
};`);

const SEED_CONTROL_MODES = ["fixed", "increment", "decrement", "randomize"];
const NODE_CLASS = "SmartPromptManager";

const {
  SEED_CONTROL_MODES_FOR_TESTS,
  clearQueuedSeedUnlessRandomize,
  installSpmSeedSerializedSync,
  installSpmSeedControlPersistence,
  installSpmSeedQueueLifecycle,
  liveSeedControlMode,
  normalizeSpmWidgetsValuesForConfigure,
  spmQueuePromptActive,
  spmSerializedWidgetValues,
  syncSpmSeedSerializedValue,
  syncSpmSerializedWidgetValues,
  setGraphNodesForTest,
} = factory();

assert.deepEqual(SEED_CONTROL_MODES_FOR_TESTS, SEED_CONTROL_MODES);

function makeNode(mode, options = {}) {
  const seed = options.seed ?? 1234;
  const serializedSeed = options.serializedSeed ?? seed;
  const reroll = options.reroll ?? 0;
  const serializedReroll = options.serializedReroll ?? reroll;
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
  const rerollWidget = { name: "reroll", value: reroll, options: {} };
  const controlWidget = {
    name: options.controlName ?? "control_after_generate",
    value: mode,
    callbackCalls: 0,
    callback(value) {
      this.callbackCalls += 1;
      this.lastCallbackValue = value;
    },
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
    widgets_values: ["{}", serializedSeed, serializedReroll],
    last_serialization: { widgets_values: ["{}", serializedSeed, serializedReroll] },
    graph: {
      incrementVersion() {},
      setDirtyCanvas() {},
    },
  };
  return { node, seedWidget, rerollWidget, controlWidget, seed, reroll };
}

{
  const info = { widgets_values: ["{}", 2222, "fixed", 7] };
  normalizeSpmWidgetsValuesForConfigure(info);
  assert.deepEqual(info.widgets_values, ["{}", 2222, 7]);
  const { node, seedWidget, rerollWidget } = makeNode("fixed", { seed: info.widgets_values[1], reroll: info.widgets_values[2] });
  syncSpmSerializedWidgetValues(node);
  assert.equal(seedWidget.value, 2222);
  assert.equal(rerollWidget.value, 7);
  assert.deepEqual(node.widgets_values, ["{}", 2222, 7]);
}

{
  const info = { widgets_values: ["{}", 2222, null, 7] };
  normalizeSpmWidgetsValuesForConfigure(info);
  assert.deepEqual(info.widgets_values, ["{}", 2222, 7]);
}

{
  const info = { widgets_values: ["{}", 1357, 11] };
  normalizeSpmWidgetsValuesForConfigure(info);
  assert.deepEqual(info.widgets_values, ["{}", 1357, 11]);
  const { node, seedWidget, rerollWidget } = makeNode("fixed", { seed: info.widgets_values[1], reroll: info.widgets_values[2] });
  syncSpmSerializedWidgetValues(node);
  assert.equal(seedWidget.value, 1357);
  assert.equal(rerollWidget.value, 11);
  assert.deepEqual(node.widgets_values, ["{}", 1357, 11]);
}

for (const mode of ["fixed", "increment", "decrement", "bogus", undefined]) {
  const { node, seedWidget, controlWidget, seed } = makeNode(mode, { seed: 2222, serializedSeed: 1111 });
  node._spmQueuedSeed = { seed: 987654321, at: Date.now() };
  installSpmSeedControlPersistence(node);
  assert.equal(installSpmSeedQueueLifecycle(node), true);
  controlWidget.beforeQueued();
  assert.equal(spmQueuePromptActive(), true);
  assert.equal(node._spmQueuedSeed, undefined, `${mode} must clear stale queued random seed state`);
  assert.equal(seedWidget.value, seed, `${mode} must leave the live seed unchanged`);
  assert.equal(node.widgets_values[1], seed, `${mode} must sync serialized seed to live seed`);
  assert.equal(node.last_serialization.widgets_values[1], seed, `${mode} must sync last serialized seed to live seed`);
  assert.equal(controlWidget.serialize, false, `${mode} control must be workflow-runtime only`);
  assert.deepEqual(node.widgets_values, ["{}", seed, 0], `${mode} must use compact SPM widget serialization`);
  controlWidget.afterQueued();
  assert.equal(spmQueuePromptActive(), false);
}

{
  const { node, seedWidget, controlWidget, seed } = makeNode("fixed", { controlName: "fixed", seed: 3333, serializedSeed: 1111 });
  installSpmSeedControlPersistence(node);
  installSpmSeedQueueLifecycle(node);
  assert.equal(liveSeedControlMode(node), "fixed");
  controlWidget.beforeQueued();
  assert.equal(seedWidget.value, seed);
  assert.equal(node.widgets_values[1], seed);
  assert.equal(node.last_serialization.widgets_values[1], seed);
  assert.equal(controlWidget.serialize, false);
  controlWidget.afterQueued();
}

{
  const { node } = makeNode("fixed");
  node._spmQueuedSeed = { seed: 9999, at: Date.now() };
  clearQueuedSeedUnlessRandomize(node);
  assert.equal(node._spmQueuedSeed, undefined);
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
  assert.equal(installSpmSeedQueueLifecycle(node), true);
  const installedBeforeQueued = controlWidget.beforeQueued;
  const installedAfterQueued = controlWidget.afterQueued;
  assert.equal(installSpmSeedQueueLifecycle(node), true);
  assert.equal(controlWidget.beforeQueued, installedBeforeQueued);
  assert.equal(controlWidget.afterQueued, installedAfterQueued);
  controlWidget.beforeQueued();
  assert.equal(spmQueuePromptActive(), true);
  assert.equal(seedWidget.value, 987654321);
  assert.equal(seedWidget.callbackCalls, 1);
  assert.equal(node.widgets_values[1], 987654321);
  assert.equal(node.last_serialization.widgets_values[1], 987654321);
  assert.equal(node._spmQueuedSeed.seed, 987654321);
  assert.notEqual(controlWidget.beforeQueued, originalBeforeQueued);
  assert.notEqual(controlWidget.afterQueued, originalAfterQueued);
  seedWidget.value = 1;
  controlWidget.afterQueued();
  assert.equal(seedWidget.value, 987654321);
  assert.equal(spmQueuePromptActive(), false);
}

{
  const { node, seedWidget, controlWidget } = makeNode("fixed", { seed: 1010, reroll: 2 });
  installSpmSeedSerializedSync(node);
  installSpmSeedControlPersistence(node);
  controlWidget.value = "randomize";
  controlWidget.callback("randomize");
  installSpmSeedQueueLifecycle(node);
  controlWidget.beforeQueued();
  assert.equal(seedWidget.value, 987654321);
  controlWidget.afterQueued();
  assert.equal(node._spmQueuedSeed.seed, 987654321);

  controlWidget.value = "fixed";
  controlWidget.callback("fixed");
  assert.equal(node._spmQueuedSeed, undefined);
  seedWidget.value = 2468;
  seedWidget.callback(2468);
  controlWidget.beforeQueued();
  assert.equal(seedWidget.value, 2468);
  assert.deepEqual(node.widgets_values, ["{}", 2468, 2]);
  controlWidget.afterQueued();
}
"""
        run_node_script(script, helper_path)

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

    def test_cycle_resolution_wraps_negative_imported_state(self):
        helper_path = ROOT / "web/js/smart_prompt_manager.js"
        script = r"""
import assert from "node:assert/strict";
import fs from "node:fs";

const source = fs.readFileSync(process.argv.at(-1), "utf8");
const start = source.indexOf("function selectVariableValue");
const end = source.indexOf("function resolvePrompt", start);
assert.notEqual(start, -1);
assert.notEqual(end, -1);
const helperSource = source.slice(start, end);

const factory = new Function(`
const MODES = ["random", "fixed", "cycle"];
function normalizeValues(value) { return value; }
${helperSource}
return { selectVariableValue };
`);

const { selectVariableValue } = factory();
const selected = selectVariableValue(
  "cycle",
  { mode: "cycle", values: ["one", "two", "three"] },
  0,
  0,
  { cycle: -1 },
  [],
);
assert.equal(selected, "three");
"""
        run_node_script(script, helper_path)

    def test_graph_to_prompt_replaces_execution_spm_data_with_cache_token(self):
        source = (ROOT / "web/js/smart_prompt_manager.js").read_text(encoding="utf-8")

        self.assertIn('const SPM_CACHE_TOKEN_PREFIX = "spm-cache-v1:";', source)
        self.assertIn("async function sha256Hex(text)", source)
        self.assertIn("function liveSpmExecutionState(node, outputNode = null)", source)
        self.assertIn("async function spmCacheTokenForNode(node, outputNode = null)", source)
        self.assertIn("function spmExecutionCacheIdentity(state)", source)
        self.assertIn("canonicalPrivacyPlaintext(spmExecutionCacheIdentity(state))", source)
        self.assertIn("async function applySpmCacheTokensToPrompt(prompt, graph = defaultGraph())", source)
        self.assertIn("function prepareSpmPrivacyForSerialization(graph = defaultGraph())", source)
        self.assertIn("async function waitForSpmPrivacySaves(graph = defaultGraph())", source)
        self.assertIn("await waitForSpmPrivacySaves(graph);", source)
        self.assertIn("if (spmQueuePromptActive())", source)
        self.assertIn("node._spmPendingPrivacySave = tracked;", source)
        self.assertIn("const output = prompt?.output;", source)
        self.assertIn("outputNode.inputs.spm_data = token;", source)
        self.assertIn("outputNode.is_changed = token;", source)
        self.assertIn("app.graphToPrompt = wrappedGraphToPrompt", source)
        self.assertIn('scheduleSpmGraphToPromptPatch("setup")', source)
        self.assertNotIn("widgets_values[index] = token", source)
        self.assertNotIn("workflow.nodes", source)

        script = r"""
import assert from "node:assert/strict";
import fs from "node:fs";

const source = fs.readFileSync(process.argv.at(-1), "utf8");
const start = source.indexOf("function liveSpmExecutionState");
const end = source.indexOf("function prepareSpmPrivacyForSerialization", start);
assert.notEqual(start, -1);
assert.notEqual(end, -1);
const helperSource = source.slice(start, end);

const factory = new Function(`
const SPM_CACHE_TOKEN_PREFIX = "spm-cache-v1:";
const SPM_PRIVACY_FIELD = "spm_data";

function widgetByName(node, name) {
  return node?.widgets?.find((widget) => widget?.name === name) || null;
}

function normalizeState(value) {
  return value;
}

function parseState(value) {
  return JSON.parse(value);
}

function isAnyEncryptedStateValue() {
  return false;
}

function canonicalPrivacyPlaintext(value) {
  return JSON.stringify(value);
}

async function sha256Hex(text) {
  return String(text);
}

${helperSource}
return { spmCacheTokenForNode };
`);

const { spmCacheTokenForNode } = factory();
const state = {
  selectedPromptId: "prompt1",
  selectedFolderId: "all",
  folders: [],
  prompts: [{ id: "prompt1", title: "Title A", text: "A {{mood}} portrait" }],
  variables: { mood: { mode: "random", values: ["calm", "stormy"] } },
  cycleState: {},
};
const node = {
  widgets: [
    { name: "spm_data", value: JSON.stringify(state) },
    { name: "seed", value: 9999 },
    { name: "reroll", value: 5 },
  ],
};

const token = await spmCacheTokenForNode(node, { inputs: { spm_data: "ignored", seed: 1234, reroll: 7 } });
assert.match(token, /^spm-cache-v1:/);

const fallbackToken = await spmCacheTokenForNode(node, { inputs: { spm_data: "ignored" } });
assert.equal(fallbackToken, token, "live widget seed changes are represented by literal queued inputs, not duplicated in spm_data");

const titleChangedState = structuredClone(state);
titleChangedState.prompts[0].title = "Title B";
const titleChangedNode = {
  ...node,
  widgets: node.widgets.map((widget) => widget.name === "spm_data"
    ? { ...widget, value: JSON.stringify(titleChangedState) }
    : { ...widget }),
};
const titleChangedToken = await spmCacheTokenForNode(titleChangedNode, { inputs: { seed: 1234, reroll: 7 } });
assert.notEqual(titleChangedToken, token, "prompt_name changes must invalidate the whole-node cache entry");

const searchChangedState = structuredClone(state);
searchChangedState.search = "visual-only filter";
const searchChangedNode = {
  ...node,
  widgets: node.widgets.map((widget) => widget.name === "spm_data"
    ? { ...widget, value: JSON.stringify(searchChangedState) }
    : { ...widget }),
};
const searchChangedToken = await spmCacheTokenForNode(searchChangedNode, { inputs: { seed: 1234, reroll: 7 } });
assert.equal(searchChangedToken, token, "visual search state must stay cache-neutral");
"""
        run_node_script(script, ROOT / "web/js/smart_prompt_manager.js")

    def test_privacy_serialization_hooks_use_stable_envelope_reuse(self):
        source = (ROOT / "web/js/smart_prompt_manager.js").read_text(encoding="utf-8")

        self.assertIn("rememberPrivacyEnvelope(node, SPM_PRIVACY_FIELD, state, envelopeString)", source)
        self.assertIn("encryptedOrReusePrivacyValue(node, SPM_PRIVACY_FIELD", source)
        self.assertIn("privacy.ensureEncryptedPrivacyValue", source)
        self.assertIn("Privacy encryption is required before Smart Prompt Manager can serialize private prompt data.", source)
        self.assertIn("node.onSerialize = function (info)", source)
        self.assertIn("writeSerializedSpmData(info, currentSerializedSpmData())", source)
        self.assertIn("dataWidget.serializeValue = async function", source)
        self.assertIn("node._spmPreparePrivacySerialization = preparePrivacySerialization", source)
        self.assertIn("forgetPrivacyEnvelope(node, SPM_PRIVACY_FIELD)", source)
        self.assertIn("if (!state.privacyMode) {\n      return dataWidget.value;\n    }", source)
        self.assertIn("if (!state.privacyMode) {\n      return Promise.resolve(dataWidget.value);\n    }", source)
        self.assertIn('const SPM_PRIVACY_SCHEMA = "helto.smart-prompt-manager";', source)
        self.assertIn('const SPM_LEGACY_PRIVACY_SCHEMA = "comfyui-helto-prompts.smart-prompt-manager";', source)
        self.assertIn('const HELTO_PRIVACY_MODULE_ROUTE = "/helto_privacy/ui/privacy.js";', source)
        self.assertIn('const HELTO_PRIVACY_TOKEN_HEADER = "X-Helto-Privacy-Token";', source)
        self.assertIn("spmSharedPrivacyModulePromise = import(HELTO_PRIVACY_MODULE_ROUTE).catch(() => null);", source)
        self.assertIn('privacy.showPrivacyKeystoreDialog("auto")', source)
        self.assertIn("const token = privacy?.getStoredPrivacyToken?.();", source)
        self.assertIn("if (token) headers[HELTO_PRIVACY_TOKEN_HEADER] = token;", source)
        self.assertIn('!(endpoint === "decrypt" && isSharedPrivacySetupError(error))', source)
        self.assertIn("await isUnreadablePrivacyValueError(error)", source)
        self.assertIn("await confirmUnreadablePrivacyReset()", source)
        self.assertIn("The encrypted value was preserved.", source)
        self.assertIn("Unreadable private prompt library was reset to defaults.", source)
        self.assertIn('const SPM_PRIVACY_RECOVERY_SOURCE = "comfyui-helto-smartprompt";', source)
        self.assertIn("privacy.registerPrivacyRecoveryDescriptors(SPM_PRIVACY_RECOVERY_SOURCE", source)
        self.assertIn("spmLockedPrivacyRecoveryDescriptor", source)
        self.assertIn("locked-current-envelope", source)
        self.assertIn("_spmPrivacyRecoveryLocked", source)
        self.assertIn('name: SPM_PRIVACY_FIELD', source)
        self.assertIn('label: "Prompt library"', source)
        self.assertIn("showPrivacyRecoveryDialog", source)
        self.assertIn('data-action="privacy-recovery"', source)
        self.assertIn('data-action="reset-private-data"', source)
        self.assertIn("initialUnsupportedEncryptedValue", source)
        self.assertIn("unsupportedPrivacyEnvelopeString(dataWidget.value)", source)
        self.assertIn("unsupportedPrivacyEnvelopeDescription", source)
        self.assertNotIn(
            "if (initialUnsupportedEncryptedValue) {\n    dataWidget.value = serializedDefaultState();",
            source,
        )

    def test_privacy_encryption_failure_blocks_queue_serialization(self):
        helper_path = ROOT / "web/js/smart_prompt_manager.js"
        script = r"""
import assert from "node:assert/strict";
import fs from "node:fs";

const source = fs.readFileSync(process.argv.at(-1), "utf8");
const start = source.indexOf("function prepareSpmPrivacyForSerialization");
const end = source.indexOf("function installSpmGraphToPromptPatch", start);
assert.notEqual(start, -1);
assert.notEqual(end, -1);
const helperSource = source.slice(start, end);

let graphNodesForTest = [];
function graphNodes() {
  return graphNodesForTest;
}

const factory = new Function("graphNodes", `
${helperSource}
return { waitForSpmPrivacySaves };
`);
const { waitForSpmPrivacySaves } = factory(graphNodes);
graphNodesForTest = [{
  _spmPreparePrivacySerialization() {
    return Promise.reject(new Error("synthetic encryption failure"));
  },
}];

await assert.rejects(
  () => waitForSpmPrivacySaves({}),
  /synthetic encryption failure/,
);
"""
        run_node_script(script, helper_path)

        source = helper_path.read_text(encoding="utf-8")
        self.assertNotIn("if (existingEnvelope) return existingEnvelope;", source)

    def test_unknown_encrypted_schema_stays_locked_for_recovery(self):
        helper_path = ROOT / "web/js/smart_prompt_manager.js"
        script = r"""
import assert from "node:assert/strict";
import fs from "node:fs";

const source = fs.readFileSync(process.argv.at(-1), "utf8");
const start = source.indexOf("function parseJsonObject");
const end = source.indexOf("function clonePlain", start);
assert.notEqual(start, -1);
assert.notEqual(end, -1);
const helperSource = source.slice(start, end);

const factory = new Function(`
const SPM_PRIVACY_SCHEMA = "helto.smart-prompt-manager";
const SPM_LEGACY_PRIVACY_SCHEMA = "comfyui-helto-prompts.smart-prompt-manager";
${helperSource}
return { isAnyEncryptedStateValue, isUnsupportedEncryptedStateValue };
`);

const { isAnyEncryptedStateValue, isUnsupportedEncryptedStateValue } = factory();
const futureEnvelope = {
  version: 2,
  schema: "future.smart-prompt-manager",
  encrypted: true,
  algorithm: "AES-256-GCM",
  keyId: "future-key",
  nonce: "nonce",
  ciphertext: "ciphertext",
};
assert.equal(isAnyEncryptedStateValue(futureEnvelope), true);
assert.equal(isUnsupportedEncryptedStateValue(futureEnvelope), true);
assert.equal(isAnyEncryptedStateValue({ prompts: [] }), false);
"""
        run_node_script(script, helper_path)

    def test_helto_design_system_tokens_and_component_roles(self):
        source = (ROOT / "web/js/smart_prompt_manager.js").read_text(encoding="utf-8")

        for token in [
            "--helto-bg: #181825;",
            "--helto-surface: #1e1e2e;",
            "--helto-surface-2: #313244;",
            "--helto-surface-3: #45475a;",
            "--helto-surface-hover: #585b70;",
            "--helto-accent: #fab387;",
            "--helto-accent-strong: #fddcc4;",
            "--helto-accent-border: #93664a;",
            "--helto-focus: #89b4fa;",
            "--helto-focus-ring: 0 0 0 3px rgba(137, 180, 250, 0.28);",
            "--helto-danger: #f38ba8;",
            "--helto-danger-border: #96526a;",
            "--helto-font-size: 12px;",
            "--helto-line: 1.4;",
        ]:
            self.assertIn(token, source)

        for old_palette_value in [
            "#0d1320",
            "#151c2a",
            "#1b2333",
            "#f1c75c",
            "#5e9bff",
            "rgba(241,199,92",
            "#4f4322",
            "#3c3318",
            "#5a2330",
            "#471b25",
        ]:
            self.assertNotIn(old_palette_value, source)

        self.assertIn(".spm-btn-primary,.spm-btn.is-active{border-color:var(--helto-accent-border);background:linear-gradient(180deg,#4f3a2a,#3d2d20);", source)
        self.assertIn(".spm-btn-danger{border-color:var(--helto-danger-border);background:linear-gradient(180deg,#5c2c3d,#482331);", source)
        self.assertIn(".spm-switch input:checked+.spm-switch-slider{background:var(--helto-accent-bg);border-color:var(--helto-accent-border)}", source)
        self.assertIn(".spm-root input:not([type=checkbox]):focus", source)
        self.assertIn(".spm-modal-backdrop{position:fixed;inset:0;z-index:9999;background:rgba(17,17,27,.72);", source)
        self.assertIn(".spm-root,.spm-modal,.spm-prompt-list,.spm-preview,.spm-autocomplete{scrollbar-width:thin;scrollbar-color:rgba(137,180,250,.45) transparent}", source)

    def test_helto_design_system_styles_actual_litegraph_node(self):
        source = (ROOT / "web/js/smart_prompt_manager.js").read_text(encoding="utf-8")

        for snippet in [
            'const SPM_WIDGET_THEME_BRIDGE_KEY = "__spmHeltoLiteGraphWidgetThemeBridgeInstalled";',
            'const SPM_WIDGET_THEME_FALLBACK_KEY = "__spmHeltoLiteGraphWidgetThemeFallbackInstalled";',
            'const SPM_WIDGET_THEME_SNAPSHOT_KEY = "__spmHeltoLiteGraphWidgetThemeSnapshot";',
            "const SPM_HELTO = {",
            "WIDGET_BGCOLOR: SPM_HELTO.bg,",
            "WIDGET_OUTLINE_COLOR: SPM_HELTO.borderStrong,",
            "WIDGET_PROMOTED_OUTLINE_COLOR: SPM_HELTO.accent,",
            "WIDGET_ADVANCED_OUTLINE_COLOR: SPM_HELTO.focus,",
            "function installSpmWidgetThemeBridge()",
            "function ensureSpmWidgetThemeFallback(node)",
            "function applySpmNodeTheme(node)",
            "function patchSpmNodeTheme(nodeType)",
            "node.color = SPM_HELTO.surface3;",
            "node.bgcolor = SPM_HELTO.surface;",
        ]:
            self.assertIn(snippet, source)

        bridge_start = source.index("function installSpmWidgetThemeBridge()")
        bridge_end = source.index("function ensureSpmWidgetThemeFallback(node)", bridge_start)
        bridge_block = source[bridge_start:bridge_end]
        self.assertIn("prototype.drawNodeWidgets = function (node)", bridge_block)
        self.assertIn("if (isSmartPromptManagerNode(node))", bridge_block)
        self.assertIn("withSpmLiteGraphWidgetTheme(() => originalDrawNodeWidgets.apply(this, arguments))", bridge_block)
        self.assertIn("return originalDrawNodeWidgets.apply(this, arguments);", bridge_block)

        fallback_start = source.index("function ensureSpmWidgetThemeFallback(node)")
        fallback_end = source.index("function applySpmNodeTheme(node)", fallback_start)
        fallback_block = source[fallback_start:fallback_end]
        self.assertIn("node.onDrawBackground = function ()", fallback_block)
        self.assertIn("applySpmLiteGraphWidgetTheme()", fallback_block)
        self.assertIn("node.onDrawForeground = function ()", fallback_block)
        self.assertIn("restoreSpmLiteGraphWidgetTheme", fallback_block)

        apply_start = source.index("function applySpmNodeTheme(node)")
        apply_end = source.index("function patchSpmNodeTheme(nodeType)", apply_start)
        apply_block = source[apply_start:apply_end]
        self.assertIn("if (!isSmartPromptManagerNode(node)) return false;", apply_block)
        self.assertIn("ensureSpmWidgetThemeFallback(node)", apply_block)
        self.assertIn("node.setDirtyCanvas?.(true, true);", apply_block)
        self.assertIn("node.graph?.setDirtyCanvas?.(true, true);", apply_block)

        self.assertIn("installSpmWidgetThemeBridge();", source)
        self.assertIn("for (const node of graphNodes())", source)
        self.assertIn("applySpmNodeTheme(this);", source)
        self.assertIn("nodeCreated(node) {", source)
        self.assertIn("loadedGraphNode(node) {", source)

    def test_helto_dialog_layout_classes_preserve_hidden_preview_contract(self):
        source = (ROOT / "web/js/smart_prompt_manager.js").read_text(encoding="utf-8")

        for class_snippet in [
            'class="spm-row spm-prompt-dialog-layout"',
            'class="spm-prompt-dialog-sidebar"',
            'class="spm-prompt-dialog-content"',
            'class="spm-prompt-list spm-list-tall"',
            'class="spm-prompt-list spm-list-short"',
            'class="spm-autocomplete spm-autocomplete-dialog"',
            'class="spm-muted spm-empty-list"',
            'class="spm-folder-name"',
        ]:
            self.assertIn(class_snippet, source)

        self.assertNotIn('style="', source)
        self.assertIn('const previewPlaceholder = \'<span class="spm-muted">Preview hidden. Hover over the node to reveal it.</span>\';', source)
        self.assertIn("Hidden prompt. Hover over the node to reveal it.", source)
        self.assertIn("const revealSelectedPreview = !selectedPreviewHidden || previewRevealActive;", source)
        self.assertIn("const revealItem = !itemHidden || previewRevealActive;", source)

    def test_dialog_event_delegation_uses_current_controls(self):
        source = (ROOT / "web/js/smart_prompt_manager.js").read_text(encoding="utf-8")

        prompt_dialog_start = source.index("function openPromptDialog()")
        prompt_dialog_end = source.index("function openVariablesDialog()", prompt_dialog_start)
        prompt_dialog = source[prompt_dialog_start:prompt_dialog_end]
        self.assertIn('const editor = modal.querySelector(".spm-dialog-editor");', prompt_dialog)
        self.assertIn('const popup = modal.querySelector("[data-dialog-autocomplete]");', prompt_dialog)
        self.assertIn("if (event.target !== editor) return;", prompt_dialog)

        folder_dialog_start = source.index("function openFoldersDialog()")
        folder_dialog_end = source.index("function renderUi()", folder_dialog_start)
        folder_dialog = source[folder_dialog_start:folder_dialog_end]
        self.assertIn('const actionButton = event.target.closest?.("[data-dialog-action]");', folder_dialog)
        self.assertIn("const action = actionButton?.dataset.dialogAction;", folder_dialog)
        self.assertIn("const folderId = actionButton.dataset.folder;", folder_dialog)
        self.assertNotIn("const folderId = event.target.dataset.folder;", folder_dialog)

    @unittest.skipUnless(HAS_PRIVACY_RECOVERY_UI, "helto-privacy 0.3.0 recovery UI is required")
    def test_shared_privacy_recovery_contract_for_smart_prompt_fields(self):
        script = r"""
import assert from "node:assert/strict";
import * as privacy from "./privacy_ui.mjs";

const SPM_SCHEMA = "helto.smart-prompt-manager";
const LEGACY_SCHEMA = "comfyui-helto-prompts.smart-prompt-manager";
const DEFAULT_STATE = JSON.stringify({ version: 1, privacyMode: false, prompts: [] });

function envelope(schema, id = schema) {
  return JSON.stringify({
    version: 1,
    encrypted: true,
    algorithm: "AES-256-GCM",
    schema,
    keyId: `key-${id}`,
    nonce: `nonce-${id}`,
    ciphertext: `ciphertext-${id}`,
  });
}

function node(id, value, privacyMode = true) {
  return {
    id,
    type: "SmartPromptManager",
    title: `Smart ${id}`,
    properties: { spmPrivacyMode: privacyMode },
    widgets: [{ name: "spm_data", value }],
    widgets_values: [value, 0, 0],
    setDirtyCanvas() { this.dirty = true; },
  };
}

function lockedNode(id, value) {
  const result = node(id, value, true);
  result._spmPrivacyRecoveryLocked = true;
  return result;
}

let capturedPlaintext = "";
privacy.registerPrivacyRecoveryDescriptors("comfyui-helto-smartprompt", [{
  id: "smart-prompt-normal",
  nodeType: "SmartPromptManager",
  label: "Smart Prompt Manager",
  schema: SPM_SCHEMA,
  privacy: { property: "spmPrivacyMode", default: false },
  fields: [{
    kind: "widget",
    name: "spm_data",
    label: "Prompt library",
    schema: SPM_SCHEMA,
    defaultValue: DEFAULT_STATE,
    sensitive: true,
    resetOnlyForLegacy: true,
    runtimeProperty: "_spmExecutionState",
  }],
  reencrypt: async (plaintext) => {
    capturedPlaintext = plaintext;
    return envelope(SPM_SCHEMA, "reencrypted");
  },
}, {
  id: "smart-prompt-locked-current-envelope",
  label: "Smart Prompt Manager locked library",
  schema: SPM_SCHEMA,
  match: (candidate) => (
    candidate?.type === "SmartPromptManager"
    && Boolean(candidate?._spmPrivacyRecoveryLocked)
    && Boolean(candidate?.widgets?.find((item) => item.name === "spm_data")?.value)
  ),
  privacy: { property: "spmPrivacyMode", default: true },
  fields: [{
    kind: "widget",
    name: "spm_data",
    label: "Locked prompt library",
    schema: SPM_SCHEMA,
    defaultValue: DEFAULT_STATE,
    sensitive: true,
    resetOnlyForLegacy: true,
    runtimeProperty: "_spmExecutionState",
    acceptsEnvelope: () => false,
  }],
}]);

const valid = node(1, envelope(SPM_SCHEMA, "valid"));
const wrong = node(2, envelope("wrong.schema", "wrong"));
const legacy = node(3, envelope(LEGACY_SCHEMA, "legacy"));
const oldPrefix = node(4, "__HELTO_ENC__:SECRET_PROMPT_TEXT");
const plaintext = node(5, JSON.stringify({ privacyMode: true, prompts: [{ text: "VERY_SECRET_PROMPT" }] }));
const publicPlaintext = node(6, JSON.stringify({ privacyMode: false, prompts: [{ text: "public" }] }), false);
const lockedCurrent = lockedNode(7, envelope(SPM_SCHEMA, "locked-current"));
const graph = { nodes: [valid, wrong, legacy, oldPrefix, plaintext, publicPlaintext, lockedCurrent] };

const issues = privacy.scanPrivacyRecoveryIssues(graph);
assert.equal(issues.some((issue) => issue.nodeId === 1), false);
assert.equal(issues.some((issue) => issue.nodeId === 6), false);
assert.deepEqual(
  issues.map((issue) => [issue.nodeId, issue.type]).sort(),
  [
    [2, "invalid_encrypted_value"],
    [3, "invalid_encrypted_value"],
    [4, "legacy_encrypted_value"],
    [5, "plaintext_sensitive_value"],
    [7, "invalid_encrypted_value"],
  ],
);

const publicModel = JSON.stringify(privacy.buildPrivacyRecoveryDialogModel(issues));
assert(!publicModel.includes("VERY_SECRET_PROMPT"));
assert(!publicModel.includes("SECRET_PROMPT_TEXT"));

const resetResult = await privacy.recoverPrivacyIssues({
  action: "reset",
  graph,
  issues: issues.filter((issue) => [2, 3, 4, 7].includes(issue.nodeId)),
});
assert.equal(resetResult.ok, true);
assert.equal(wrong.widgets[0].value, DEFAULT_STATE);
assert.equal(legacy.widgets[0].value, DEFAULT_STATE);
assert.equal(oldPrefix.widgets[0].value, DEFAULT_STATE);
assert.equal(lockedCurrent.widgets[0].value, DEFAULT_STATE);

const reencryptResult = await privacy.recoverPrivacyIssues({
  action: "reencrypt",
  graph,
  issues: issues.filter((issue) => issue.nodeId === 5),
});
assert.equal(reencryptResult.ok, true);
assert(capturedPlaintext.includes("VERY_SECRET_PROMPT"));
assert.equal(JSON.parse(plaintext.widgets[0].value).schema, SPM_SCHEMA);
assert.equal(plaintext.dirty, true);
"""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            (tmp_path / "privacy_ui.mjs").write_text(HELTO_PRIVACY_UI_SOURCE, encoding="utf-8")
            script_path = tmp_path / "test.mjs"
            script_path.write_text(script, encoding="utf-8")
            result = subprocess.run(
                ["node", str(script_path)],
                cwd=tmp_path,
                text=True,
                capture_output=True,
                check=False,
            )
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)

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
        self.assertIn("Imported encrypted library, but could not decrypt it with the shared privacy keystore", import_library)
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
const SPM_PRIVACY_SCHEMA = "helto.smart-prompt-manager";
const SPM_LEGACY_PRIVACY_SCHEMA = "comfyui-helto-prompts.smart-prompt-manager";
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

const SPM_PRIVACY_SCHEMA_FOR_TEST = "helto.smart-prompt-manager";
const SPM_LEGACY_PRIVACY_SCHEMA_FOR_TEST = "comfyui-helto-prompts.smart-prompt-manager";

function envelope(id, schema = SPM_PRIVACY_SCHEMA_FOR_TEST) {
  return JSON.stringify({
    version: 1,
    schema,
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

const poisonedVariableLibrary = {
  ...plaintextState,
  seed: 1125899906842624,
  reroll: 99,
  control_after_generate: "randomize",
  widgets_values: ["{}", 1125899906842624, "randomize", 99],
  last_serialization: { widgets_values: ["{}", 1125899906842624, "randomize", 99] },
};
const parsedPoisoned = parseSpmImport(JSON.stringify(poisonedVariableLibrary));
assert.equal(parsedPoisoned.encrypted, false);
assert.equal(parsedPoisoned.state.prompts.length, 2);
assert.deepEqual(parsedPoisoned.state.variables.mood.values, ["calm"]);
assert.equal(Object.hasOwn(parsedPoisoned.state, "seed"), false);
assert.equal(Object.hasOwn(parsedPoisoned.state, "reroll"), false);
assert.equal(Object.hasOwn(parsedPoisoned.state, "widgets_values"), false);
assert.equal(Object.hasOwn(parsedPoisoned.state, "last_serialization"), false);
assert.equal(Object.hasOwn(parsedPoisoned.state, "control_after_generate"), false);

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
assert.throws(
  () => parseSpmImport(envelope("legacy", SPM_LEGACY_PRIVACY_SCHEMA_FOR_TEST)),
  /unsupported legacy privacy schema/,
);
assert.throws(
  () => parseSpmImport(envelope("future", "future.smart-prompt-manager")),
  /unsupported encrypted privacy schema or algorithm/,
);
assert.throws(
  () => parseSpmImport(JSON.stringify({ ...privatePackage, spm_data: envelope("legacy-export", SPM_LEGACY_PRIVACY_SCHEMA_FOR_TEST) })),
  /unsupported legacy privacy schema/,
);

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
        run_node_script(script, helper_path)

    def test_plaintext_library_replace_preserves_destination_privacy_mode(self):
        helper_path = ROOT / "web/js/smart_prompt_manager.js"
        script = r"""
import assert from "node:assert/strict";
import fs from "node:fs";

const source = fs.readFileSync(process.argv.at(-1), "utf8");
const start = source.indexOf("async function importLibraryText(raw, replace)");
const end = source.indexOf("async function importLibraryFile", start);
assert.notEqual(start, -1);
assert.notEqual(end, -1);
const helperSource = source.slice(start, end);

const factory = new Function(`
const SPM_PRIVACY_FIELD = "spm_data";
let state = { privacyMode: true, prompts: [{ id: "current" }] };
let saveCount = 0;
const node = {};
const dataWidget = {};
function parseSpmImport() {
  return { encrypted: false, state: { privacyMode: false, prompts: [{ id: "imported" }] } };
}
function forgetPrivacyEnvelope() {}
function save() { saveCount += 1; }
${helperSource}
return {
  importLibraryText,
  getState: () => state,
  getSaveCount: () => saveCount,
};
`);

const replacement = factory();
await replacement.importLibraryText("{}", true);
assert.equal(replacement.getState().privacyMode, true);
assert.equal(replacement.getState().prompts[0].id, "imported");
assert.equal(replacement.getSaveCount(), 1);
"""
        run_node_script(script, helper_path)

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

const factory = new Function("parseJsonObject", `
const SPM_PRIVACY_SCHEMA = "helto.smart-prompt-manager";
const SPM_LEGACY_PRIVACY_SCHEMA = "comfyui-helto-prompts.smart-prompt-manager";
${helperSource}
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

const SPM_PRIVACY_SCHEMA = "helto.smart-prompt-manager";
const SPM_LEGACY_PRIVACY_SCHEMA = "comfyui-helto-prompts.smart-prompt-manager";

function envelope(id, schema = SPM_PRIVACY_SCHEMA) {
  return JSON.stringify({
    version: 1,
    schema,
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
assert.equal(encryptedPrivacyEnvelopeString(JSON.parse(envelope("legacy", SPM_LEGACY_PRIVACY_SCHEMA))), "");

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
