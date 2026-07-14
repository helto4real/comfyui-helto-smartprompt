// Browser adapters for the shared Smart Prompt privacy profile. Product/editor
// ownership is injected through a bridge; the managed connector registers them.

import { createSmartPromptExternalWorkflowTransition } from "./smart_prompt_managed_mode_transition.js";

export const SMART_PROMPT_PRIVACY_NODE_TYPE = "SmartPromptManager";
export const SMART_PROMPT_PRIVACY_FIELD_ID = "prompt-library-state";
export const SMART_PROMPT_PRIVACY_WIDGET = "spm_data";
export const SMART_PROMPT_PRIVACY_MODE_PROPERTY = "spmPrivacyMode";
export const SMART_PROMPT_PRIVACY_SCOPE_ID = "prompt-library";
export const SMART_PROMPT_MODE_BROWSER_ADAPTER_ID = "prompt-library-mode-browser";
export const SMART_PROMPT_WORKFLOW_BROWSER_ADAPTER_ID = "prompt-library-workflow-browser";

const INVALID = "PRIVACY_SMART_PROMPT_ADAPTER_INVALID";

function fail() {
  throw new Error(INVALID);
}

function method(bridge, name) {
  const candidate = bridge?.[name];
  if (typeof candidate !== "function") fail();
  return candidate.bind(bridge);
}

function optionalMethod(bridge, name) {
  const candidate = bridge?.[name];
  return typeof candidate === "function" ? candidate.bind(bridge) : null;
}

function contextFieldId(context) {
  const fieldId = context?.field?.id ?? context?.fieldId ?? context?.id;
  if (fieldId !== SMART_PROMPT_PRIVACY_FIELD_ID) fail();
  const location = context?.field?.location ?? context?.location;
  if (location?.name !== undefined && location.name !== SMART_PROMPT_PRIVACY_WIDGET) fail();
  return fieldId;
}

function clone(value) {
  if (typeof structuredClone === "function") return structuredClone(value);
  return JSON.parse(JSON.stringify(value));
}

export function createSmartPromptModeBrowserAdapter({ productBridge } = {}) {
  const readModeMirror = method(productBridge, "readModeMirror");
  const writeModeMirror = method(productBridge, "writeModeMirror");
  const reconcileProductNode = optionalMethod(productBridge, "reconcileNode");
  const reconcileProductDefinition = optionalMethod(productBridge, "reconcileNodeDefinition");
  const notifyProductSession = optionalMethod(productBridge, "onPrivacySessionChange");

  return Object.freeze({
    readDeclaredMode(node) {
      const value = readModeMirror(node, SMART_PROMPT_PRIVACY_MODE_PROPERTY);
      if (value === false) return "public";
      if (value === true) return "private";
      return "inherit";
    },
    writeDeclaredMode(node, mode) {
      if (!["inherit", "private", "public"].includes(mode)) fail();
      const value = mode === "inherit" ? undefined : mode === "private";
      writeModeMirror(node, SMART_PROMPT_PRIVACY_MODE_PROPERTY, value);
    },
    reconcileNode(node) {
      reconcileProductNode?.(node);
    },
    reconcileNodeDefinition(nodeType, nodeData) {
      reconcileProductDefinition?.(nodeType, nodeData);
    },
    onPrivacySessionChange(snapshot) {
      notifyProductSession?.(snapshot);
    },
  });
}

function serializedWidgetIndex(node) {
  let index = 0;
  for (const candidate of node?.widgets || []) {
    const serialized = candidate?.serialize !== false
      && candidate?.options?.serialize !== false;
    if (candidate?.name === SMART_PROMPT_PRIVACY_WIDGET) return serialized ? index : -1;
    if (serialized) index += 1;
  }
  return -1;
}

