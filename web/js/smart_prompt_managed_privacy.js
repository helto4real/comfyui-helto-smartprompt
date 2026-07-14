import { app } from "../../scripts/app.js";

import {
  SMART_PROMPT_MODE_BROWSER_ADAPTER_ID,
  SMART_PROMPT_WORKFLOW_BROWSER_ADAPTER_ID,
  createSmartPromptModeBrowserAdapter,
  createSmartPromptWorkflowBrowserAdapter,
} from "./smart_prompt_privacy_adapters.js";
import { createSmartPromptPrivacyCoordinator } from "./smart_prompt_privacy_coordinator.js";

export const SMART_PROMPT_PROFILE_ID = "helto.smart-prompt-manager";
export const SMART_PROMPT_PROFILE_FINGERPRINT = "5a352fd3fb086cd3418039368457e7a2fbd8b4ae81aa0deae6151d8bcbd22352";

const MODE_RESOURCE_ID = "prompt-library-mode";
const WORKFLOW_RESOURCE_ID = "prompt-library-workflow";
const EXECUTION_RESOURCE_ID = "prompt-library-execution";
const INSTALLATION_BLOCKED = "PRIVACY_SMART_PROMPT_INSTALLATION_BLOCKED";
const BRIDGE_PROPERTY = "__smartPromptManagedProductBridge";
const REQUIRED_NODE_METHODS = Object.freeze([
  "readModeMirror",
  "writeModeMirror",
  "captureEditorState",
  "normalizeEditorState",
  "applyEditorState",
  "clearEditorState",
  "readProtectedState",
  "writeProtectedState",
  "writeWorkflowProjection",
  "flushEditorState",
  "captureImportState",
  "applyImportResult",
  "commitImportState",
  "restoreImportState",
  "readDestinationPrivate",
  "downloadExport",
  "writeExecutionInputs",
  "clearExecutionInputs",
  "reconcileNode",
  "onPrivacySessionChange",
]);

const owners = new Set();
let connectionPromise = null;

function blocked() {
  throw new Error(INSTALLATION_BLOCKED);
}

function nodeBridge(owner) {
  const bridge = owner?.[BRIDGE_PROPERTY];
  if (!bridge || typeof bridge !== "object") blocked();
  return bridge;
}

function dispatch(owner, method, ...args) {
  const candidate = nodeBridge(owner)?.[method];
  if (typeof candidate !== "function") blocked();
  return candidate.call(nodeBridge(owner), owner, ...args);
}

function dispatchAll(method, ...args) {
  for (const owner of [...owners]) {
    if (owner?.[BRIDGE_PROPERTY]) dispatch(owner, method, ...args);
    else owners.delete(owner);
  }
}

const productBridge = Object.freeze({
  readModeMirror: (owner, property) => dispatch(owner, "readModeMirror", property),
  writeModeMirror: (owner, property, value) => dispatch(owner, "writeModeMirror", property, value),
  captureEditorState: (owner, context) => dispatch(owner, "captureEditorState", context),
  normalizeEditorState: (owner, value, context) => (
    dispatch(owner, "normalizeEditorState", value, context)
  ),
  applyEditorState: (owner, value, context) => dispatch(owner, "applyEditorState", value, context),
  clearEditorState: (owner, context) => dispatch(owner, "clearEditorState", context),
  readProtectedState: (owner, context) => dispatch(owner, "readProtectedState", context),
  writeProtectedState: (owner, value, context) => dispatch(owner, "writeProtectedState", value, context),
  writeWorkflowProjection: (owner, serializedNode, value, context) => (
    dispatch(owner, "writeWorkflowProjection", serializedNode, value, context)
  ),
  flushEditorState: (owner) => dispatch(owner, "flushEditorState"),
  captureImportState: (owner, operationId) => dispatch(owner, "captureImportState", operationId),
  applyImportResult: (owner, result, operationId) => dispatch(owner, "applyImportResult", result, operationId),
  commitImportState: (owner, boundary, operationId) => dispatch(owner, "commitImportState", boundary, operationId),
  restoreImportState: (owner, boundary, operationId) => dispatch(owner, "restoreImportState", boundary, operationId),
  readDestinationPrivate: (owner) => dispatch(owner, "readDestinationPrivate"),
  downloadExport: (owner, payload) => dispatch(owner, "downloadExport", payload),
  exportedAt: () => new Date().toISOString().replace(/\.\d{3}Z$/, "Z"),
  writeExecutionInputs: (owner, prepared) => dispatch(owner, "writeExecutionInputs", prepared),
  clearExecutionInputs: () => dispatchAll("clearExecutionInputs"),
  reconcileNode: (owner) => dispatch(owner, "reconcileNode"),
  reconcileNodeDefinition() {},
  onPrivacySessionChange: (snapshot) => dispatchAll("onPrivacySessionChange", snapshot),
});

