from pathlib import Path
import subprocess
import tempfile
import unittest

import helto_privacy


ROOT = Path(__file__).resolve().parents[1]
HELTO_PRIVACY_WEB = Path(helto_privacy.__file__).resolve().parent / "web"
HELTO_PRIVACY_UI = HELTO_PRIVACY_WEB / "privacy_ui.js"
HELTO_PRIVACY_UI_SOURCE = HELTO_PRIVACY_UI.read_text(encoding="utf-8") if HELTO_PRIVACY_UI.is_file() else ""
HELTO_PRIVACY_UI_DEPENDENCIES = {
    name: (HELTO_PRIVACY_WEB / name).read_text(encoding="utf-8")
    for name in (
        "privacy_client.js",
        "privacy_records.js",
        "privacy_artifacts.js",
    )
    if (HELTO_PRIVACY_WEB / name).is_file()
}
HAS_PRIVACY_RECOVERY_UI = (
    "registerPrivacyRecoveryDescriptors" in HELTO_PRIVACY_UI_SOURCE
    and len(HELTO_PRIVACY_UI_DEPENDENCIES) == 3
)


def run_node_script(script, *paths):
    subprocess.run(
        ["node", "--input-type=module", "-", *(str(path) for path in paths)],
        input=script,
        text=True,
        check=True,
    )


class SmartPromptManagerFrontendTests(unittest.TestCase):
    def test_seed_frontend_randomizes_live_seed_before_queue(self):
        source = (ROOT / "web/js/smart_prompt_manager.js").read_text(encoding="utf-8")

        self.assertIn("const SEED_MAX = 1125899906842624;", source)
        self.assertIn("Math.floor(randomUnit53() * (SEED_MAX - 1)) + 1", source)
        self.assertIn("// ---- Seed queue helpers ----", source)
        self.assertIn("function randomizeSpmSeedsBeforeQueue()", source)
        self.assertIn('liveSeedControlMode(node) !== "randomize"', source)
        self.assertIn("delete node._spmQueuedSeed;", source)
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
  clearQueuedSeedUnlessRandomize,
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
  setGraphNodesForTest([node]);
  const queued = randomizeSpmSeedsBeforeQueue();
  assert.equal(queued.length, 0, `${mode} must not queue an SPM random seed`);
  assert.equal(node._spmQueuedSeed, undefined, `${mode} must clear stale queued random seed state`);
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