export function createSmartPromptWorkflowBrowserAdapter({
  productBridge,
  workflowHandle = null,
  app = null,
} = {}) {
  const captureEditorState = method(productBridge, "captureEditorState");
  const normalizeEditorState = method(productBridge, "normalizeEditorState");
  const applyEditorState = method(productBridge, "applyEditorState");
  const clearEditorState = method(productBridge, "clearEditorState");
  const readProductProtected = method(productBridge, "readProtectedState");
  const writeProductProtected = method(productBridge, "writeProtectedState");
  const writeProductProjection = method(productBridge, "writeWorkflowProjection");
  const reconcileProductNode = optionalMethod(productBridge, "reconcileNode");
  const reconcileProductDefinition = optionalMethod(productBridge, "reconcileNodeDefinition");
  const notifyProductSession = optionalMethod(productBridge, "onPrivacySessionChange");
  const flushEditorState = optionalMethod(productBridge, "flushEditorState");
  const readDetachedProtected = optionalMethod(productBridge, "readDetachedProtectedState");
  const markWorkflowEdited = workflowHandle
    ? method(workflowHandle, "markEdited")
    : null;
  const settleWorkflow = workflowHandle ? method(workflowHandle, "settle") : null;
  const owners = new Set();

  function normalized(node, value, context) {
    contextFieldId(context);
    const result = normalizeEditorState(node, clone(value), context);
    if (!result || typeof result !== "object" || Array.isArray(result)) fail();
    return clone(result);
  }

  function reconcileOwner(node) {
    if (!node || typeof node !== "object") fail();
    owners.add(node);
    transition.synchronizeOwner(node);
    reconcileProductNode?.(node);
  }

  function detachedProtected(node, serializedNode, context) {
    if (readDetachedProtected) {
      const value = readDetachedProtected(node, serializedNode, context);
      if (typeof value !== "string") fail();
      return value;
    }
    const index = serializedWidgetIndex(node);
    const value = index >= 0 ? serializedNode?.widgets_values?.[index] : undefined;
    if (typeof value !== "string") fail();
    return value;
  }

  const transition = createSmartPromptExternalWorkflowTransition({
    app,
    owners,
    registerNode: reconcileOwner,
    readStorage(node, context) {
      contextFieldId(context);
      const value = readProductProtected(node, context);
      if (typeof value !== "string") fail();
      return value;
    },
    writeStorage(node, value, context) {
      contextFieldId(context);
      writeProductProtected(node, value, context);
    },
    readDetachedStorage: detachedProtected,
    async settleOwner(node) {
      const flushed = flushEditorState?.(node);
      if (flushed && typeof flushed.then === "function") await flushed;
      if (markWorkflowEdited) {
        markWorkflowEdited(node, SMART_PROMPT_PRIVACY_FIELD_ID);
        await settleWorkflow("mode-transition");
      }
    },
    reloadRuntime(node, exact, context) {
      let value;
      try {
        value = JSON.parse(exact);
      } catch {
        fail();
      }
      if (!value || typeof value !== "object" || Array.isArray(value)) fail();
      if (value.encrypted === true) clearEditorState(node, context);
      else applyEditorState(node, normalized(node, value, context), context);
    },
    reconcileRuntime: reconcileOwner,
    fail,
  });

  return Object.freeze({
    normalize(node, context) {
      return normalized(node, captureEditorState(node, context), context);
    },
    readProtected(node, context) {
      contextFieldId(context);
      const productValue = readProductProtected(node, context);
      if (typeof productValue !== "string") fail();
      return productValue;
    },
    writeProtected(node, protectedValue, context) {
      transition.requireMutable();
      contextFieldId(context);
      if (typeof protectedValue !== "string") fail();
      // The product's declared protected widget is the single byte owner.
      // Revealed apply/clear calls below never rewrite this opaque value.
      writeProductProtected(node, protectedValue, context);
    },
    writeWorkflowProjection(node, serializedNode, protectedValue, context) {
      contextFieldId(context);
      if (typeof protectedValue !== "string") fail();
      writeProductProjection(node, serializedNode, protectedValue, context);
    },
    apply(node, value, context) {
      transition.requireMutable();
      applyEditorState(node, normalized(node, value, context), context);
    },
    clear(node, context) {
      transition.requireMutable();
      contextFieldId(context);
      clearEditorState(node, context);
    },
    reconcileNode(node) {
      reconcileOwner(node);
    },
    reconcileNodeDefinition(nodeType, nodeData) {
      reconcileProductDefinition?.(nodeType, nodeData);
    },
    onPrivacySessionChange(snapshot) {
      notifyProductSession?.(snapshot);
    },
    ...transition,
  });
}
