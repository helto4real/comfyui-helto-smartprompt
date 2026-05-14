# ComfyUI Helto Prompts

`Smart Prompt Manager` is a ComfyUI custom node for reusable prompts with per-node prompt libraries, folders, search, deterministic randomized variables, copy/paste portability, import/export, and a practical visual editor.

The first version deliberately uses a robust hybrid editor: a normal textarea for editing, a highlighted preview below it, hover previews for variables, and autocomplete attached to the textarea.

## Installation

Clone or copy this repository into your ComfyUI `custom_nodes` directory:

```bash
cd ComfyUI/custom_nodes
git clone <this-repository-url> comfyui-helto-prompts
```

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

## Creating Prompts

Use the **Prompt Library** section to add, duplicate, delete, and select prompts. Each prompt stores:

- title
- prompt text
- description
- folder
- tags
- favorite flag
- lock flag
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

## Seed And Reroll

`seed` and `reroll` are normal node inputs/widgets.

- Same prompt, variables, seed, and reroll produce the same `resolved_prompt`.
- Change `reroll` or press **Reroll** to get a different random selection.
- Fixed variables ignore random seed and reroll.

## Folders And Search

Folders have stable IDs and editable names. Deleting a folder moves prompts to **Unsorted**. Prompts and folders can also be marked hidden, which hides the selected prompt preview in the node until the mouse is hovering over the node.

Virtual folders:

- `All`
- `Unsorted`
- `Favorites`

Search is live and case-insensitive. It checks prompt title, text, folder name, tags, and description. Search applies inside the selected folder, or globally when `All` is selected.

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

Buttons in the editor support:

- **Copy resolved**: copies only the current resolved prompt as plain text
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

## Known Limitations

- Prompt history is not included in v1.
- The editor is not a full rich text editor; this is intentional for ComfyUI compatibility.
- Autocomplete cursor positioning uses a practical popup placement instead of exact textarea caret geometry.
- The JavaScript UI mirrors backend resolution logic, but the Python backend remains the source of truth for actual node outputs.

## Development

Run tests from the repository root:

```bash
python -m unittest discover
```

Core modules:

- `resolver.py`: deterministic variable resolver
- `schema.py`: schema defaults, normalization, and import merge helpers
- `validation.py`: warning generation
- `nodes.py`: ComfyUI node class
- `web/js/smart_prompt_manager.js`: browser UI extension
