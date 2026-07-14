import assert from "node:assert/strict";
import test from "node:test";

import {
  SMART_PROMPT_FINAL_ATOMIC_SWITCH,
  createSmartPromptPrivacyCoordinator,
} from "../web/js/smart_prompt_privacy_coordinator.js";
import {
  SMART_PROMPT_MODE_BROWSER_ADAPTER_ID,
  SMART_PROMPT_WORKFLOW_BROWSER_ADAPTER_ID,
  createSmartPromptModeBrowserAdapter,
  createSmartPromptWorkflowBrowserAdapter,
} from "../web/js/smart_prompt_privacy_adapters.js";


class MemoryStore {
  constructor() { this.values = new Map(); }
  get length() { return this.values.size; }
  key(index) { return [...this.values.keys()][index] ?? null; }
  getItem(key) { return this.values.has(key) ? this.values.get(key) : null; }
  setItem(key, value) { this.values.set(key, String(value)); }
  removeItem(key) { this.values.delete(key); }
}

function node(id) {
  return { id, editor: { title: `before-${id}` }, protected: `ORIGINAL:${id}`, private: true, mode: {} };
}

function harness({
  applyFailure = false,
  cancelResponseLossCount = 0,
  downloadFailure = false,
  finalizeFailure = false,
  finalizeResponseLoss = false,
  prepareResponseLossCount = 0,
  statusResponseLossCount = 0,
  prepareBarrier = null,
  recoverySession = null,
  sharedState = null,
  prebuiltBrowserAdapters = false,
} = {}) {
  const events = [];
  const edited = new Set();
  const state = sharedState ?? {
    statuses: new Map(),
    originals: new Map(),
    prepareResults: new Map(),
    sessionStore: new MemoryStore(),
  };
  const { statuses, originals, prepareResults, sessionStore } = state;
  let remainingPrepareResponseLosses = prepareResponseLossCount;
  let remainingStatusResponseLosses = statusResponseLossCount;
  let remainingCancelResponseLosses = cancelResponseLossCount;
  let generation = 0;
  const workflowHandle = {
    markEdited(owner) { edited.add(owner); events.push(["mark", owner.id]); return ++generation; },
    async settle(reason) {
      events.push(["settle", reason]);
      for (const owner of edited) owner.protected = `COMMITTED:${owner.id}:${generation}`;
      edited.clear();
    },
    async runWithSnapshot(_reason, operation) { await this.settle("manual-save"); return operation({}); },
    requireSettled() { if (edited.size) throw new Error("UNSETTLED"); return true; },
    workflowProjection(owner) { events.push(["projection", owner.id, owner.protected]); return owner.protected; },
    async reload(owner) { events.push(["reload", owner.id, owner.protected]); },
    async invoke(operation, payload) {
      events.push([
        `server:${payload.phase ?? operation}`,
        payload.owner_id,
        structuredClone(payload),
      ]);
      if (payload.phase === "prepare") {
        if (prepareBarrier) await prepareBarrier;
        const legacy = payload.raw !== "plain";
        const requestKey = `${operation}:${payload.owner_id}:${payload.idempotency_key}`;
        let prepared = prepareResults.get(requestKey);
        if (!prepared) {
          prepared = {
            state: { title: `after-${payload.owner_id}`, privacyMode: payload.destination_private },
            protectedValue: `PREPARED:${payload.owner_id}`,
            transactionId: legacy ? `tx-${payload.owner_id}` : null,
            resumeToken: legacy ? `resume-${payload.owner_id}` : null,
            bindingId: legacy ? `binding-${operation}` : null,
            disposition: legacy ? "prepared" : "not-required",
          };
          prepareResults.set(requestKey, prepared);
          if (legacy) originals.set(prepared.transactionId, payload.destination_snapshot);
        }
        if (remainingPrepareResponseLosses > 0) {
          remainingPrepareResponseLosses -= 1;
          throw new Error("SYNTHETIC_PREPARE_RESPONSE_LOSS");
        }
        return structuredClone(prepared);
      }
      const tx = payload.transaction_id;
      if (payload.phase === "reexport") return { filename: `${tx}.json`, text: "{}", digest: "d".repeat(64) };
      if (payload.phase === "finalize") {
        if (finalizeFailure) throw new Error("SYNTHETIC_FINALIZE_FAILURE");
        statuses.set(tx, { disposition: "migrated", receiptId: `receipt-${tx}` });
        if (finalizeResponseLoss) throw new Error("SYNTHETIC_FINALIZE_RESPONSE_LOSS");
        return statuses.get(tx);
      }
      if (payload.phase === "status") {
        if (remainingStatusResponseLosses > 0) {
          remainingStatusResponseLosses -= 1;
          throw new Error("SYNTHETIC_STATUS_RESPONSE_LOSS");
        }
        return statuses.get(tx) ?? { disposition: "prepared" };
      }
      if (payload.phase === "resume") return {
        disposition: "prepared",
        originalSnapshot: originals.get(tx),
      };
      if (payload.phase === "cancel") {
        if (remainingCancelResponseLosses > 0) {
          remainingCancelResponseLosses -= 1;
          throw new Error("SYNTHETIC_CANCEL_RESPONSE_LOSS");
        }
        return { disposition: "rollback-required", originalSnapshot: originals.get(tx) };
      }
      if (payload.phase === "rollback-ack") return { disposition: "rolled-back" };
      if (operation === "export") return { filename: "export.json", text: "{}" };
      throw new Error("UNEXPECTED_PHASE");
    },
  };
  const productBridge = {
    flushEditorState(owner) { events.push(["flush", owner.id]); },
    captureImportState(owner) {
      events.push(["capture", owner.id, owner.protected]);
      return { editor: structuredClone(owner.editor), protectedValue: owner.protected };
    },
    async applyImportResult(owner, result) {
      owner.editor = structuredClone(result.state);
      events.push(["apply", owner.id]);
      if (applyFailure) throw new Error("SYNTHETIC_APPLY_FAILURE");
    },
    async commitImportState(owner) { events.push(["commit", owner.id]); },
    async restoreImportState(owner, boundary) {
      owner.editor = structuredClone(boundary.editor);
      owner.protected = boundary.protectedValue;
      events.push(["restore", owner.id, owner.protected]);
    },
    readDestinationPrivate(owner) { return owner.private; },
    async downloadExport(owner) {
      events.push(["download", owner.id]);
      if (downloadFailure) throw new Error("SYNTHETIC_DOWNLOAD_FAILURE");
    },
    exportedAt() { return "2026-07-13T12:00:00Z"; },
    readModeMirror(owner, property) { return owner.mode[property]; },
    writeModeMirror(owner, property, value) { if (value === undefined) delete owner.mode[property]; else owner.mode[property] = value; },
    captureEditorState(owner) { return structuredClone(owner.editor); },
    normalizeEditorState(_owner, value) { return value; },
    applyEditorState(owner, value) { owner.editor = structuredClone(value); },
    clearEditorState(owner) { owner.editor = null; },
    readProtectedState(owner) { return owner.protected; },
    writeProtectedState(owner, value) { owner.protected = value; },
    writeWorkflowProjection() {},
    async writeExecutionInputs() {},
    clearExecutionInputs() {},
    reconcileNode() {},
  };
  if (recoverySession) {
    sessionStore.setItem(
      `helto-smart-prompt-s2:node-${recoverySession.ownerId}:${recoverySession.operation}`,
      JSON.stringify(recoverySession.session),
    );
    originals.set(recoverySession.session.transactionId, recoverySession.originalSnapshot);
  }
  const browserAdapters = prebuiltBrowserAdapters ? {
    [SMART_PROMPT_MODE_BROWSER_ADAPTER_ID]: createSmartPromptModeBrowserAdapter({ productBridge }),
    [SMART_PROMPT_WORKFLOW_BROWSER_ADAPTER_ID]: createSmartPromptWorkflowBrowserAdapter({
      productBridge,
      workflowHandle,
    }),
  } : null;
  const coordinator = createSmartPromptPrivacyCoordinator({
    workflowHandle,
    modeHandle: { resolve() { return { effective: "private", source: "test" }; } },
    executionHandle: { async prepare() {} },
    productBridge,
    browserAdapters,
    sessionStore,
    idFactory: (() => { let value = 0; return () => `id-${++value}`; })(),
  });
  return { coordinator, events, state, browserAdapters };
}

