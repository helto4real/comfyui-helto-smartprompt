# AGENTS.md

Guidance for coding agents working on this ComfyUI custom node repository.

## Project

This repo implements the **Smart Prompt Manager** custom node for ComfyUI.

Core files:

- `nodes.py`: ComfyUI backend node and HTTP privacy routes.
- `resolver.py`: deterministic variable resolution.
- `schema.py`: state defaults, normalization, and merge helpers.
- `managed_privacy.py`: shared privacy profile declarations and workflow adapters.
- `managed_import_export.py`: managed private import/export and legacy migration.
- `managed_execution.py`: protected prompt resolution and execution adapters.
- `validation.py`: state warning generation.
- `web/js/smart_prompt_manager.js`: frontend extension and custom node UI.
- `tests/`: standard-library `unittest` tests.

## Development Rules

- Keep prompt state per node instance in `spm_data`.
- Preserve backward compatibility with existing plaintext workflow JSON.
- Do not store prompt libraries globally.
- Do not commit `config/`; it contains local privacy keys and is ignored by git.
- Use the textarea plus rendered preview approach. Avoid fragile rich text editor rewrites.
- Keep frontend changes robust inside ComfyUI: compact UI, defensive event handling, no external JS dependency unless truly needed.

## Privacy Mode

Privacy mode is owned by the shared `helto-privacy` runtime. The Smart Prompt
profile binds workflow serialization, execution, import/export, recovery, and
legacy readers to shared handles. Missing or mismatched shared runtime state
must block generically; do not add local crypto, token, route, retry, or
fallback policy.

Historical Smart Prompt v1 data is accepted only through the declared shared
legacy readers and explicit key-import/migration path. Never add a legacy
writer or silently replace unreadable encrypted bytes.

The repository has no local privacy codec. Keep all privacy mechanics in the
shared runtime and consumer adapters.

Never write the key into workflow JSON, exported prompt JSON, README examples, tests, or logs.

## Checks

Run these before handing work back:

```bash
node --check web/js/smart_prompt_manager.js
python -m unittest discover
```

The frontend is served by ComfyUI. Python route changes require restarting ComfyUI; browser refresh alone is not enough.

## Git

Remote:

```bash
origin git@github.com:helto4real/comfyui-helto-smartprompt.git
```

Keep commits focused and do not revert user changes unless explicitly asked.
