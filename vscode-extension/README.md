## COTproj VS Code Extension

Activity Bar:
- A COTproj icon appears in the VS Code activity bar. The **COTproj Actions** view lists buttons for the common tasks below.

Commands (Command Palette or COT Actions view):
- `COTproj: Launch Tk UI` — Opens the existing Tk UI (`ui.py`) in a VS Code terminal.
- `COTproj: Pre-generate QL Queries` — Runs the Python bridge to create query files in `cli_tool/generated_ql_queries`.
- `COTproj: Create CodeQL Database` — Wraps `codeql database create` with optional build command.
- `COTproj: Run CodeQL Analysis` — Runs the regexp queries, converts to SARIF, and merges into `res.sarif`.
- `COTproj: Load SARIF and Show Diagnostics` — Load a `res.sarif` (or any SARIF) and annotate files with diagnostics.
- `COTproj: Choose Workspace/Codebase` — Pick the active codebase folder (also available from the Codebase section).

Configuration keys (`File → Preferences → Settings → Extensions → COT`):
- `cot.pythonPath` — Python executable to use (default `python3`).
- `cot.defaultOutputDir` — Optional default output folder for analysis/report outputs.

Notes:
- The extension shells out to `python_bridge.py` so it reuses the existing Python logic. Keep the extension folder inside the repository so relative imports resolve.
- The COTproj output channel shows detailed logs and JSON payloads from the bridge.
- After `Run CodeQL Analysis` (or manual `Load SARIF`), issues from `res.sarif` are surfaced as VS Code diagnostics (squiggles + Problems panel) for the current workspace.
- Files with SARIF issues are tinted red in the VS Code explorer (via decorations) so they’re easy to spot.
- CodeQL DB creation now defaults to placing databases outside the source tree (e.g., `../codeql-dbs/<project>-db`) and will refuse paths inside the source to avoid accidental source modifications.
- The sidebar now includes Codebase, Overview, Actions, and Rules sections with quick navigation; issue lists and buttons are accessible without typing paths (folder pickers are used). Overview shows loaded SARIF info and algorithm-grouped findings.
