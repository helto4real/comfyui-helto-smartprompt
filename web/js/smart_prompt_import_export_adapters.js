// Managed S2 browser phase client. Only product-free recovery capabilities are
// persisted, and every request stays bound to the declared import operation.

export const SMART_PROMPT_IMPORT_REPLACE_OPERATION = "import-replace";
export const SMART_PROMPT_IMPORT_MERGE_OPERATION = "import-merge";
export const SMART_PROMPT_EXPORT_OPERATION = "export";

const INVALID = "PRIVACY_SMART_PROMPT_IMPORT_EXPORT_INVALID";
const OPERATIONS = new Set([
  SMART_PROMPT_IMPORT_REPLACE_OPERATION,
  SMART_PROMPT_IMPORT_MERGE_OPERATION,
]);
const SESSION_PHASES = new Set([
  "preparing",
  "prepared",
  "finalize-ambiguous",
  "not-required",
]);

function fail() { throw new Error(INVALID); }

function required(owner, name) {
  const candidate = owner?.[name];
  if (typeof candidate !== "function") fail();
  return candidate.bind(owner);
}

function targetOwner(value) {
  if (!value || typeof value !== "object" || value.id === undefined) fail();
  return value;
}

function operation(value) {
  if (!OPERATIONS.has(value)) fail();
  return value;
}

function record(value) {
  if (!value || typeof value !== "object" || Array.isArray(value)) fail();
  return value;
}