test("coordinator reuses the browser adapters registered with the shared pack", () => {
  const { coordinator, browserAdapters } = harness({ prebuiltBrowserAdapters: true });
  assert.equal(
    coordinator.browserAdapters[SMART_PROMPT_MODE_BROWSER_ADAPTER_ID],
    browserAdapters[SMART_PROMPT_MODE_BROWSER_ADAPTER_ID],
  );
  assert.equal(
    coordinator.browserAdapters[SMART_PROMPT_WORKFLOW_BROWSER_ADAPTER_ID],
    browserAdapters[SMART_PROMPT_WORKFLOW_BROWSER_ADAPTER_ID],
  );
});

test("legacy import applies, settles, commits, downloads, then receives receipt", async () => {
  const { coordinator, events } = harness();
  const owner = node(1);
  const result = await coordinator.importReplace(owner, "legacy", { explicitReexport: true });
  assert.equal(result.receiptId, "receipt-tx-node-1");
  const names = events.map((entry) => entry[0]);
  for (const pair of [["capture", "server:prepare"], ["apply", "commit"], ["commit", "server:reexport"], ["download", "server:finalize"]]) {
    assert(names.indexOf(pair[0]) < names.indexOf(pair[1]), `${pair[0]} before ${pair[1]}`);
  }
});

