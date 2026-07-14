import assert from "node:assert/strict";
import test from "node:test";

import {
  SMART_PROMPT_IMPORT_MERGE_OPERATION,
  SMART_PROMPT_IMPORT_REPLACE_OPERATION,
  createSmartPromptImportExportAdapter,
} from "../web/js/smart_prompt_import_export_adapters.js";


class MemoryStore {
  constructor() { this.values = new Map(); }
  get length() { return this.values.size; }
  key(index) { return [...this.values.keys()][index] ?? null; }
  getItem(key) { return this.values.has(key) ? this.values.get(key) : null; }
  setItem(key, value) { this.values.set(key, String(value)); }
  removeItem(key) { this.values.delete(key); }
}

function harness({ losePrepareResponse = false } = {}) {
  const calls = [];
  const store = new MemoryStore();
  let ids = 0;
  let remainingPrepareLosses = losePrepareResponse ? 1 : 0;
  const preparedByKey = new Map();
  const workflowHandle = {
    async settle(reason) { calls.push(["settle", reason]); },
    workflowProjection(owner) { return owner.protected; },
    async invoke(operation, payload) {
      calls.push(["invoke", operation, structuredClone(payload)]);
      if (payload.phase === "prepare") {
        const requestKey = `${operation}:${payload.owner_id}:${payload.idempotency_key}`;
        let result = preparedByKey.get(requestKey);
        if (!result) {
          result = {
            state: { privacyMode: payload.destination_private },
            protectedValue: `NEXT:${ownerFrom(payload.owner_id)}`,
            transactionId: `hp-external-${payload.owner_id}`,
            resumeToken: `hp-resume-${payload.owner_id}`,
            bindingId: `binding-${operation}`,
            disposition: "prepared",
          };
          preparedByKey.set(requestKey, result);
        }
        if (remainingPrepareLosses > 0) {
          remainingPrepareLosses -= 1;
          throw new Error("SYNTHETIC_RESPONSE_LOSS");
        }
        return structuredClone(result);
      }
      if (payload.phase === "reexport") return { filename: "export.json", text: "{}", digest: "d".repeat(64) };
      if (payload.phase === "finalize") return { receiptId: "hp-receipt-1", disposition: "migrated" };
      if (payload.phase === "cancel") return { disposition: "rollback-required", originalSnapshot: "ORIGINAL" };
      if (payload.phase === "rollback-ack") return { disposition: "rolled-back" };
      return { disposition: "prepared" };
    },
  };
  const productBridge = {
    readDestinationPrivate(owner) { return owner.private; },
    async downloadExport() {},
    exportedAt() { return "2026-07-13T12:00:00Z"; },
  };
  const adapter = createSmartPromptImportExportAdapter({
    workflowHandle, productBridge, sessionStore: store,
    idFactory: () => `id-${++ids}`,
  });
  return { adapter, calls, store };
}

function ownerFrom(value) { return value.replace("node-", ""); }

test("prepare captures exact owner boundary and stores product-free recovery ids only", async () => {
  const { adapter, calls, store } = harness();
  const owner = { id: 11, private: true, protected: "EXACT:11" };
  assert.equal(await adapter.captureBoundary(owner), "EXACT:11");
  const result = await adapter.prepare(owner, SMART_PROMPT_IMPORT_REPLACE_OPERATION, "SYNTHETIC_RAW", {
    explicitReexport: true,
    destinationSnapshot: "EXACT:11",
    destinationPrivate: true,
  });
  assert.equal(result.session.transactionId, "hp-external-node-11");
  const persisted = [...store.values.values()].join("\n");
  assert.doesNotMatch(persisted, /SYNTHETIC_RAW|EXACT:11|protectedValue|state/);
  assert.match(persisted, /hp-external-node-11/);
  assert.deepEqual(calls[0], ["settle", "manual-save"]);
  assert.equal(calls[1][2].destination_snapshot, "EXACT:11");
});

test("two owners and operations retain isolated capabilities", async () => {
  const { adapter, store } = harness();
  const first = { id: 21, private: true, protected: "A" };
  const second = { id: 22, private: false, protected: "B" };
  await adapter.prepare(first, SMART_PROMPT_IMPORT_REPLACE_OPERATION, "{}", {
    destinationSnapshot: "A", destinationPrivate: true,
  });
  await adapter.prepare(second, SMART_PROMPT_IMPORT_MERGE_OPERATION, "{}", {
    destinationSnapshot: "B", destinationPrivate: false,
  });
  assert.equal(store.values.size, 2);
  assert.notEqual([...store.values.keys()][0], [...store.values.keys()][1]);
});

test("prepare response loss retains only the idempotency key for deterministic retry", async () => {
  const { adapter, calls, store } = harness({ losePrepareResponse: true });
  const owner = { id: 31, private: true, protected: "BOUNDARY" };
  await assert.rejects(adapter.prepare(owner, SMART_PROMPT_IMPORT_REPLACE_OPERATION, "{}", {
    destinationSnapshot: "BOUNDARY", destinationPrivate: true,
  }), /SYNTHETIC_RESPONSE_LOSS/);
  const persisted = JSON.parse([...store.values.values()][0]);
  assert.equal(persisted.idempotencyKey, "request-id-1");
  assert.equal(persisted.transactionId, null);
  assert.equal(calls[0][2].idempotency_key, "request-id-1");
  const recovered = await adapter.prepare(
    owner,
    SMART_PROMPT_IMPORT_REPLACE_OPERATION,
    "{}",
    { destinationSnapshot: "BOUNDARY", destinationPrivate: true },
  );
  assert.equal(recovered.session.transactionId, "hp-external-node-31");
  assert.equal(recovered.session.resumeToken, "hp-resume-node-31");
  assert.equal(calls[1][2].idempotency_key, "request-id-1");
});

test("reexport, finalize, cancel and rollback ack send strict phase payloads", async () => {
  const { adapter, calls, store } = harness();
  const owner = { id: 41, private: true, protected: "A" };
  const prepared = await adapter.prepare(owner, SMART_PROMPT_IMPORT_REPLACE_OPERATION, "{}", {
    destinationSnapshot: "A", destinationPrivate: true,
  });
  const reexport = await adapter.reexport(owner, SMART_PROMPT_IMPORT_REPLACE_OPERATION, prepared.session, "B", true);
  const receipt = await adapter.finalize(owner, SMART_PROMPT_IMPORT_REPLACE_OPERATION, prepared.session, "B", true, reexport.digest);
  assert.equal(receipt.receiptId, "hp-receipt-1");
  assert.equal(store.values.size, 0);
  assert.deepEqual(calls.slice(-2).map((entry) => entry[2].phase), ["reexport", "finalize"]);
});