{
  const { node, seedWidget, controlWidget } = makeNode("fixed", { seed: 1010, reroll: 2 });
  installSpmSeedSerializedSync(node);
  installSpmSeedControlPersistence(node);
  controlWidget.value = "randomize";
  controlWidget.callback("randomize");
  setGraphNodesForTest([node]);
  const queued = randomizeSpmSeedsBeforeQueue();
  assert.equal(queued.length, 1);
  assert.equal(seedWidget.value, 987654321);
  restoreQueuedSpmSeeds(queued);
  assert.equal(node._spmQueuedSeed.seed, 987654321);

  controlWidget.value = "fixed";
  controlWidget.callback("fixed");
  assert.equal(node._spmQueuedSeed, undefined);
  seedWidget.value = 2468;
  seedWidget.callback(2468);
  setGraphNodesForTest([node]);
  const fixedQueued = randomizeSpmSeedsBeforeQueue();
  assert.equal(fixedQueued.length, 0);
  assert.equal(seedWidget.value, 2468);
  assert.deepEqual(node.widgets_values, ["{}", 2468, 2]);
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

    def test_shared_gate_owns_execution_submission(self):
        source = (ROOT / "web/js/smart_prompt_manager.js").read_text(encoding="utf-8")

        self.assertIn('from "./smart_prompt_managed_privacy.js";', source)
        self.assertIn("registerSmartPromptManagedOwner(node, managedProductBridge())", source)
        self.assertNotIn("SPM_CACHE_TOKEN_PREFIX", source)
        self.assertNotIn("installSpmGraphToPromptPatch", source)
        self.assertNotIn("app.graphToPrompt = wrappedGraphToPrompt", source)
    def test_shared_pack_owns_privacy_serialization(self):
        source = (ROOT / "web/js/smart_prompt_manager.js").read_text(encoding="utf-8")

        managed = (ROOT / "web/js/smart_prompt_managed_privacy.js").read_text(encoding="utf-8")
        self.assertIn('fetch("/helto_privacy/status", { cache: "no-store" })', managed)
        self.assertIn("runtime.connectPrivacyPack({", managed)
        self.assertIn("profileFingerprint: SMART_PROMPT_PROFILE_FINGERPRINT", managed)
        self.assertIn("writeWorkflowProjection", source)
        self.assertIn("coordinator.flushEditor(node)", source)
        for retired in (
            "dataWidget.serializeValue = async function",
            "node.onSerialize = function",
            "getStoredPrivacyToken",
            "privacy.registerPrivacyRecoveryDescriptors",
            "_spmPendingPrivacySave",
        ):
            self.assertNotIn(retired, source)
    def test_blocked_suite_conceals_and_rejects_local_fallback(self):
        source = (ROOT / "web/js/smart_prompt_manager.js").read_text(encoding="utf-8")
        managed = (ROOT / "web/js/smart_prompt_managed_privacy.js").read_text(encoding="utf-8")
        self.assertIn("Privacy installation blocked:", source)
        self.assertIn("Prompt data stays concealed until the installation is active.", source)
        self.assertIn('suite?.suiteStatus !== "active"', managed)
        self.assertIn("connectionPromise = null;", managed)
        self.assertNotIn("prepareSpmPrivacyForSerialization", source)
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
        self.assertIn(
            "return Boolean(state.privacyMode || prompt.hidden || folderById(state, prompt.folderId)?.hidden);",
            source,
        )

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
            (tmp_path / "package.json").write_text(
                '{"type":"module"}',
                encoding="utf-8",
            )
            for name, source in HELTO_PRIVACY_UI_DEPENDENCIES.items():
                (tmp_path / name).write_text(source, encoding="utf-8")
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

    def test_import_export_delegates_to_managed_operations(self):
        helper_path = ROOT / "web/js/smart_prompt_manager.js"
        source = helper_path.read_text(encoding="utf-8")
        import_start = source.index("async function importLibraryText(raw, replace)")
        import_end = source.index("async function importLibraryFile(file, replace)", import_start)
        import_library = source[import_start:import_end]

        self.assertIn("await coordinator.importReplace(node, raw)", import_library)
        self.assertIn("await coordinator.importMerge(node, raw)", import_library)
        self.assertNotIn("privacyPost(", import_library)
        self.assertNotIn("setWidgetRawValue", import_library)
        self.assertIn('const input = document.createElement("input");', source)
        self.assertIn('input.type = "file";', source)
        self.assertIn('await importLibraryFile(input.files?.[0], replace);', source)
    def test_import_replace_and_merge_use_distinct_managed_operations(self):
        source = (ROOT / "web/js/smart_prompt_manager.js").read_text(encoding="utf-8")
        start = source.index("async function importLibraryText(raw, replace)")
        end = source.index("async function importLibraryFile(file, replace)", start)
        live = source[start:end]
        self.assertIn("replace\n      ? await coordinator.importReplace(node, raw)", live)
        self.assertIn(": await coordinator.importMerge(node, raw);", live)
        self.assertNotIn("destinationPrivacyMode", live)
    def test_local_envelope_memo_is_removed(self):
        source = (ROOT / "web/js/smart_prompt_manager.js").read_text(encoding="utf-8")
        managed = (ROOT / "web/js/smart_prompt_managed_privacy.js").read_text(encoding="utf-8")
        self.assertNotIn("SPM_PRIVACY_MEMOS", source)
        self.assertNotIn("encryptedOrReusePrivacyValue", source)
        self.assertNotIn("rememberPrivacyEnvelope", source)
        self.assertIn("connectPrivacyPack", managed)
