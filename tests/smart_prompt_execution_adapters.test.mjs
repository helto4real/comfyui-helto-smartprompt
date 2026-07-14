import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

import {
  SMART_PROMPT_EXECUTION_PROJECTION,
  createSmartPromptExecutionAdapter,
} from "../web/js/smart_prompt_execution_adapters.js";


test("execution prepares one settled generation and writes only the protected reference", async () => {
  const node = { id: 7 };
  const reference = { schema: "helto.private-execution-reference", grant: "synthetic" };
  let settlements = 0;
  let prepareCalls = 0;
  let written = null;
  const adapter = createSmartPromptExecutionAdapter({
    workflowHandle: {
      runWithSnapshot: async (reason, operation) => {
        settlements += 1;
        assert.equal(reason, "queue");
        return operation();
      },
    },
    executionHandle: {
      prepare: async (owner, projection) => {
        prepareCalls += 1;
        assert.equal(owner, node);
        assert.equal(projection, SMART_PROMPT_EXECUTION_PROJECTION);
        return reference;
      },
    },
    productBridge: {
      writeExecutionInputs: async (owner, prepared) => { written = [owner, prepared]; },
      clearExecutionInputs: () => {},
    },
  });

  assert.equal(await adapter.prepareNode(node), reference);
  assert.equal(settlements, 1);
  assert.equal(prepareCalls, 1);
  assert.deepEqual(written, [node, reference]);
});


test("locked session clears prepared inputs without a fallback", () => {
  let clears = 0;
  const adapter = createSmartPromptExecutionAdapter({
    workflowHandle: { runWithSnapshot: async () => null },
    executionHandle: { prepare: async () => null },
    productBridge: {
      writeExecutionInputs: async () => {},
      clearExecutionInputs: () => { clears += 1; },
    },
  });
  adapter.onPrivacySessionChange({ state: "locked" });
  adapter.onPrivacySessionChange({ state: "ready" });
  assert.equal(clears, 1);
});


test("S3 contains no unkeyed token, hash, fallback, transport, or live import", () => {
  const source = fs.readFileSync(
    new URL("../web/js/smart_prompt_execution_adapters.js", import.meta.url),
    "utf8",
  );
  const live = fs.readFileSync(
    new URL("../web/js/smart_prompt_manager.js", import.meta.url),
    "utf8",
  );
  for (const forbidden of [
    "spm-cache-v1:",
    "sha256",
    "crypto.subtle",
    "fetch(",
    "privacyPost(",
    "registerExtension(",
    "import(",
  ]) {
    assert.equal(source.toLowerCase().includes(forbidden.toLowerCase()), false, forbidden);
  }
  assert.equal(live.includes("smart_prompt_execution_adapters.js"), false);
});
