const vscode = require('vscode');
const { spawn } = require('child_process');
const path = require('path');
const fs = require('fs');
const { promises: fsp } = require('fs');

function getWorkspaceFolder() {
  return vscode.workspace.workspaceFolders && vscode.workspace.workspaceFolders.length
    ? vscode.workspace.workspaceFolders[0].uri.fsPath
    : undefined;
}

function activate(context) {
  const output = vscode.window.createOutputChannel('COTproj');
  const diagnostics = vscode.languages.createDiagnosticCollection('cot');
  const bridgePath = context.asAbsolutePath('python_bridge.py');
  const bridgeCwd = path.dirname(bridgePath);
  const decoratedFiles = new Set();
  const decorationEmitter = new vscode.EventEmitter();
  const diagStore = new Map(); // fsPath -> [{ diagnostic, originalText, range }]
  let lastSarifPath = null;
  let currentWorkspacePath = getWorkspaceFolder();
  let sarifSummary = { algCounts: new Map() };
  const statusItem = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left, 1000);
  statusItem.text = 'COTproj: idle';
  statusItem.show();
  const highlightDecoration = vscode.window.createTextEditorDecorationType({
    backgroundColor: 'rgba(255, 92, 92, 0.18)',
    border: '1px solid rgba(255, 92, 92, 0.4)',
    overviewRulerColor: 'rgba(255,92,92,0.8)',
    overviewRulerLane: vscode.OverviewRulerLane.Right,
    isWholeLine: false,
  });

  const getConfig = () => vscode.workspace.getConfiguration('cot');

  const getPythonPath = () => {
    const cfg = getConfig().get('pythonPath') || 'python3';
    return cfg.trim() || 'python3';
  };

  const ensureBridgeExists = () => {
    if (!fs.existsSync(bridgePath)) {
      throw new Error(`Bridge script not found at ${bridgePath}`);
    }
  };

  const pickFolder = async (title, defaultUri) => {
    const selection = await vscode.window.showOpenDialog({
      canSelectFiles: false,
      canSelectFolders: true,
      canSelectMany: false,
      openLabel: title,
      defaultUri: defaultUri && fs.existsSync(defaultUri) ? vscode.Uri.file(defaultUri) : undefined,
    });
    return selection && selection.length ? selection[0].fsPath : undefined;
  };

  const pickFile = async (title, defaultUri, filters) => {
    const selection = await vscode.window.showOpenDialog({
      canSelectFiles: true,
      canSelectFolders: false,
      canSelectMany: false,
      openLabel: title,
      defaultUri: defaultUri && fs.existsSync(defaultUri) ? vscode.Uri.file(defaultUri) : undefined,
      filters,
    });
    return selection && selection.length ? selection[0].fsPath : undefined;
  };

  const notNullOrEmpty = (s) => typeof s === 'string' && s.trim().length > 0;

  const runBridge = (subcommand, extraArgs = []) => {
    ensureBridgeExists();
    return new Promise((resolve, reject) => {
      const python = getPythonPath();
      const args = [bridgePath, subcommand, ...extraArgs];
      statusItem.text = `COTproj: ${subcommand}...`;
      output.show(true);
      output.appendLine(`$ ${python} ${args.map((a) => (a.includes(' ') ? `"${a}"` : a)).join(' ')}`);

      const child = spawn(python, args, { cwd: bridgeCwd });
      let stdout = '';
      let stderr = '';

      child.stdout.on('data', (data) => {
        const text = data.toString();
        stdout += text;
        output.append(text);
      });

      child.stderr.on('data', (data) => {
        const text = data.toString();
        stderr += text;
        output.append(text);
      });

      child.on('close', (code) => {
        statusItem.text = 'COTproj: idle';
        if (!stdout.trim() && stderr.trim()) {
          output.appendLine(`Bridge exited with code ${code}`);
        }
        let parsed;
        const combined = stdout.trim();
        const firstBrace = combined.indexOf('{');
        const lastBrace = combined.lastIndexOf('}');
        if (firstBrace !== -1 && lastBrace !== -1 && lastBrace >= firstBrace) {
          const maybeJson = combined.slice(firstBrace, lastBrace + 1);
          try {
            parsed = JSON.parse(maybeJson);
          } catch (err) {
            parsed = undefined;
          }
        }
        if (code === 0 && parsed && parsed.ok) {
          resolve(parsed.data);
        } else {
          const msg = parsed && parsed.error ? parsed.error : stderr || stdout || `Bridge exited with code ${code}`;
          reject(new Error(msg));
        }
      });
    });
  };

  const runBridgeInTerminal = (subcommand, extraArgs = []) => {
    ensureBridgeExists();
    const python = getPythonPath();
    const args = [bridgePath, subcommand, ...extraArgs];
    const cmd = `${python} ${args.map((a) => (a.includes(' ') ? `"${a}"` : a)).join(' ')}`;
    const terminal = vscode.window.createTerminal({
      name: 'COTproj',
      cwd: bridgeCwd,
    });
    output.show(true);
    output.appendLine(`$ ${cmd}`);
    terminal.sendText(cmd);
    terminal.show(true);
  };

  const showError = (err) => {
    output.appendLine(String(err));
    vscode.window.showErrorMessage(String(err));
  };

  const resolveFsPath = (uriLike) => {
    if (!uriLike) return undefined;
    if (uriLike.startsWith('file://')) {
      return vscode.Uri.parse(uriLike).fsPath;
    }
    if (uriLike.startsWith('file:')) {
      try {
        return vscode.Uri.file(uriLike.replace('file:', '')).fsPath;
      } catch {
        return undefined;
      }
    }
    if (path.isAbsolute(uriLike)) return uriLike;
    const workspaceRoot = getWorkspaceFolder();
    return workspaceRoot ? path.join(workspaceRoot, uriLike) : undefined;
  };

  const getTextForRange = async (fsPath, range) => {
    const uri = vscode.Uri.file(fsPath);
    const openDoc = vscode.workspace.textDocuments.find((d) => d.uri.fsPath === fsPath);
    try {
      const doc = openDoc || (await vscode.workspace.openTextDocument(uri));
      return doc.getText(range);
    } catch {
      try {
        const content = await fsp.readFile(fsPath, 'utf8');
        const lines = content.split(/\r?\n/);
        const sliceLines = lines.slice(range.start.line, range.end.line + 1);
        if (!sliceLines.length) return '';
        sliceLines[0] = sliceLines[0].slice(range.start.character);
        sliceLines[sliceLines.length - 1] = sliceLines[sliceLines.length - 1].slice(0, range.end.character);
        return sliceLines.join('\n');
      } catch {
        return '';
      }
    }
  };

  const getOffsetsForRange = async (fsPath, range) => {
    const uri = vscode.Uri.file(fsPath);
    const openDoc = vscode.workspace.textDocuments.find((d) => d.uri.fsPath === fsPath);
    try {
      const doc = openDoc || (await vscode.workspace.openTextDocument(uri));
      const start = doc.offsetAt(range.start);
      const end = doc.offsetAt(range.end);
      return { start, end, doc };
    } catch {
      try {
        const content = await fsp.readFile(fsPath, 'utf8');
        const lines = content.split(/\r?\n/);
        let offset = 0;
        for (let i = 0; i < range.start.line; i++) {
          offset += lines[i].length + 1;
        }
        const start = offset + range.start.character;
        let offsetEnd = 0;
        for (let i = 0; i < range.end.line; i++) {
          offsetEnd += lines[i].length + 1;
        }
        const end = offsetEnd + range.end.character;
        return { start, end, doc: null, content };
      } catch {
        return { start: 0, end: 0, doc: null };
      }
    }
  };

  const findSnippetNear = (doc, text, target, centerOffset, windowSize = 4000) => {
    if (!target || !target.length) return null;
    const total = text.length;
    const start = Math.max(0, centerOffset - Math.floor(windowSize / 2));
    const end = Math.min(total, centerOffset + Math.floor(windowSize / 2));
    const slice = text.slice(start, end);
    const idxInSlice = slice.indexOf(target);
    if (idxInSlice === -1) return null;
    const globalStart = start + idxInSlice;
    const globalEnd = globalStart + target.length;
    const startPos = doc.positionAt(globalStart);
    const endPos = doc.positionAt(globalEnd);
    const range = new vscode.Range(startPos, endPos);
    return { range, offset: globalStart };
  };

  const refreshHighlightsForEditor = (editor) => {
    if (!editor) return;
    const fsPath = editor.document.uri.fsPath;
    const entries = diagStore.get(fsPath) || [];
    const ranges = entries.map((e) => e.range);
    editor.setDecorations(highlightDecoration, ranges);
  };

  const refreshAllHighlights = () => {
    vscode.window.visibleTextEditors.forEach(refreshHighlightsForEditor);
  };

  const reanchorEntry = (entry, doc, contentChanges) => {
    const target = entry.originalText;
    if (!target) return null;
    let anchor = entry.anchorOffset ?? doc.offsetAt(entry.range.start);
    let affected = false;
    for (const change of contentChanges) {
      const delta = change.text.length - change.rangeLength;
      const changeStart = change.rangeOffset;
      const changeEnd = changeStart + change.rangeLength;
      if (changeEnd <= anchor) {
        anchor += delta;
      } else if (changeStart <= anchor + target.length && changeEnd >= anchor) {
        affected = true;
      }
    }
    const text = doc.getText();
    const found = findSnippetNear(doc, text, target, anchor, 2000);
    if (found) {
      const diag = new vscode.Diagnostic(found.range, entry.diagnostic.message, entry.diagnostic.severity);
      diag.code = entry.diagnostic.code;
      return { diagnostic: diag, range: found.range, originalText: entry.originalText, anchorOffset: found.offset, algorithm: entry.algorithm };
    }
    if (affected) {
      return null;
    }
    // Not affected and not found; keep range shifted to anchor
    const start = doc.positionAt(anchor);
    const end = doc.positionAt(anchor + target.length);
    const range = new vscode.Range(start, end);
    const diag = new vscode.Diagnostic(range, entry.diagnostic.message, entry.diagnostic.severity);
    diag.code = entry.diagnostic.code;
    return { diagnostic: diag, range, originalText: entry.originalText, anchorOffset: anchor, algorithm: entry.algorithm };
  };

  let updateDiagnosticsForFile = (fsPath, entries) => {
    if (!entries || !entries.length) {
      diagnostics.delete(vscode.Uri.file(fsPath));
      diagStore.delete(fsPath);
      decoratedFiles.delete(fsPath);
      decorationEmitter.fire();
      refreshAllHighlights();
      return;
    }
    diagnostics.set(vscode.Uri.file(fsPath), entries.map((e) => e.diagnostic));
    diagStore.set(fsPath, entries);
    decoratedFiles.add(fsPath);
    decorationEmitter.fire([vscode.Uri.file(fsPath)]);
    refreshAllHighlights();
  };

  const applySarifDiagnostics = async (sarifPath) => {
    try {
      diagnostics.clear();
      decoratedFiles.clear();
      diagStore.clear();
      sarifSummary = { algCounts: new Map(), safeAlternatives: [] };
      const content = await fsp.readFile(sarifPath, 'utf8');
      const sarif = JSON.parse(content);
      const runs = Array.isArray(sarif.runs) ? sarif.runs : [];
      const diagMap = new Map();
      const severityMap = {
        error: vscode.DiagnosticSeverity.Error,
        warning: vscode.DiagnosticSeverity.Warning,
        note: vscode.DiagnosticSeverity.Information,
        none: vscode.DiagnosticSeverity.Hint,
      };
      const toInt = (value, fallback) => {
        const num = Number(value);
        return Number.isFinite(num) ? num : fallback;
      };

      for (const run of runs) {
        const results = Array.isArray(run.results) ? run.results : [];
        for (const result of results) {
          const locations = Array.isArray(result.locations) ? result.locations : [];
          const msgText = result.message && result.message.text ? result.message.text : '';
          let algo = null;
          let alternative = null;
          msgText.split(/\r?\n/).forEach((line) => {
            const trimmed = line.trim();
            if (trimmed.toLowerCase().startsWith('algorithm:')) {
              algo = trimmed.split(':', 2)[1]?.trim() || null;
            } else if (trimmed.toLowerCase().startsWith('alternative:')) {
              alternative = trimmed.split(':', 2)[1]?.trim() || null;
            } else if (trimmed.toLowerCase().startsWith('vuln content:') && notNullOrEmpty(trimmed.split(':', 2)[1])) {
              const candidate = trimmed.split(':', 2)[1].trim();
              if (!algo) {
                algo = candidate;
              }
            }
          });
          if (!algo) {
            algo = result.ruleId || 'Uncategorized';
          }
          const algKey = algo || 'Uncategorized';
          sarifSummary.algCounts.set(algKey, (sarifSummary.algCounts.get(algKey) || 0) + 1);
          for (const loc of locations) {
            const phys = loc.physicalLocation;
            const artifact = phys && phys.artifactLocation;
            const region = phys && phys.region;
            const uri = artifact && (artifact.uri || artifact.uriBaseId);
            const fsPath = resolveFsPath(uri);
            if (!fsPath || !region || toInt(region.startLine, undefined) === undefined) {
              continue;
            }
            const startLine = Math.max(toInt(region.startLine, 1) - 1, 0);
            const startCol = Math.max(toInt(region.startColumn, 1) - 1, 0);
            const endLine = Math.max(toInt(region.endLine, region.startLine ?? 1) - 1, startLine);
            const endCol = Math.max(toInt(region.endColumn, region.startColumn ?? 1) - 1, startCol);
            const range = new vscode.Range(startLine, startCol, endLine, endCol);
            const message = result.message && result.message.text
              ? result.message.text
              : result.ruleId || 'SARIF issue';
            const severity = severityMap[String(result.level || '').toLowerCase()] ?? vscode.DiagnosticSeverity.Warning;
            const diag = new vscode.Diagnostic(range, message, severity);
            diag.code = result.ruleId;
            const key = fsPath;
            if (!diagMap.has(key)) {
              diagMap.set(key, []);
            }
            diagMap.get(key).push({ diagnostic: diag, range, originalText: null, anchorOffset: null, algorithm: algo });
            decoratedFiles.add(fsPath);
          }
        }
      }

      for (const [file, entries] of diagMap.entries()) {
        for (const entry of entries) {
          entry.originalText = await getTextForRange(file, entry.range);
          const offsets = await getOffsetsForRange(file, entry.range);
          entry.anchorOffset = offsets.start;
        }
        diagnostics.set(vscode.Uri.file(file), entries.map((e) => e.diagnostic));
        diagStore.set(file, entries);
      }
      decorationEmitter.fire(Array.from(decoratedFiles).map((f) => vscode.Uri.file(f)));
      refreshAllHighlights();
      output.appendLine(`Loaded diagnostics from ${sarifPath} (${diagMap.size} files).`);
      vscode.window.showInformationMessage(`COTproj SARIF applied: ${diagMap.size} file(s) annotated.`);
      statusItem.text = `COTproj: ${diagMap.size} file(s) annotated`;
    } catch (err) {
      diagnostics.clear();
      decoratedFiles.clear();
      diagStore.clear();
      decorationEmitter.fire();
      refreshAllHighlights();
      throw new Error(`Failed to load SARIF (${sarifPath}): ${err.message}`);
    }
  };

  const loadSarifCommand = vscode.commands.registerCommand('cot.loadSarif', async () => {
    try {
      const defaultDir = currentWorkspacePath || getWorkspaceFolder() || bridgeCwd;
      const selection = await pickFile('Load SARIF', defaultDir, { 'SARIF Files': ['sarif'], 'All Files': ['*'] });
      if (!selection) {
        return;
      }
      lastSarifPath = selection;
      await applySarifDiagnostics(selection);
      treeProvider.refresh();
    } catch (err) {
      showError(err);
    }
  });

  const launchGuiCommand = vscode.commands.registerCommand('cot.launchGui', async () => {
    try {
      const python = getPythonPath();
      const uiPath = path.resolve(bridgeCwd, '..', 'ui.py');
      if (!fs.existsSync(uiPath)) {
        throw new Error(`ui.py not found at ${uiPath}`);
      }
      const terminal = vscode.window.createTerminal({
        name: 'COTproj UI',
        cwd: path.dirname(uiPath),
      });
      terminal.sendText(`${python} "${uiPath}"`);
      terminal.show(true);
    } catch (err) {
      showError(err);
    }
  });

  const generateQueriesCommand = vscode.commands.registerCommand('cot.generateQueries', async () => {
    try {
      const data = await runBridge('generate-queries');
      const outputDir = path.dirname(data.generated[0]);
      vscode.window.showInformationMessage(`Queries generated: ${data.generated.length}. Output: ${outputDir}`);
    } catch (err) {
      showError(err);
    }
  });

  const createCodeqlDbCommand = vscode.commands.registerCommand('cot.createCodeqlDb', async () => {
    try {
      const workspace = currentWorkspacePath || getWorkspaceFolder();
      const sourceRoot = await pickFolder('Select source root for CodeQL DB', workspace);
      if (!sourceRoot) {
        vscode.window.showWarningMessage('Source root not provided.');
        return;
      }
      currentWorkspacePath = sourceRoot;

      const suggestedBase = workspace ? path.dirname(workspace) : path.dirname(sourceRoot);
      const suggestedName = `${path.basename(sourceRoot)}-db`;
      const suggestedDir = path.join(suggestedBase, 'codeql-dbs', suggestedName);

      const targetDir = await pickFolder('Select folder to create the CodeQL DB in (parent)', path.dirname(suggestedDir));
      if (!targetDir) {
        vscode.window.showWarningMessage('Database parent folder not selected.');
        return;
      }
      const dbName = await vscode.window.showInputBox({
        prompt: 'CodeQL DB folder name',
        value: path.basename(suggestedDir),
      });
      if (!dbName) {
        vscode.window.showWarningMessage('Database name not provided.');
        return;
      }
      const databasePath = path.join(targetDir, dbName);

      const insideSource = (() => {
        const rel = path.relative(sourceRoot, databasePath);
        return rel === '' || (!rel.startsWith('..') && !path.isAbsolute(rel));
      })();
      if (insideSource) {
        vscode.window.showErrorMessage('Choose a database path outside the source tree to avoid modifying sources.');
        return;
      }

      const buildOptions = [
        { label: 'None (skip build command)', command: '' },
        { label: 'make -j$(nproc)', command: 'make -j$(nproc)' },
        { label: 'cmake --build build', command: 'cmake --build build' },
        { label: 'ninja -C build', command: 'ninja -C build' },
        { label: 'Custom…', command: '__custom__' },
      ];

      let buildCommand = '';
      const pick = await vscode.window.showQuickPick(buildOptions, {
        placeHolder: 'Select an optional build command to pass to codeql database create',
      });
      if (!pick) {
        return;
      }
      if (pick.command === '__custom__') {
        const custom = await vscode.window.showInputBox({
          prompt: 'Enter custom build command (optional)',
          value: '',
        });
        buildCommand = custom || '';
      } else {
        buildCommand = pick.command;
      }

      const extra = ['--source-root', sourceRoot, '--database-path', databasePath];
      if (buildCommand) {
        extra.push('--build-command', buildCommand);
      }

      await vscode.window.withProgress(
        { location: vscode.ProgressLocation.Notification, title: 'Creating CodeQL database...', cancellable: false },
        async () => {
          runBridgeInTerminal('create-codeql-db', extra);
          vscode.window.showInformationMessage('CodeQL database creation started in terminal. See the COTproj terminal for live logs.');
        }
      );
    } catch (err) {
      showError(err);
    }
  });

  const runAnalysisCommand = vscode.commands.registerCommand('cot.runAnalysis', async () => {
    try {
      const database = await pickFolder('Select CodeQL database folder', currentWorkspacePath);
      if (!database) {
        vscode.window.showWarningMessage('Database not selected.');
        return;
      }
      const configuredOutput = getConfig().get('defaultOutputDir');
      const defaultOutput = configuredOutput && configuredOutput.trim().length
        ? configuredOutput.trim()
        : path.dirname(database);
      const outputDir = await pickFolder('Select output directory for SARIF/BQRS files', defaultOutput);
      const args = ['--database', database];
      if (outputDir) {
        args.push('--output-dir', outputDir);
      }
      runBridgeInTerminal('run-analysis', args);
      vscode.window.showInformationMessage('Analysis started in terminal. Use "Load SARIF" after it completes.');
    } catch (err) {
      showError(err);
    }
  });

  context.subscriptions.push(
    output,
    diagnostics,
    launchGuiCommand,
    generateQueriesCommand,
    createCodeqlDbCommand,
    runAnalysisCommand,
    loadSarifCommand
  );

  const actionItems = [
    { label: 'Pre-generate QL Queries', command: 'cot.generateQueries', description: 'Create/update query files', icon: new vscode.ThemeIcon('wand') },
    { label: 'Create CodeQL Database', command: 'cot.createCodeqlDb', description: 'Build CodeQL DB', icon: new vscode.ThemeIcon('database') },
    { label: 'Run CodeQL Analysis', command: 'cot.runAnalysis', description: 'Run queries + merge SARIF', icon: new vscode.ThemeIcon('beaker') },
    { label: 'Load SARIF', command: 'cot.loadSarif', description: 'Annotate workspace from res.sarif', icon: new vscode.ThemeIcon('cloud-download') },
  ];

  const severityOrder = ['error', 'warning', 'information', 'hint'];
  const severityIcon = {
    error: new vscode.ThemeIcon('error', new vscode.ThemeColor('list.warningForeground')),
    warning: new vscode.ThemeIcon('warning', new vscode.ThemeColor('list.warningForeground')),
    information: new vscode.ThemeIcon('info'),
    hint: new vscode.ThemeIcon('question'),
  };

  class CotTreeProvider {
    constructor() {
      this._onDidChangeTreeData = new vscode.EventEmitter();
      this.onDidChangeTreeData = this._onDidChangeTreeData.event;
    }
    refresh() {
      this._onDidChangeTreeData.fire();
    }
    getTreeItem(element) {
      if (element.type === 'section') {
        const item = new vscode.TreeItem(element.label, vscode.TreeItemCollapsibleState.Expanded);
        item.description = element.description;
        item.iconPath = element.icon;
        item.contextValue = 'cotSection';
        return item;
      }
      if (element.type === 'action') {
        const item = new vscode.TreeItem(element.label, vscode.TreeItemCollapsibleState.None);
        item.description = element.description;
        item.command = { command: element.command, title: element.label };
        item.contextValue = 'cotAction';
        item.iconPath = element.icon;
        return item;
      }
      if (element.type === 'file') {
        const item = new vscode.TreeItem(element.label, vscode.TreeItemCollapsibleState.Collapsed);
        item.description = element.description;
        item.iconPath = element.icon;
        item.tooltip = element.tooltip;
        item.contextValue = 'cotFile';
        return item;
      }
      if (element.type === 'issue') {
        const item = new vscode.TreeItem(element.label, vscode.TreeItemCollapsibleState.None);
        item.description = element.description;
        item.command = { command: 'cot.openIssue', title: 'Open Issue', arguments: [element] };
        item.iconPath = element.icon;
        item.tooltip = element.tooltip;
        item.contextValue = 'cotIssue';
        return item;
      }
      const item = new vscode.TreeItem(element.label || 'Unknown', element.collapsibleState || vscode.TreeItemCollapsibleState.None);
      item.description = element.description;
      item.tooltip = element.tooltip;
      item.iconPath = element.icon;
      if (element.command) {
        item.command = { command: element.command, title: element.label, arguments: element.arguments || [] };
      }
      return item;
    }
    getChildren(element) {
      if (!element) {
        return [
          { type: 'section', label: 'Overview', description: lastSarifPath ? `SARIF: ${path.basename(lastSarifPath)}` : 'No SARIF loaded', icon: new vscode.ThemeIcon('info') },
          { type: 'section', label: 'Codebase', description: currentWorkspacePath || 'No workspace chosen', icon: new vscode.ThemeIcon('folder-opened') },
          { type: 'section', label: 'Actions', icon: new vscode.ThemeIcon('rocket') },
          { type: 'section', label: 'Rules', icon: new vscode.ThemeIcon('list-selection') },
        ];
      }
      if (element.type === 'section' && element.label === 'Overview') {
        const counts = { total: 0 };
        const algMap = new Map();
        for (const [fsPath, entries] of diagStore.entries()) {
          counts.total += entries.length;
          for (const e of entries) {
            const alg = e.algorithm || 'Uncategorized';
            if (!algMap.has(alg)) algMap.set(alg, []);
            algMap.get(alg).push({ fsPath, entry: e });
          }
        }
        const items = [
          {
            type: 'summary',
            label: `Total: ${counts.total}`,
            description: lastSarifPath ? path.basename(lastSarifPath) : 'No SARIF loaded',
            icon: new vscode.ThemeIcon('list-selection'),
            tooltip: 'Total issues',
          },
        ];
        const algos = Array.from(algMap.entries()).map(([name, list]) => {
          const display = name === 'Uncategorized' ? 'Other' : name;
          return {
            type: 'alg',
            algorithm: name,
            count: list.length,
            icon: new vscode.ThemeIcon('flame'),
            tooltip: `${list.length} finding(s) for ${display}`,
            label: `${display}: ${list.length}`,
            issues: list,
            collapsibleState: vscode.TreeItemCollapsibleState.Collapsed,
          };
        });
        algos.sort((a, b) => b.count - a.count || a.label.localeCompare(b.label));
        items.push(...algos);
        return items;
      }
      if (element.type === 'section' && element.label === 'Codebase') {
        return [
          {
            type: 'summary',
            label: currentWorkspacePath ? path.basename(currentWorkspacePath) : 'Choose codebase…',
            description: currentWorkspacePath || 'Pick a folder',
            icon: new vscode.ThemeIcon('root-folder'),
            command: 'cot.pickWorkspace',
          },
        ];
      }
      if (element.type === 'section' && element.label === 'Actions') {
        return actionItems.map((a) => ({
          type: 'action',
          label: a.label,
          description: a.description,
          command: a.command,
          icon: a.icon || new vscode.ThemeIcon('run'),
        }));
      }
      if (element.type === 'section' && element.label === 'Rules') {
        const ruleCounts = new Map();
        for (const entries of diagStore.values()) {
          entries.forEach((e) => {
            const code = e.diagnostic.code || 'unknown';
            ruleCounts.set(code, (ruleCounts.get(code) || 0) + 1);
          });
        }
        const rules = Array.from(ruleCounts.entries()).map(([rule, count]) => ({
          type: 'summary',
          label: `${rule}`,
          description: `${count} finding(s)`,
          icon: new vscode.ThemeIcon('symbol-key'),
          tooltip: `${count} finding(s) for ${rule}`,
        }));
        rules.sort((a, b) => b.description.localeCompare(a.description));
        return rules;
      }
      if (element.type === 'alg') {
        const issues = element.issues || [];
        const items = issues.map((item, idx) => {
          const e = item.entry || item;
          const fsPath = item.fsPath || '';
          const sev =
            (e.diagnostic.severity === vscode.DiagnosticSeverity.Error && 'error') ||
            (e.diagnostic.severity === vscode.DiagnosticSeverity.Warning && 'warning') ||
            (e.diagnostic.severity === vscode.DiagnosticSeverity.Information && 'information') ||
            'hint';
          const loc = `L${e.range.start.line + 1}:C${e.range.start.character + 1}`;
          return {
            type: 'issue',
            key: `${fsPath}-${idx}`,
            fsPath,
            range: e.range,
            label: e.diagnostic.message.slice(0, 80) + (e.diagnostic.message.length > 80 ? '…' : ''),
            description: `${path.basename(fsPath)} • ${loc}`,
            icon: severityIcon[sev] || new vscode.ThemeIcon('warning'),
            tooltip: `${e.diagnostic.message}\n${fsPath}:${loc}`,
          };
        });
        items.sort((a, b) => a.description.localeCompare(b.description));
        return items;
      }
      return [];
    }
  }

  const treeProvider = new CotTreeProvider();
  const decorationProvider = {
    onDidChangeFileDecorations: decorationEmitter.event,
    provideFileDecoration(uri) {
      if (decoratedFiles.has(uri.fsPath)) {
        return {
          color: '#ff5c5c',
          tooltip: 'COTproj SARIF issue(s) in this file',
          badge: '●',
        };
      }
      return undefined;
    },
  };

  context.subscriptions.push(
    vscode.window.registerTreeDataProvider('cot.actions', treeProvider),
    vscode.window.registerFileDecorationProvider(decorationProvider),
    highlightDecoration,
    vscode.window.onDidChangeVisibleTextEditors(() => refreshAllHighlights()),
    vscode.workspace.onDidChangeTextDocument(async (event) => {
      const fsPath = event.document.uri.fsPath;
      if (!diagStore.has(fsPath)) return;
      const entries = diagStore.get(fsPath) || [];
      const updated = [];
      for (const entry of entries) {
        const reanchored = reanchorEntry(entry, event.document, event.contentChanges || []);
        if (reanchored) {
          updated.push(reanchored);
        }
      }
      updateDiagnosticsForFile(fsPath, updated);
    })
  );

  const openIssueCommand = vscode.commands.registerCommand('cot.openIssue', async (issue) => {
    try {
      if (!issue || !issue.fsPath || !issue.range) return;
      const doc = await vscode.workspace.openTextDocument(issue.fsPath);
      const editor = await vscode.window.showTextDocument(doc, { preview: false });
      const selection = issue.range;
      editor.selection = new vscode.Selection(selection.start, selection.end);
      editor.revealRange(selection, vscode.TextEditorRevealType.InCenter);
    } catch (err) {
      showError(err);
    }
  });

  context.subscriptions.push(openIssueCommand);

  const refreshTree = () => treeProvider.refresh();
  const originalUpdateDiagnosticsForFile = updateDiagnosticsForFile;
  updateDiagnosticsForFile = (fsPath, entries) => {
    originalUpdateDiagnosticsForFile(fsPath, entries);
    refreshTree();
    return;
  };

  const pickWorkspaceCommand = vscode.commands.registerCommand('cot.pickWorkspace', async () => {
    try {
      const chosen = await pickFolder('Choose workspace/codebase', currentWorkspacePath || getWorkspaceFolder());
      if (chosen) {
        currentWorkspacePath = chosen;
        treeProvider.refresh();
      }
    } catch (err) {
      showError(err);
    }
  });
  context.subscriptions.push(pickWorkspaceCommand);
}

function deactivate() {}

module.exports = {
  activate,
  deactivate,
};