export function createSmartPromptImportExportAdapter({
  workflowHandle,
  productBridge,
  sessionStore = globalThis.sessionStorage,
  idFactory = () => globalThis.crypto.randomUUID(),
} = {}) {
  const invoke = required(workflowHandle, "invoke");
  const settle = required(workflowHandle, "settle");
  const workflowProjection = required(workflowHandle, "workflowProjection");
  const readDestinationPrivate = required(productBridge, "readDestinationPrivate");
  const downloadExport = required(productBridge, "downloadExport");
  const exportedAt = required(productBridge, "exportedAt");
  if (!sessionStore || typeof sessionStore.getItem !== "function"
      || typeof sessionStore.setItem !== "function"
      || typeof sessionStore.removeItem !== "function"
      || typeof sessionStore.key !== "function"
      || typeof sessionStore.length !== "number"
      || typeof idFactory !== "function") fail();

  function ownerId(owner) { return `node-${String(targetOwner(owner).id)}`; }
  function storageKey(owner, operationId) {
    return `helto-smart-prompt-s2:${ownerId(owner)}:${operation(operationId)}`;
  }
  function load(owner, operationId) {
    const raw = sessionStore.getItem(storageKey(owner, operationId));
    if (raw === null) return null;
    try {
      const value = JSON.parse(raw);
      if (!value || typeof value !== "object" || Array.isArray(value)) fail();
      return value;
    } catch { fail(); }
  }
  function save(owner, operationId, value) {
    const phase = value.phase ?? (
      typeof value.transactionId === "string" && value.transactionId
        ? "prepared"
        : "preparing"
    );
    if (!SESSION_PHASES.has(phase)) fail();
    const allowed = {
      idempotencyKey: value.idempotencyKey,
      transactionId: value.transactionId ?? null,
      resumeToken: value.resumeToken ?? null,
      bindingId: value.bindingId ?? null,
      phase,
    };
    sessionStore.setItem(storageKey(owner, operationId), JSON.stringify(allowed));
    return Object.freeze(allowed);
  }
  function clear(owner, operationId) {
    sessionStore.removeItem(storageKey(owner, operationId));
  }
  function hasAnyPendingSession() {
    for (let index = 0; index < sessionStore.length; index += 1) {
      const key = sessionStore.key(index);
      if (typeof key === "string" && key.startsWith("helto-smart-prompt-s2:")) {
        return true;
      }
    }
    return false;
  }
  function requireSession(owner, operationId, candidate = load(owner, operationId)) {
    record(candidate);
    for (const name of ["idempotencyKey", "transactionId", "resumeToken", "bindingId"]) {
      if (typeof candidate[name] !== "string" || !candidate[name]) fail();
    }
    return candidate;
  }
  async function settledProjection(target, reason) {
    await settle(reason);
    const projection = workflowProjection(targetOwner(target), "prompt-library-state");
    if (typeof projection !== "string" || !projection) fail();
    return projection;
  }
  function phasePayload(session, phase, extra = {}) {
    return {
      phase,
      owner_id: session.ownerId,
      transaction_id: session.transactionId,
      resume_token: session.resumeToken,
      binding_id: session.bindingId,
      ...extra,
    };
  }

  return Object.freeze({
    async captureBoundary(target) {
      target = targetOwner(target);
      return settledProjection(target, "manual-save");
    },
    async prepare(target, operationId, raw, {
      explicitReexport = false,
      destinationSnapshot,
      destinationPrivate = readDestinationPrivate(targetOwner(target)) !== false,
    } = {}) {
      target = targetOwner(target);
      operationId = operation(operationId);
      if (typeof raw !== "string" || !raw.trim()
          || typeof destinationSnapshot !== "string"
          || typeof destinationPrivate !== "boolean") fail();
      const prior = load(target, operationId);
      const idempotencyKey = prior?.idempotencyKey ?? `request-${idFactory()}`;
      save(target, operationId, {
        idempotencyKey,
        transactionId: prior?.transactionId,
        resumeToken: prior?.resumeToken,
        bindingId: prior?.bindingId,
        phase: "preparing",
      });
      const result = record(await invoke(operationId, {
        phase: "prepare",
        owner_id: ownerId(target),
        idempotency_key: idempotencyKey,
        raw,
        explicit_reexport: explicitReexport === true,
        destination_snapshot: destinationSnapshot,
        destination_private: destinationPrivate,
      }));
      const session = save(target, operationId, {
        idempotencyKey,
        transactionId: result.transactionId,
        resumeToken: result.resumeToken,
        bindingId: result.bindingId,
        phase: result.transactionId ? "prepared" : "not-required",
      });
      return Object.freeze({ ...result, session: Object.freeze({
        ...session,
        ownerId: ownerId(target),
      }) });
    },
    async reexport(target, operationId, session, committedSnapshot, destinationPrivate) {
      target = targetOwner(target);
      operationId = operation(operationId);
      session = requireSession(target, operationId, session);
      return record(await invoke(operationId, phasePayload(
        { ...session, ownerId: ownerId(target) }, "reexport", {
          committed_snapshot: committedSnapshot,
          destination_private: destinationPrivate,
        },
      )));
    },
    async finalize(target, operationId, session, committedSnapshot, destinationPrivate, digest) {
      target = targetOwner(target);
      operationId = operation(operationId);
      session = requireSession(target, operationId, session);
      session = save(target, operationId, {
        ...session,
        phase: "finalize-ambiguous",
      });
      const result = record(await invoke(operationId, phasePayload(
        { ...session, ownerId: ownerId(target) }, "finalize", {
          committed_snapshot: committedSnapshot,
          destination_private: destinationPrivate,
          reexport_digest: digest,
        },
      )));
      clear(target, operationId);
      return result;
    },
    status(target, operationId, session) {
      target = targetOwner(target);
      operationId = operation(operationId);
      session = requireSession(target, operationId, session);
      return invoke(operationId, phasePayload({ ...session, ownerId: ownerId(target) }, "status"));
    },
    async resume(target, operationId) {
      target = targetOwner(target);
      operationId = operation(operationId);
      const session = requireSession(target, operationId);
      const result = record(await invoke(
        operationId,
        phasePayload({ ...session, ownerId: ownerId(target) }, "resume"),
      ));
      return Object.freeze({
        ...result,
        session: Object.freeze({ ...session, ownerId: ownerId(target) }),
      });
    },
    pendingSession(target, operationId) {
      target = targetOwner(target);
      operationId = operation(operationId);
      const session = load(target, operationId);
      if (session === null) return null;
      return Object.freeze({ ...session, ownerId: ownerId(target) });
    },
    hasPendingSession(target) {
      target = targetOwner(target);
      return [...OPERATIONS].some((operationId) => load(target, operationId) !== null);
    },
    hasAnyPendingSession,
    cancel(target, operationId, session) {
      target = targetOwner(target);
      operationId = operation(operationId);
      session = requireSession(target, operationId, session);
      return invoke(operationId, phasePayload({ ...session, ownerId: ownerId(target) }, "cancel"));
    },
    async rollbackAck(target, operationId, session, restoredSnapshot) {
      target = targetOwner(target);
      operationId = operation(operationId);
      session = requireSession(target, operationId, session);
      const result = await invoke(operationId, phasePayload(
        { ...session, ownerId: ownerId(target) }, "rollback-ack", {
          restored_snapshot: restoredSnapshot,
        },
      ));
      clear(target, operationId);
      return result;
    },
    clearSession(target, operationId) { clear(targetOwner(target), operation(operationId)); },
    async exportLibrary(target) {
      target = targetOwner(target);
      const settledSnapshot = await settledProjection(target, "export");
      const result = await invoke(SMART_PROMPT_EXPORT_OPERATION, {
        settled_snapshot: settledSnapshot,
        private: readDestinationPrivate(target) !== false,
        exported_at: exportedAt(target),
      });
      await downloadExport(target, result);
      return result;
    },
  });
}
