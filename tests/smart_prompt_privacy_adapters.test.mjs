import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

import {
  SMART_PROMPT_PRIVACY_FIELD_ID,
  SMART_PROMPT_PRIVACY_MODE_PROPERTY,
  SMART_PROMPT_PRIVACY_WIDGET,
  createSmartPromptModeBrowserAdapter,
  createSmartPromptWorkflowBrowserAdapter,
} from "../web/js/smart_prompt_privacy_adapters.js";


const context = {
  fieldId: SMART_PROMPT_PRIVACY_FIELD_ID,
  location: { name: SMART_PROMPT_PRIVACY_WIDGET },
};


function productBridge() {
  return {
    flushes: 0,
    readModeMirror(node, property) {
      return node.mode?.[property];
    },
    writeModeMirror(node, property, value) {
      node.mode ||= {};
      if (value === undefined) delete node.mode[property];
      else node.mode[property] = value;
    },
    captureEditorState(node) {
      return structuredClone(node.editor);
    },
    normalizeEditorState(_owner, value) {
      return {
        version: 1,
        privacyMode: value?.privacyMode !== false,
        prompts: Array.isArray(value?.prompts) ? value.prompts : [],
      };
    },
    applyEditorState(node, value) {
      node.editor = structuredClone(value);
    },
    clearEditorState(node) {
      node.editor = null;
    },
    readProtectedState(node) {
      return node.protected;
    },
    writeProtectedState(node, value) {
      node.protected = value;
    },
    writeWorkflowProjection(_node, serializedNode, value) {
      serializedNode.widgets_values[0] = value;
    },
    flushEditorState() {
      this.flushes += 1;
    },
    reconcileNode(node) {
      node.reconciled = true;
    },
    reconcileNodeDefinition(nodeType) {
      this.definition = nodeType;
    },
    onPrivacySessionChange(snapshot) {
      this.session = snapshot?.state;
    },
  };
}


test("mode adapter mirrors only through the injected product bridge", () => {
  const bridge = productBridge();
  const adapter = createSmartPromptModeBrowserAdapter({ productBridge: bridge });
  const node = { mode: {} };

  assert.equal(adapter.readDeclaredMode(node), "inherit");
  node.mode[SMART_PROMPT_PRIVACY_MODE_PROPERTY] = "malformed";
  assert.equal(adapter.readDeclaredMode(node), "inherit");
  adapter.writeDeclaredMode(node, "private");
  assert.equal(node.mode[SMART_PROMPT_PRIVACY_MODE_PROPERTY], true);
  assert.equal(adapter.readDeclaredMode(node), "private");
  adapter.writeDeclaredMode(node, "public");
  assert.equal(node.mode[SMART_PROMPT_PRIVACY_MODE_PROPERTY], false);
  assert.equal(adapter.readDeclaredMode(node), "public");
  adapter.writeDeclaredMode(node, "inherit");
  assert.equal(SMART_PROMPT_PRIVACY_MODE_PROPERTY in node.mode, false);
});


