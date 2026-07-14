// Product integration for the composed Smart Prompt privacy profile.
// Shared browser handles exclusively own mode, generations, serialization,
// protection, migration, execution preparation, and session freshness.

import {
  SMART_PROMPT_MODE_BROWSER_ADAPTER_ID,
  SMART_PROMPT_PRIVACY_FIELD_ID,
  SMART_PROMPT_PRIVACY_SCOPE_ID,
  SMART_PROMPT_WORKFLOW_BROWSER_ADAPTER_ID,
  createSmartPromptModeBrowserAdapter,
  createSmartPromptWorkflowBrowserAdapter,
} from "./smart_prompt_privacy_adapters.js";
import { createSmartPromptImportExportAdapter } from "./smart_prompt_import_export_adapters.js";
import { createSmartPromptExecutionAdapter } from "./smart_prompt_execution_adapters.js";

export {
  SMART_PROMPT_MODE_BROWSER_ADAPTER_ID,
  SMART_PROMPT_PRIVACY_SCOPE_ID,
  SMART_PROMPT_WORKFLOW_BROWSER_ADAPTER_ID,
};

// Auditable inventory of the live seams replaced by the atomic activation.
export const SMART_PROMPT_FINAL_ATOMIC_SWITCH = Object.freeze([
  Object.freeze({
    current: "function save(render = true)",
    replacement: "coordinator.flushEditor(node)",
    removes: Object.freeze(["trackPrivacySave", "encryptAndSetWidget"]),
  }),
  Object.freeze({
    current: "function saveWithoutRender()",
    replacement: "coordinator.flushEditor(node)",
    removes: Object.freeze(["_spmPendingPrivacySave"]),
  }),
  Object.freeze({
    current: "dataWidget.serializeValue = async function",
    replacement: "coordinator.serializeWorkflow(node, serializeOperation)",
    removes: Object.freeze(["preparePrivacySerialization"]),
  }),
  Object.freeze({
    current: "node.onSerialize = function (info)",
    replacement: "coordinator.workflowProjection(node)",
    removes: Object.freeze(["currentSerializedSpmData", "writeSerializedSpmData"]),
  }),
  Object.freeze({
    current: "async function exportLibraryFile()",
    replacement: "coordinator.exportLibrary(node)",
    removes: Object.freeze(["buildSpmExportPackage", "privacyPost"]),
  }),
  Object.freeze({
    current: "async function importLibraryText(raw, replace)",
    replacement: "coordinator.importReplace(node, raw) / coordinator.importMerge(node, raw)",
    removes: Object.freeze(["parseSpmImport", "privacyPost"]),
  }),
  Object.freeze({
    current: "function installSpmGraphToPromptPatch",
    replacement: "shared connectPrivacyPack submission injection",
    removes: Object.freeze([
      "waitForSpmPrivacySaves",
      "applySpmCacheTokensToPrompt",
      "SPM_CACHE_TOKEN_PREFIX",
    ]),
  }),
  Object.freeze({
    current: "async function setPrivacyMode(enabled)",
    replacement: "coordinator.transitionMode(node, target)",
    removes: Object.freeze(["privacyPost", "syncSpmRecoveryPrivacyModeProperty"]),
  }),
  Object.freeze({
    current: "async function openPrivacyRecoveryDialog()",
    replacement: "coordinator.onSharedRecoveryComplete(node)",
    removes: Object.freeze([
      "openPrivacyRecoveryDialog",
      "privacy-recovery button/action",
      "registerSpmPrivacyRecovery",
      "SPM_PRIVACY_MEMOS",
      "_spmPendingPrivacySave",
    ]),
  }),
]);

const INVALID = "PRIVACY_SMART_PROMPT_COORDINATOR_INVALID";
const MODES = new Set(["inherit", "private", "public"]);

function fail() {
  throw new Error(INVALID);
}

function required(owner, name) {
  const candidate = owner?.[name];
  if (typeof candidate !== "function") fail();
  return candidate.bind(owner);
}

function requireNode(node) {
  if (!node || typeof node !== "object" || node.id === undefined) fail();
  return node;
}

function requireOperation(operation) {
  if (typeof operation !== "function") fail();
  return operation;
}