test("two node imports are isolated and same-owner overlap is rejected", async () => {
  const { coordinator } = harness();
  const first = node(2);
  const second = node(3);
  second.private = false;
  const [one, two] = await Promise.all([
    coordinator.importReplace(first, "legacy", { explicitReexport: true }),
    coordinator.importMerge(second, "legacy", { explicitReexport: true }),
  ]);
  assert.match(one.receiptId, /node-2/);
  assert.match(two.receiptId, /node-3/);
  assert.equal(second.editor.privacyMode, false);
});

test("download failure cancels, restores exact bytes, reloads, reads back, and acknowledges", async () => {
  const { coordinator, events } = harness({ downloadFailure: true });
  const owner = node(4);
  await assert.rejects(coordinator.importReplace(owner, "legacy", { explicitReexport: true }));
  assert.equal(owner.protected, "COMMITTED:4:1");
  const names = events.map((entry) => entry[0]);
  assert(names.indexOf("server:cancel") < names.indexOf("restore"));
  assert(names.indexOf("restore") < names.indexOf("reload"));
  assert(names.indexOf("reload") < names.lastIndexOf("projection"));
  assert(names.lastIndexOf("projection") < names.indexOf("server:rollback-ack"));
});

test("finalize response loss recovers migrated receipt through status without rollback", async () => {
  const { coordinator, events } = harness({ finalizeResponseLoss: true });
  const owner = node(5);
  const result = await coordinator.importReplace(owner, "legacy", { explicitReexport: true });
  assert.equal(result.receiptId, "receipt-tx-node-5");
  assert(events.some((entry) => entry[0] === "server:status"));
  assert(!events.some((entry) => entry[0] === "server:cancel"));
});

test("apply and finalize failures both cancel and restore the exact boundary", async () => {
  for (const options of [{ applyFailure: true }, { finalizeFailure: true }]) {
    const { coordinator, events } = harness(options);
    const owner = node(options.applyFailure ? 6 : 7);
    await assert.rejects(coordinator.importReplace(owner, "legacy", { explicitReexport: true }));
    assert.match(owner.protected, /^COMMITTED:/);
    assert(events.some((entry) => entry[0] === "server:cancel"));
    assert(events.some((entry) => entry[0] === "server:rollback-ack"));
  }
});

test("same-owner pending import rejects serialization and a concurrent import", async () => {
  let release;
  const barrier = new Promise((resolve) => { release = resolve; });
  const { coordinator } = harness({ prepareBarrier: barrier });
  const owner = node(8);
  const other = node(80);
  const pending = coordinator.importReplace(owner, "legacy", { explicitReexport: true });
  await Promise.resolve();
  assert.throws(() => coordinator.serializeWorkflow(owner), /PRIVACY_SMART_PROMPT_COORDINATOR_INVALID/);
  assert.throws(() => coordinator.serializeWorkflow(other), /PRIVACY_SMART_PROMPT_COORDINATOR_INVALID/);
  await assert.rejects(
    coordinator.saveWorkflow(other, async () => "must-not-save"),
    /PRIVACY_SMART_PROMPT_COORDINATOR_INVALID/,
  );
  await assert.rejects(
    coordinator.importMerge(owner, "legacy", { explicitReexport: true }),
    /PRIVACY_SMART_PROMPT_COORDINATOR_INVALID/,
  );
  release();
  await pending;
});

test("restart recovery resumes private original then cancels and verifies rollback", async () => {
  const recoverySession = {
    ownerId: 9,
    operation: "import-replace",
    originalSnapshot: "RESTART-ORIGINAL:9",
    session: {
      idempotencyKey: "request-restart",
      transactionId: "tx-node-9",
      resumeToken: "resume-node-9",
      bindingId: "binding-import-replace",
    },
  };
  const { coordinator, events } = harness({ recoverySession });
  const owner = node(9);
  owner.protected = "AMBIGUOUS:9";
  const recovered = await coordinator.recoverPendingImport(owner, "import-replace");
  assert.equal(recovered.disposition, "rolled-back");
  assert.equal(owner.protected, "RESTART-ORIGINAL:9");
  assert(events.some((entry) => entry[0] === "server:status"));
  assert(events.some((entry) => entry[0] === "server:cancel"));
  assert(events.some((entry) => entry[0] === "server:rollback-ack"));
});