test("workflow transition freezes edits and proves exact detached recovery", async () => {
  const bridge = productBridge();
  const node = {
    id: 41,
    type: "SmartPromptManager",
    widgets: [{ name: SMART_PROMPT_PRIVACY_WIDGET, value: "unused" }],
    editor: { version: 1, privacyMode: true, prompts: [{ id: "private" }] },
    protected: JSON.stringify({
      version: 1,
      schema: "helto.smart-prompt-manager",
      encrypted: true,
      algorithm: "AES-256-GCM",
      keyId: "synthetic-key",
      nonce: "synthetic-nonce",
      ciphertext: "synthetic-ciphertext",
    }),
  };
  const graph = {
    _nodes: [node],
    serialize() {
      return {
        nodes: [{
          id: node.id,
          type: node.type,
          widgets_values: [node.protected],
        }],
      };
    },
  };
  node.graph = graph;
  let settlements = 0;
  let marked = 0;
  const adapter = createSmartPromptWorkflowBrowserAdapter({
    productBridge: bridge,
    workflowHandle: {
      markEdited(owner, fieldId) {
        assert.equal(owner, node);
        assert.equal(fieldId, SMART_PROMPT_PRIVACY_FIELD_ID);
        marked += 1;
      },
      async settle(reason) {
        assert.equal(reason, "mode-transition");
        settlements += 1;
      },
    },
    app: { graph },
  });
  const transitionContext = {
    field: {
      id: SMART_PROMPT_PRIVACY_FIELD_ID,
      nodeTypes: ["SmartPromptManager"],
      location: { kind: "widget", name: SMART_PROMPT_PRIVACY_WIDGET },
      externalTransitionPolicy: {
        maxOwners: 16,
        maxOriginalBytesPerOwner: 1024 * 1024,
        maxTargetBytesPerOwner: 1024 * 1024,
      },
    },
  };
  const original = node.protected;
  adapter.reconcileNode(node);
  for (const method of [
    "settleModeTransition",
    "inventoryModeTransitionOwners",
    "readModeTransitionOwnerExact",
    "applyModeTransitionOwnerExact",
    "extractDetachedModeTransitionOwnerExact",
    "restoreModeTransitionOwnerExact",
    "reloadModeTransitionRuntime",
    "reconcileModeTransitionRuntime",
  ]) {
    assert.equal(typeof adapter[method], "function", method);
  }

  const settlement = adapter.settleModeTransition(transitionContext);
  assert.deepEqual(await settlement.settled, { offlineRepresentationCount: 0 });
  assert.equal(bridge.flushes, 1);
  assert.equal(marked, 1);
  assert.equal(settlements, 1);
  assert.equal(node.__smartPromptManagedPrivacyTransitionFrozen, true);
  assert.throws(
    () => adapter.writeProtected(node, "blocked", context),
    /PRIVACY_SMART_PROMPT_ADAPTER_INVALID/,
  );

  const [inventory] = adapter.inventoryModeTransitionOwners(transitionContext);
  assert.deepEqual(
    {
      rootGraphId: inventory.rootGraphId,
      graphId: inventory.graphId,
      nodeId: inventory.nodeId,
    },
    { rootGraphId: "root", graphId: "root", nodeId: "41" },
  );
  assert.equal(
    Buffer.from(adapter.readModeTransitionOwnerExact(
      inventory.owner,
      transitionContext,
    )).toString(),
    original,
  );

  const publicExact = new TextEncoder().encode(JSON.stringify({
    version: 1,
    privacyMode: false,
    prompts: [{ id: "public" }],
  }));
  adapter.applyModeTransitionOwnerExact(
    inventory.owner,
    publicExact,
    transitionContext,
  );
  assert.deepEqual(
    adapter.readModeTransitionOwnerExact(inventory.owner, transitionContext),
    publicExact,
  );
  assert.deepEqual(
    adapter.extractDetachedModeTransitionOwnerExact(
      inventory.owner,
      graph.serialize(),
      transitionContext,
    ),
    publicExact,
  );
  adapter.reloadModeTransitionRuntime(inventory.owner, transitionContext);
  assert.deepEqual(node.editor, {
    version: 1,
    privacyMode: false,
    prompts: [{ id: "public" }],
  });
  adapter.reconcileModeTransitionRuntime(inventory.owner, transitionContext);

  adapter.restoreModeTransitionOwnerExact(
    inventory.owner,
    new TextEncoder().encode(original),
    transitionContext,
  );
  adapter.readModeTransitionOwnerExact(inventory.owner, transitionContext);
  adapter.reloadModeTransitionRuntime(inventory.owner, transitionContext);
  assert.equal(node.editor, null);
  adapter.reconcileModeTransitionRuntime(inventory.owner, transitionContext);
  await settlement.release();
  assert.equal(node.__smartPromptManagedPrivacyTransitionFrozen, false);
});


test("revealed apply and clear preserve locked ciphertext byte for byte", () => {
  const bridge = productBridge();
  const adapter = createSmartPromptWorkflowBrowserAdapter({ productBridge: bridge });
  const original = "{ \"ciphertext\" : \"LOCKED_SYNTHETIC_BYTES\" }\n";
  const node = {
    editor: { version: 1, privacyMode: true, prompts: [{ id: "one" }] },
    protected: original,
  };

  adapter.writeProtected(node, original, context);
  adapter.apply(
    node,
    { version: 1, privacyMode: true, prompts: [{ id: "revealed" }] },
    context,
  );
  assert.deepEqual(adapter.normalize(node, context), {
    version: 1,
    privacyMode: true,
    prompts: [{ id: "revealed" }],
  });
  assert.equal(adapter.readProtected(node, context), original);
  assert.equal(node.protected, original);

  adapter.clear(node, context);
  assert.equal(node.editor, null);
  assert.equal(adapter.readProtected(node, context), original);
  assert.equal(node.protected, original);

  const serialized = { widgets_values: ["old", 1, 0] };
  adapter.writeWorkflowProjection(node, serialized, original, context);
  assert.equal(serialized.widgets_values[0], original);
});


test("workflow adapter rejects missing bridges and malformed product results", () => {
  assert.throws(
    () => createSmartPromptWorkflowBrowserAdapter({ productBridge: {} }),
    /PRIVACY_SMART_PROMPT_ADAPTER_INVALID/,
  );
  const bridge = productBridge();
  bridge.normalizeEditorState = () => "plaintext string";
  const adapter = createSmartPromptWorkflowBrowserAdapter({ productBridge: bridge });
  assert.throws(
    () => adapter.normalize({ editor: {} }, context),
    /PRIVACY_SMART_PROMPT_ADAPTER_INVALID/,
  );
});


test("managed adapter has no loader, network, crypto, or live import side effects", () => {
  const source = fs.readFileSync(
    new URL("../web/js/smart_prompt_privacy_adapters.js", import.meta.url),
    "utf8",
  );
  const live = fs.readFileSync(
    new URL("../web/js/smart_prompt_manager.js", import.meta.url),
    "utf8",
  );
  const packageInit = fs.readFileSync(new URL("../__init__.py", import.meta.url), "utf8");

  for (const forbidden of [
    "registerExtension(",
    "app.registerExtension",
    "fetch(",
    "privacyPost(",
    "crypto.subtle",
    "import(",
    "/helto_privacy/",
  ]) {
    assert.equal(source.includes(forbidden), false, `forbidden live behavior: ${forbidden}`);
  }
  assert.equal(live.includes("smart_prompt_privacy_adapters.js"), false);
  assert.equal(packageInit.includes("managed_privacy"), false);
});