export function createSmartPromptPrivacyCoordinator({
  workflowHandle,
  modeHandle,
  executionHandle,
  productBridge,
  browserAdapters = null,
  sessionStore,
  idFactory,
  app = null,
} = {}) {
  const markEdited = required(workflowHandle, "markEdited");
  const settle = required(workflowHandle, "settle");
  const runWithSnapshot = required(workflowHandle, "runWithSnapshot");
  const requireSettled = required(workflowHandle, "requireSettled");
  const workflowProjection = required(workflowHandle, "workflowProjection");
  const reload = required(workflowHandle, "reload");
  const resolveMode = required(modeHandle, "resolve");
  const flushEditorState = required(productBridge, "flushEditorState");
  const captureImportState = required(productBridge, "captureImportState");
  const applyImportResult = required(productBridge, "applyImportResult");
  const commitImportState = required(productBridge, "commitImportState");
  const restoreImportState = required(productBridge, "restoreImportState");
  const readDestinationPrivate = required(productBridge, "readDestinationPrivate");
  const downloadExport = required(productBridge, "downloadExport");
  const exportedAt = required(productBridge, "exportedAt");
  const pendingImports = new Set();
  const ambiguousImports = new Set();

  const modeAdapter = browserAdapters?.[SMART_PROMPT_MODE_BROWSER_ADAPTER_ID]
    ?? createSmartPromptModeBrowserAdapter({ productBridge });
  const workflowAdapter = browserAdapters?.[SMART_PROMPT_WORKFLOW_BROWSER_ADAPTER_ID]
    ?? createSmartPromptWorkflowBrowserAdapter({
      productBridge,
      workflowHandle,
      app,
    });
  const importExportAdapter = createSmartPromptImportExportAdapter({
    workflowHandle,
    productBridge: {
      readDestinationPrivate,
      downloadExport,
      exportedAt,
    },
    sessionStore,
    idFactory,
  });
  const executionAdapter = createSmartPromptExecutionAdapter({
    workflowHandle,
    executionHandle,
    productBridge,
  });

  function mark(node) {
    workflowAdapter.requireMutable();
    return markEdited(requireNode(node), SMART_PROMPT_PRIVACY_FIELD_ID);
  }

  function ownerKey(node) {
    return String(requireNode(node).id);
  }

  function flush(node) {
    const owner = requireNode(node);
    workflowAdapter.requireMutable();
    const result = flushEditorState(owner);
    if (result && typeof result.then === "function") fail();
    return mark(owner);
  }

  function reconcile(node) {
    const owner = requireNode(node);
    modeAdapter.reconcileNode(owner);
    workflowAdapter.reconcileNode(owner);
  }

  function modeResult(owner, result) {
    if (!result || typeof result !== "object" || Array.isArray(result)) fail();
    return Object.freeze({
      ...result,
      declared: modeAdapter.readDeclaredMode(owner),
    });
  }

  function requireGlobalBarrierAvailable() {
    if (
      pendingImports.size > 0
      || ambiguousImports.size > 0
      || importExportAdapter.hasAnyPendingSession()
    ) fail();
  }

  function requireOwnerAvailable(owner) {
    const key = ownerKey(owner);
    if (
      pendingImports.has(key)
      || ambiguousImports.has(key)
      || importExportAdapter.hasPendingSession(owner)
    ) fail();
  }

  async function rollbackImport(owner, boundary, operationId, session) {
    let failed = false;
    let originalSnapshot = boundary?.protectedValue;
    let restoreBoundary = boundary;
    if (session?.transactionId) {
      const status = await importExportAdapter.status(owner, operationId, session);
      if (status?.disposition === "migrated") {
        if (typeof status.receiptId !== "string" || !status.receiptId) fail();
        importExportAdapter.clearSession(owner, operationId);
        return status;
      }
      if (!["prepared", "rollback-required"].includes(status?.disposition)) fail();
      const cancelled = await importExportAdapter.cancel(owner, operationId, session);
      if (cancelled?.disposition === "migrated") {
        if (typeof cancelled.receiptId !== "string" || !cancelled.receiptId) fail();
        importExportAdapter.clearSession(owner, operationId);
        return cancelled;
      }
      if (cancelled?.disposition !== "rollback-required"
          || typeof cancelled.originalSnapshot !== "string") fail();
      originalSnapshot = cancelled.originalSnapshot;
      if (boundary !== null && originalSnapshot !== boundary.protectedValue) fail();
      restoreBoundary = boundary ?? Object.freeze({
        protectedValue: originalSnapshot,
        recovery: true,
      });
    }
    if (!restoreBoundary || typeof originalSnapshot !== "string") fail();
    try {
      await restoreImportState(owner, restoreBoundary, operationId);
    } catch {
      failed = true;
    }
    try {
      reconcile(owner);
    } catch {
      failed = true;
    }
    try {
      await reload(owner, SMART_PROMPT_PRIVACY_FIELD_ID);
      requireSettled("serialize");
      const restored = workflowProjection(owner, SMART_PROMPT_PRIVACY_FIELD_ID);
      if (restored !== originalSnapshot) failed = true;
      if (session?.transactionId) {
        const acknowledged = await importExportAdapter.rollbackAck(
          owner, operationId, session, restored,
        );
        if (acknowledged?.disposition !== "rolled-back") failed = true;
      } else {
        importExportAdapter.clearSession(owner, operationId);
      }
    } catch {
      failed = true;
    }
    if (failed) fail();
    return Object.freeze({ disposition: "rolled-back" });
  }

  async function importLibrary(node, raw, options, operationId) {
    const owner = requireNode(node);
    const key = ownerKey(owner);
    const persisted = importExportAdapter.pendingSession(owner, operationId);
    const preparingRetry = persisted?.phase === "preparing"
      && !persisted.transactionId;
    if (
      pendingImports.has(key)
      || (ambiguousImports.has(key) && !preparingRetry)
      || (persisted !== null && !preparingRetry)
    ) fail();
    if (preparingRetry) ambiguousImports.delete(key);
    pendingImports.add(key);
    let boundary = null;
    let result = null;
    let reexport = null;
    try {
      flush(owner);
      const destinationSnapshot = await importExportAdapter.captureBoundary(owner);
      boundary = await captureImportState(owner, operationId);
      if (
        !boundary
        || typeof boundary !== "object"
        || Array.isArray(boundary)
        || typeof boundary.protectedValue !== "string"
        || boundary.protectedValue !== destinationSnapshot
      ) fail();
      const invocationOptions = options === undefined ? {} : options;
      if (
        !invocationOptions
        || typeof invocationOptions !== "object"
        || Array.isArray(invocationOptions)
      ) fail();
      const destinationPrivate = readDestinationPrivate(owner) !== false;
      result = await importExportAdapter.prepare(owner, operationId, raw, {
        ...invocationOptions,
        destinationSnapshot,
        destinationPrivate,
      });
      await applyImportResult(owner, result, operationId);
      mark(owner);
      await settle("manual-save");
      requireSettled("serialize");
      const committedSnapshot = workflowProjection(
        owner, SMART_PROMPT_PRIVACY_FIELD_ID,
      );
      await commitImportState(owner, boundary, operationId);
      if (!result.session.transactionId) {
        importExportAdapter.clearSession(owner, operationId);
        return result;
      }
      reexport = await importExportAdapter.reexport(
        owner, operationId, result.session, committedSnapshot, destinationPrivate,
      );
      await downloadExport(owner, reexport);
      requireSettled("serialize");
      const finalSnapshot = workflowProjection(
        owner, SMART_PROMPT_PRIVACY_FIELD_ID,
      );
      let receipt;
      try {
        receipt = await importExportAdapter.finalize(
          owner, operationId, result.session, finalSnapshot,
          destinationPrivate, reexport.digest,
        );
      } catch (error) {
        ambiguousImports.add(key);
        let status;
        try {
          status = await importExportAdapter.status(owner, operationId, result.session);
        } catch {
          throw error;
        }
        if (status?.disposition !== "migrated" || typeof status.receiptId !== "string") {
          throw error;
        }
        receipt = status;
        importExportAdapter.clearSession(owner, operationId);
        ambiguousImports.delete(key);
      }
      return Object.freeze({ ...result, receiptId: receipt.receiptId, reexport });
    } catch (error) {
      if (boundary !== null && result !== null && !(result?.receiptId)) {
        try {
          const recovered = await rollbackImport(
            owner, boundary, operationId, result.session,
          );
          if (recovered.disposition === "migrated") {
            ambiguousImports.delete(key);
            return Object.freeze({
              ...result,
              receiptId: recovered.receiptId,
              reexport,
            });
          }
          ambiguousImports.delete(key);
        } catch (rollbackError) {
          if (result.session?.transactionId) ambiguousImports.add(key);
          throw rollbackError;
        }
      } else if (boundary !== null && result === null) {
        const preparing = importExportAdapter.pendingSession(owner, operationId);
        if (preparing?.phase === "preparing") ambiguousImports.add(key);
      }
      throw error;
    } finally {
      pendingImports.delete(key);
    }
  }

  return Object.freeze({
    browserAdapters: Object.freeze({
      [SMART_PROMPT_MODE_BROWSER_ADAPTER_ID]: modeAdapter,
      [SMART_PROMPT_WORKFLOW_BROWSER_ADAPTER_ID]: workflowAdapter,
    }),
    markEditorMutation(node) {
      requireOwnerAvailable(node);
      return mark(node);
    },
    flushEditor(node) {
      requireOwnerAvailable(node);
      return flush(node);
    },
    async saveWorkflow(node, operation) {
      requireNode(node);
      requireGlobalBarrierAvailable();
      flush(node);
      return runWithSnapshot("manual-save", requireOperation(operation));
    },
    serializeWorkflow(node) {
      const owner = requireNode(node);
      requireGlobalBarrierAvailable();
      requireSettled("serialize");
      return workflowProjection(owner, SMART_PROMPT_PRIVACY_FIELD_ID);
    },
    workflowProjection(node) {
      requireGlobalBarrierAvailable();
      return workflowProjection(requireNode(node), SMART_PROMPT_PRIVACY_FIELD_ID);
    },
    async importReplace(node, raw, options) {
      return importLibrary(node, raw, options, "import-replace");
    },
    async importMerge(node, raw, options) {
      return importLibrary(node, raw, options, "import-merge");
    },
    async recoverPendingImport(node, operationId) {
      const owner = requireNode(node);
      const key = ownerKey(owner);
      if (!["import-replace", "import-merge"].includes(operationId)
          || pendingImports.has(key)) fail();
      pendingImports.add(key);
      try {
        const session = importExportAdapter.pendingSession(owner, operationId);
        if (!session?.transactionId) fail();
        let status;
        try {
          status = await importExportAdapter.status(owner, operationId, session);
        } catch (error) {
          ambiguousImports.add(key);
          throw error;
        }
        if (status?.disposition === "migrated") {
          importExportAdapter.clearSession(owner, operationId);
          ambiguousImports.delete(key);
          return status;
        }
        try {
          const recovered = await rollbackImport(owner, null, operationId, session);
          ambiguousImports.delete(key);
          return recovered;
        } catch (error) {
          ambiguousImports.add(key);
          throw error;
        }
      } finally {
        pendingImports.delete(key);
      }
    },
    async exportLibrary(node) {
      const owner = requireNode(node);
      requireGlobalBarrierAvailable();
      flush(owner);
      return importExportAdapter.exportLibrary(owner);
    },
    async resolveMode(node) {
      const owner = requireNode(node);
      return modeResult(
        owner,
        await resolveMode(SMART_PROMPT_PRIVACY_SCOPE_ID, owner),
      );
    },
    async transitionMode(node, target) {
      const owner = requireNode(node);
      requireOwnerAvailable(owner);
      if (!MODES.has(target)) fail();
      const previous = modeAdapter.readDeclaredMode(owner);
      modeAdapter.writeDeclaredMode(owner, target);
      try {
        mark(owner);
        await settle("manual-save");
        return modeResult(
          owner,
          await resolveMode(SMART_PROMPT_PRIVACY_SCOPE_ID, owner),
        );
      } catch (error) {
        modeAdapter.writeDeclaredMode(owner, previous);
        try {
          mark(owner);
          await settle("manual-save");
          reconcile(owner);
        } catch {
          fail();
        }
        throw error;
      }
    },
    reconcileAfterRecovery(node) {
      reconcile(node);
    },
    onSharedRecoveryComplete(node) {
      reconcile(node);
    },
    reconcilePrivacySession(snapshot, owners) {
      if (!Array.isArray(owners)) fail();
      modeAdapter.onPrivacySessionChange(snapshot);
      workflowAdapter.onPrivacySessionChange(snapshot);
      executionAdapter.onPrivacySessionChange(snapshot);
      for (const owner of owners) {
        reconcile(owner);
      }
    },
  });
}
