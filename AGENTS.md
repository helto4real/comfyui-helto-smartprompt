# AGENTS.md

Guidance for coding agents working on this ComfyUI custom node repository.

## Project

This repo implements the **Smart Prompt Manager** custom node for ComfyUI.

Core files:

- `nodes.py`: ComfyUI backend node and HTTP privacy routes.
- `resolver.py`: deterministic variable resolution.
- `schema.py`: state defaults, normalization, and merge helpers.
- `privacy.py`: local AES-GCM workflow encryption helpers.
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

Privacy mode encrypts `spm_data` using a local key file:

- key path: `config/privacy_key.json`
- algorithm: AES-256-GCM via Python `cryptography`
- encrypted workflows cannot be recovered without the matching key

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
