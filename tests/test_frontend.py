from pathlib import Path
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]


class SmartPromptManagerFrontendTests(unittest.TestCase):
    def test_seed_frontend_randomizes_live_seed_before_queue(self):
        source = (ROOT / "web/js/smart_prompt_manager.js").read_text(encoding="utf-8")

        self.assertIn("const SEED_MAX = Number.MAX_SAFE_INTEGER;", source)
        self.assertIn("function randomizeSpmSeedsBeforeQueue()", source)
        self.assertIn('liveSeedControlMode(node) !== "randomize"', source)
        self.assertIn("writeSpmSeedValue(node, seed)", source)
        self.assertIn("suspendSeedControlCallbacks(controlWidget)", source)
        self.assertIn("restoreQueuedSpmSeeds(queuedSeeds)", source)
        self.assertIn("app.queuePrompt = wrappedQueuePrompt", source)
        self.assertIn('scheduleSpmSeedQueuePatch("setup")', source)
        self.assertIn("spmQueuePromptDepth += 1;", source)
        self.assertIn("spmQueuePromptDepth = Math.max(0, spmQueuePromptDepth - 1);", source)

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