export function registerSmartPromptManagedOwner(owner, bridge) {
  if (!owner || typeof owner !== "object" || owner.id === undefined
      || !bridge || typeof bridge !== "object"
      || REQUIRED_NODE_METHODS.some((method) => typeof bridge[method] !== "function")) {
    blocked();
  }
  owner[BRIDGE_PROPERTY] = bridge;
  owners.add(owner);
  return () => {
    owners.delete(owner);
    if (owner[BRIDGE_PROPERTY] === bridge) delete owner[BRIDGE_PROPERTY];
  };
}

async function connect() {
  const response = await fetch("/helto_privacy/status", { cache: "no-store" });
  if (!response.ok) blocked();
  const suite = await response.json();
  if (suite?.ok !== true || suite?.suiteStatus !== "active"
      || !/^[0-9a-f]{64}$/.test(String(suite?.suiteManifestDigest || ""))) {
    blocked();
  }
  const runtime = await import(
    `/helto_privacy/ui/privacy_profile/${suite.suiteManifestDigest}.js`
  );
  if (typeof runtime.connectPrivacyPack !== "function" || !runtime.PRIVACY_CONTRACT_V3) blocked();
  const browserAdapters = {};
  const pack = await runtime.connectPrivacyPack({
    app,
    packId: SMART_PROMPT_PROFILE_ID,
    contract: runtime.PRIVACY_CONTRACT_V3,
    profileFingerprint: SMART_PROMPT_PROFILE_FINGERPRINT,
    suiteManifestDigest: suite.suiteManifestDigest,
    adapterFactories: {
      [SMART_PROMPT_MODE_BROWSER_ADAPTER_ID]: () => {
        const adapter = createSmartPromptModeBrowserAdapter({ productBridge });
        browserAdapters[SMART_PROMPT_MODE_BROWSER_ADAPTER_ID] = adapter;
        return adapter;
      },
      [SMART_PROMPT_WORKFLOW_BROWSER_ADAPTER_ID]: ({ handle }) => {
        const adapter = createSmartPromptWorkflowBrowserAdapter({
          productBridge,
          workflowHandle: handle,
          app,
        });
        browserAdapters[SMART_PROMPT_WORKFLOW_BROWSER_ADAPTER_ID] = adapter;
        return adapter;
      },
    },
  });
  const coordinator = createSmartPromptPrivacyCoordinator({
    workflowHandle: pack.workflow(WORKFLOW_RESOURCE_ID),
    modeHandle: pack.mode(MODE_RESOURCE_ID),
    executionHandle: pack.execution(EXECUTION_RESOURCE_ID),
    productBridge,
    browserAdapters,
    app,
  });
  return Object.freeze({ pack, coordinator });
}

export function smartPromptManagedPrivacy() {
  connectionPromise ??= connect().catch((error) => {
    connectionPromise = null;
    throw error;
  });
  return connectionPromise;
}
