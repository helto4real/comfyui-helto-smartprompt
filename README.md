# ComfyUI Helto Prompts

`Smart Prompt Manager` is a ComfyUI custom node for reusable prompts with per-node prompt libraries, folders, search, deterministic randomized variables, copy/paste portability, import/export, hidden/private previews, and a practical visual editor.

The node uses a robust hybrid editor instead of a fragile rich text editor: a normal textarea for editing, a highlighted preview below it, hover previews for variables, and autocomplete attached to the textarea. Prompt, folder, and variable editing now happens in popup windows so the node itself can stay compact.

## Installation

Clone or copy this repository into your ComfyUI `custom_nodes` directory:

```bash
cd ComfyUI/custom_nodes
git clone https://github.com/helto4real/comfyui-helto-smartprompt comfyui-helto-smartprompt
```

Install the node's Python dependencies with the same interpreter that runs ComfyUI:

```bash
cd ..
python -m pip install -r custom_nodes/comfyui-helto-smartprompt/requirements.txt
```

If ComfyUI uses a virtual environment or embedded Python, replace `python` with that interpreter. ComfyUI Manager installations handle the requirements step automatically.

Restart ComfyUI. The node appears under:

```text
Helto/Prompt -> Smart Prompt Manager
```

## Outputs

The node returns standard ComfyUI strings:

- `resolved_prompt`: the final prompt after variable resolution
- `raw_prompt`: the original unresolved prompt text
- `prompt_name`: selected prompt title
- `variables_json`: all variable definitions, variables used by the selected prompt, and used names
- `selected_values_json`: the selected value for each variable in the current generation
- `warnings_json`: missing variables, variables used, and warnings

## UI Overview

The main node shows a compact prompt library, the selected prompt summary, highlighted/resolved previews, import/export, and validation warnings.

The top row uses icon buttons. Hover an icon to see its tooltip:

- edit prompts
- edit folders
- edit variables
- reroll variables

The top row also includes **Privacy mode**. Checkboxes have tooltips; the visible labels are kept for readability, while the tooltip gives the exact behavior.

## Creating And Editing Prompts

Use the **Edit prompts** icon button to open the prompt editor window. In that window you can:

- add a new prompt
- duplicate the current prompt
- delete a prompt
- select an existing prompt
- edit title, folder, tags, description, and prompt text
- mark a prompt as favorite, locked, or hidden
- copy the resolved prompt or prompt JSON

When you add a new prompt, it starts as a draft. It is only added to the library and selected when you press **Done**. **Close** discards an unsaved draft.

The edit prompt window includes a folder filter above search. New prompts use the selected real folder as their default folder, or **Unsorted** when that filter is selected. The prompt list also has hover previews showing prompt text, variables, resolved preview, and warnings.

Each prompt stores:

- title
- prompt text
- description
- folder
- tags
- favorite flag
- lock flag
- hidden preview flag
- created and updated timestamps

Prompt state is saved inside the node's `spm_data` widget, so two node instances can have completely different libraries and both survive workflow save/load.

## Variables

Variables use double braces:

```text
A {{mood}} cinematic portrait of {{character}} in {{lighting}}.
```

Variable names may contain letters, numbers, underscores, and hyphens. Spaces are invalid.

Example variables:

```text
mood:
- dreamy
- melancholic
- dramatic

character:
- cyberpunk detective
- medieval knight
- astronaut

lighting:
- golden hour
- neon rim light
- soft studio light
```

Supported modes:

- `random`: picks one value deterministically from `seed`, `reroll`, and variable name
- `fixed`: uses `fixedValue`, then fallback, then the first value
- `cycle`: uses `(cycleState[name] + reroll) % number_of_values`

Repeated uses of the same variable in one prompt resolve to the same value. Missing variables keep the original `{{token}}` and produce a warning instead of crashing.

Use the **Edit variables** icon button to open the variable editor window. Variable rows include name, mode, values, fixed value, fallback, description, and a remove icon.

## Seed And Reroll

`seed` and `reroll` are normal node inputs/widgets.

- Same prompt, variables, seed, and reroll produce the same `resolved_prompt`.
- Change `reroll` or press the **Reroll variables** icon to get a different random selection.
- Fixed variables ignore random seed and reroll.

## Folders And Search

Use the **Edit folders** icon button to open the folder editor window. Folders have stable IDs and editable names. Deleting a folder moves prompts to **Unsorted**.

Folders can be marked hidden. When a folder is hidden, prompts in that folder have their titles, folder labels, prompt previews, and resolved previews masked in the main node until the mouse is hovering over the node.

Virtual folders:

- `All`
- `Unsorted`
- `Favorites`

Search is live and case-insensitive. It checks prompt title, text, folder name, tags, and description. Search applies inside the selected folder, or globally when `All` is selected. The edit prompt window has its own folder filter and search input for finding prompts to edit in long libraries.

## Hidden Previews

Prompts and folders can be marked hidden.

When a prompt is hidden, or when it belongs to a hidden folder, the main node masks:

- selected prompt title
- selected folder/tag summary
- highlighted raw prompt preview
- resolved prompt preview
- prompt titles and folder labels in the main prompt list
- prompt-list hover preview text while the node is not hovered

Hover over the node to reveal the hidden information. The prompt editor popup still shows the prompt normally because opening it is an explicit edit action.

## Privacy Mode

Hidden previews only affect what is visible on screen. **Privacy mode** protects saved workflow JSON by encrypting the node's prompt library before it is stored in `spm_data`.