test("prepare response loss keeps the idempotency key and restart retry recovers the same transaction", async () => {
  const first = harness({ prepareResponseLossCount: 1 });
  const firstOwner = node(10);
  await assert.rejects(
    first.coordinator.importReplace(firstOwner, "legacy", { explicitReexport: true }),
    /SYNTHETIC_PREPARE_RESPONSE_LOSS/,
  );
  assert(!first.events.some((entry) => entry[0] === "restore"));
  assert(!first.events.some((entry) => entry[0] === "server:cancel"));
  const storedAfterLoss = JSON.parse([...first.state.sessionStore.values.values()][0]);
  assert.equal(storedAfterLoss.phase, "preparing");
  assert.equal(storedAfterLoss.transactionId, null);
  assert.throws(
    () => first.coordinator.serializeWorkflow(node(100)),
    /PRIVACY_SMART_PROMPT_COORDINATOR_INVALID/,
  );

  const restarted = harness({ sharedState: first.state });
  const restartedOwner = node(10);
  const result = await restarted.coordinator.importReplace(
    restartedOwner, "legacy", { explicitReexport: true },
  );
  assert.equal(result.receiptId, "receipt-tx-node-10");
  const firstPrepare = first.events.find((entry) => entry[0] === "server:prepare");
  const secondPrepare = restarted.events.find((entry) => entry[0] === "server:prepare");
  assert.equal(
    firstPrepare[2].idempotency_key,
    secondPrepare[2].idempotency_key,
  );
  assert.equal(first.state.prepareResults.size, 1);
  assert.equal(first.state.sessionStore.values.size, 0);
});

test("double finalize and status response loss never rolls back and restart recovers migrated receipt", async () => {
  const first = harness({
    finalizeResponseLoss: true,
    statusResponseLossCount: 2,
  });
  const owner = node(11);
  await assert.rejects(
    first.coordinator.importReplace(owner, "legacy", { explicitReexport: true }),
    /SYNTHETIC_STATUS_RESPONSE_LOSS/,
  );
  assert.match(owner.protected, /^COMMITTED:/);
  assert(!first.events.some((entry) => entry[0] === "server:cancel"));
  assert(!first.events.some((entry) => entry[0] === "restore"));
  const persisted = JSON.parse([...first.state.sessionStore.values.values()][0]);
  assert.equal(persisted.phase, "finalize-ambiguous");
  assert.throws(
    () => first.coordinator.serializeWorkflow(node(110)),
    /PRIVACY_SMART_PROMPT_COORDINATOR_INVALID/,
  );
  assert.throws(
    () => first.coordinator.markEditorMutation(owner),
    /PRIVACY_SMART_PROMPT_COORDINATOR_INVALID/,
  );
  await assert.rejects(
    first.coordinator.saveWorkflow(node(111), async () => "must-not-save"),
    /PRIVACY_SMART_PROMPT_COORDINATOR_INVALID/,
  );

  const restarted = harness({ sharedState: first.state });
  const restartedOwner = node(11);
  restartedOwner.protected = owner.protected;
  const recovered = await restarted.coordinator.recoverPendingImport(
    restartedOwner, "import-replace",
  );
  assert.equal(recovered.disposition, "migrated");
  assert.equal(recovered.receiptId, "receipt-tx-node-11");
  assert.equal(restartedOwner.protected, owner.protected);
  assert(!restarted.events.some((entry) => entry[0] === "server:cancel"));
  assert(!restarted.events.some((entry) => entry[0] === "restore"));
  assert.equal(first.state.sessionStore.values.size, 0);
});

test("cancel response loss never performs an unacknowledged local restore", async () => {
  const { coordinator, events, state } = harness({
    applyFailure: true,
    cancelResponseLossCount: 1,
  });
  const owner = node(12);
  await assert.rejects(
    coordinator.importReplace(owner, "legacy", { explicitReexport: true }),
    /SYNTHETIC_CANCEL_RESPONSE_LOSS/,
  );
  assert(!events.some((entry) => entry[0] === "restore"));
  assert(!events.some((entry) => entry[0] === "server:rollback-ack"));
  assert.equal(state.sessionStore.values.size, 1);
  assert.throws(
    () => coordinator.serializeWorkflow(node(120)),
    /PRIVACY_SMART_PROMPT_COORDINATOR_INVALID/,
  );
});

test("pending import blocks serialization and activation inventory remains all-at-once", async () => {
  assert(SMART_PROMPT_FINAL_ATOMIC_SWITCH.length >= 8);
  assert(SMART_PROMPT_FINAL_ATOMIC_SWITCH.every((entry) => Object.isFrozen(entry)));
});
