// Smart Prompt S3 execution coordinator. Shared handles own snapshot
// settlement, protected references, grants, session identity, and RAM cache.

export const SMART_PROMPT_EXECUTION_PROJECTION = "resolve-prompt";

const INVALID = "PRIVACY_SMART_PROMPT_EXECUTION_INVALID";

function fail() {
  throw new Error(INVALID);
}

function required(owner, name) {
  const candidate = owner?.[name];
  if (typeof candidate !== "function") fail();
  return candidate.bind(owner);
}

export function createSmartPromptExecutionAdapter({
  workflowHandle,
  executionHandle,
  productBridge,
} = {}) {
  const runWithSnapshot = required(workflowHandle, "runWithSnapshot");
  const prepare = required(executionHandle, "prepare");
  const writeExecutionInputs = required(productBridge, "writeExecutionInputs");
  const clearExecutionInputs = required(productBridge, "clearExecutionInputs");

  return Object.freeze({
    async prepareNode(node) {
      if (!node || typeof node !== "object" || node.id === undefined) fail();
      const prepared = await runWithSnapshot("queue", () => (
        prepare(node, SMART_PROMPT_EXECUTION_PROJECTION)
      ));
      if (!prepared || typeof prepared !== "object") fail();
      await writeExecutionInputs(node, prepared);
      return prepared;
    },
    onPrivacySessionChange(snapshot) {
      if (snapshot?.state === "ready" || snapshot?.state === "unlocked") return;
      clearExecutionInputs();
    },
  });
}