When Privacy mode is enabled:

- prompt library data is stored in the workflow as an AES-256-GCM encrypted envelope with schema `helto.smart-prompt-manager`
- encryption uses the shared `helto-privacy` keystore at `~/.config/helto/privacy_keystore.json`
- one shared unlock covers Helto node packs in the same ComfyUI origin
- workflow reload decrypts the library through the local ComfyUI backend after the shared privacy dialog unlocks or creates the keystore
- the key and session token are never written into the workflow, exports, copy/paste JSON, or README examples

Back up the shared Helto privacy keystore privately. If it is lost or the password is unavailable, encrypted workflows cannot be decrypted. Encrypted workflows written by older Smart Prompt Manager privacy schemas are not migrated by this version; they show a locked/incompatible state and can be reset from the node UI. Plaintext workflows still load normally.

Privacy mode protects against accidentally sharing clear-text prompts in workflow files. It does not protect against someone with access to the local ComfyUI machine, browser session, Python process, or node outputs during execution.

## Editor, Highlighting, And IntelliSense

The prompt editor is a real textarea. Below it, the rendered preview highlights variables:

- defined variables use normal variable styling
- undefined or invalid variables use warning styling
- hovering a variable shows values, mode, fallback, selected value, and warnings

Autocomplete opens when typing inside a `{{partial` token. Suggestions are sorted alphabetically and filtered case-insensitively, with prefix matches first.

Keyboard shortcuts:

- `Ctrl+n`: next suggestion
- `Ctrl+p`: previous suggestion
- `Ctrl+y`: accept suggestion and insert `{{variable_name}}`
- `Escape`: close suggestions

The shortcut definitions live near the top of `web/js/smart_prompt_manager.js` so they are easy to change if a browser or platform conflict appears.

## Copy And Paste

Icon buttons in the node and editor support:

- **Copy resolved prompt**: copies only the current resolved prompt as plain text
- **Copy prompt JSON**: copies the selected prompt plus required variable definitions
- **Paste prompt JSON**: imports copied prompt JSON into the current node instance

If clipboard access is unavailable, the JSON/text is placed in the fallback textbox in **Import / Export**.

Prompt JSON contains:

```json
{
  "version": 1,
  "prompt": {
    "title": "Cinematic portrait",
    "text": "A {{mood}} portrait of {{character}}",
    "tags": ["portrait"],
    "description": "",
    "folderName": "Portraits"
  },
  "variablesUsed": ["mood", "character"],
  "variables": {
    "mood": {
      "mode": "random",
      "values": ["dreamy", "dramatic"],
      "fixedValue": null,
      "fallback": "dreamy",
      "description": ""
    }
  }
}
```

When pasting, missing variables are added. Existing variables are reused if identical. Conflicting variables are renamed with a suffix and prompt tokens are rewritten.

## Import And Export

Use **Export library** to copy the whole node library as JSON. Use **Import merge** or **Import replace** with JSON in the fallback textbox.

Library schema:

```json
{
  "version": 1,
  "selectedFolderId": "all",
  "selectedPromptId": "prompt1",
  "privacyMode": false,
  "folders": [{ "id": "folder1", "name": "Portraits", "hidden": false }],
  "prompts": [
    {
      "id": "prompt1",
      "title": "Cinematic portrait",
      "text": "A {{mood}} portrait of {{character}}, {{lighting}}",
      "folderId": "folder1",
      "tags": ["portrait", "cinematic"],
      "description": "",
      "favorite": false,
      "locked": false,
      "hidden": false,
      "createdAt": "2026-01-01T12:00:00Z",
      "updatedAt": "2026-01-01T12:00:00Z"
    }
  ],
  "variables": {
    "mood": {
      "mode": "random",
      "values": ["dreamy", "melancholic", "dramatic"],
      "fixedValue": null,
      "fallback": "cinematic",
      "description": ""
    }
  },
  "cycleState": {},
  "ui": { "collapsedSections": {} }
}
```

Malformed JSON is reported in the UI and backend warnings. Merge import avoids ID collisions and keeps existing conflicting variables.

When Privacy mode is enabled, the saved workflow and full-library export contain an encrypted envelope instead of this clear-text schema. Plaintext library replacement preserves the destination node's current Privacy mode; use the Privacy mode switch and its confirmation if you intend to store the imported library in clear text. Copying a resolved prompt or prompt JSON remains an explicit clear-text clipboard action.

## Known Limitations

- Prompt history is not included in v1.
- The editor is not a full rich text editor; this is intentional for ComfyUI compatibility.
- Autocomplete cursor positioning uses a practical popup placement instead of exact textarea caret geometry.
- Privacy mode requires `helto-privacy` and the Python `cryptography` package.
- The JavaScript UI mirrors backend resolution logic, but the Python backend remains the source of truth for actual node outputs.

## Development

Run tests from the repository root:

```bash
python -m pip install -r requirements.txt
node --check web/js/smart_prompt_manager.js
python -m unittest discover
```

Use the same Python interpreter that runs the target ComfyUI installation.

Core modules:

- `resolver.py`: deterministic variable resolver
- `schema.py`: schema defaults, normalization, and import merge helpers
- `privacy.py`: local AES-GCM workflow encryption helpers
- `validation.py`: warning generation
- `nodes.py`: ComfyUI node class
- `web/js/smart_prompt_manager.js`: browser UI extension
