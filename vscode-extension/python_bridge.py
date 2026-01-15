#!/usr/bin/env python3
"""
Lightweight bridge that exposes ui.py/cli_tool capabilities to the VS Code
extension via simple CLI subcommands. This avoids tkinter usage and keeps the
heavy lifting in Python while the extension focuses on UX.
"""
import argparse
import json
import os
import sqlite3
import subprocess
import threading
import sys
import traceback
from pathlib import Path


EXT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = EXT_DIR.parent
CLI_ROOT = PROJECT_ROOT / "cli_tool"

# Ensure cli_tool modules are importable
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(CLI_ROOT))

CORE_DB_PATH = CLI_ROOT / "DB" / "crypto_primitives.db"
GENERATED_QL_OUTPUT_DIR = CLI_ROOT / "generated_ql_queries"
PROJECT_OUTPUTS_DIR = PROJECT_ROOT / "outputs"
DEFAULT_LIBRARY_IDS = [1, 2, 3, 4, 5, 6, 7]
DEFAULT_ANALYSIS_QUERIES = [
    "query_regexp_calls_and_args.ql",
    "query_regexp_macro.ql",
]


try:
    from cli_tool.query_maker.query_maker import (
        generate_query_no_args,
        generate_query_with_args,
        generate_query_macros,
        generate_query_regexp_calls_and_args,
        generate_query_regexp_macro,
    )
    from cli_tool.environ_detector.environ_detector import scan_project as cli_scan_environment
    from cli_tool.db_creator_updater.db_creator_updater import update as cli_update_db
    from cli_tool.report_maker.report_maker import make_pdf_report as cli_make_pdf_report
except Exception as exc:  # pragma: no cover - defensive import guard
    print(f"ERROR: Could not import CLI dependencies: {exc}", file=sys.stderr)
    print(traceback.format_exc(), file=sys.stderr)
    sys.exit(1)


def _run_command(cmd, passthrough=False):
    """Run a command and return subprocess.CompletedProcess with text outputs."""
    if passthrough:
        result = subprocess.run(cmd)
        return subprocess.CompletedProcess(cmd, result.returncode, "", "")

    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=0,
    )

    stdout_chunks = []
    stderr_chunks = []

    def _reader(stream, sink, chunks):
        while True:
            data = stream.read(4096)
            if not data:
                break
            chunks.append(data)
            sink.write(data)
            sink.flush()

    threads = []
    if process.stdout:
        t_out = threading.Thread(target=_reader, args=(process.stdout, sys.stdout, stdout_chunks))
        t_out.start()
        threads.append(t_out)
    if process.stderr:
        t_err = threading.Thread(target=_reader, args=(process.stderr, sys.stderr, stderr_chunks))
        t_err.start()
        threads.append(t_err)

    returncode = process.wait()
    for t in threads:
        t.join()

    return subprocess.CompletedProcess(cmd, returncode, "".join(stdout_chunks), "".join(stderr_chunks))


def generate_queries(library_ids=None):
    library_ids = library_ids or DEFAULT_LIBRARY_IDS
    GENERATED_QL_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    results = {}

    try:
        conn1 = sqlite3.connect(CORE_DB_PATH)
        results["query_noargs.ql"] = generate_query_no_args(conn1, library_ids)
        conn1.close()

        conn2 = sqlite3.connect(CORE_DB_PATH)
        results["query_withargs.ql"] = generate_query_with_args(conn2, library_ids)
        conn2.close()

        results["query_macro.ql"] = generate_query_macros()
        results["query_regexp_calls_and_args.ql"] = generate_query_regexp_calls_and_args()
        results["query_regexp_macro.ql"] = generate_query_regexp_macro()
    except Exception as exc:
        raise RuntimeError(f"Failed to generate queries: {exc}") from exc

    written_files = []
    for filename, content in results.items():
        if not content:
            continue
        target = GENERATED_QL_OUTPUT_DIR / filename
        target.write_text(content)
        written_files.append(str(target))

    return {"generated": written_files}


def scan_environment(path):
    if not Path(path).exists():
        raise FileNotFoundError(f"Path not found: {path}")
    env_info = cli_scan_environment(str(path))
    return {"path": str(path), "environment": env_info}


def update_db():
    cli_update_db()
    return {"status": "db updated"}


def create_codeql_database(source_root, database_path, build_command=None):
    source_root = Path(source_root).resolve()
    database_path = Path(database_path).resolve()

    # Safety guard: never create the DB inside the source tree
    try:
        database_path.relative_to(source_root)
    except ValueError:
        pass  # safe, not inside source root
    else:
        raise ValueError(
            f"Refusing to create CodeQL database inside the source tree: {database_path}. "
            f"Choose a path outside {source_root} (e.g., ../codeql-dbs/{source_root.name}-db)."
        )

    if database_path.is_file():
        raise ValueError(f"Target DB path points to an existing file: {database_path}")

    database_path.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        "codeql",
        "database",
        "create",
        str(database_path),
        "--language=c-cpp",
        f"--source-root={source_root}",
        "--overwrite",
    ]
    if build_command:
        cmd.append(f"--command={build_command}")

    result = _run_command(cmd, passthrough=True)
    return {
        "command": cmd,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "returncode": result.returncode,
    }


def _ensure_queries_exist(library_ids):
    missing = [name for name in DEFAULT_ANALYSIS_QUERIES if not (GENERATED_QL_OUTPUT_DIR / name).exists()]
    if missing:
        generate_queries(library_ids)


def run_codeql_analysis(database_path, output_dir=None, library_ids=None, query_files=None):
    database_path = Path(database_path)
    if not database_path.is_dir():
        raise FileNotFoundError(f"Database folder not found: {database_path}")

    query_files = query_files or DEFAULT_ANALYSIS_QUERIES
    _ensure_queries_exist(library_ids or DEFAULT_LIBRARY_IDS)

    output_dir = Path(output_dir) if output_dir else database_path.parent
    output_dir.mkdir(parents=True, exist_ok=True)

    results = []
    sarif_files = []

    for query_file in query_files:
        query_path = GENERATED_QL_OUTPUT_DIR / query_file
        if not query_path.exists():
            results.append(
                {
                    "query": query_file,
                    "error": f"Query file missing: {query_path}",
                }
            )
            continue

        query_basename = query_path.stem
        bqrs_path = output_dir / f"{query_basename}.bqrs"
        sarif_path = output_dir / f"{query_basename}.sarif"

        cmd_run = [
            "codeql",
            "query",
            "run",
            f"--database={database_path}",
            str(query_path),
            f"--output={bqrs_path}",
        ]
        run_result = _run_command(cmd_run, passthrough=True)

        cmd_interpret = [
            "codeql",
            "bqrs",
            "interpret",
            "--format=sarifv2.1.0",
            "-t=kind=problem",
            f"--output={sarif_path}",
            "--",
            str(bqrs_path),
        ]
        interpret_result = _run_command(cmd_interpret, passthrough=True)

        if sarif_path.exists():
            sarif_files.append(str(sarif_path))

        results.append(
            {
                "query": query_file,
                "run_returncode": run_result.returncode,
                "run_stdout": run_result.stdout,
                "run_stderr": run_result.stderr,
                "interpret_returncode": interpret_result.returncode,
                "interpret_stdout": interpret_result.stdout,
                "interpret_stderr": interpret_result.stderr,
                "bqrs": str(bqrs_path),
                "sarif": str(sarif_path),
            }
        )

    res_sarif_path = output_dir / "res.sarif"
    merge_result = None
    if sarif_files:
        cmd_merge = ["codeql", "github", "merge-results", f"--output={res_sarif_path}"]
        for sarif_file in sarif_files:
            cmd_merge.append(f"--sarif={sarif_file}")
        merge_result = _run_command(cmd_merge, passthrough=True)

    return {
        "database": str(database_path),
        "output_dir": str(output_dir),
        "queries": results,
        "merged_sarif": str(res_sarif_path) if res_sarif_path.exists() else None,
        "merge_stdout": merge_result.stdout if merge_result else "",
        "merge_stderr": merge_result.stderr if merge_result else "",
        "merge_returncode": merge_result.returncode if merge_result else None,
    }


def generate_reports(source_dir, output_dir=None):
    source_dir = Path(source_dir)
    if not source_dir.is_dir():
        raise FileNotFoundError(f"Source directory not found: {source_dir}")

    output_dir = Path(output_dir) if output_dir else PROJECT_OUTPUTS_DIR
    output_dir.mkdir(parents=True, exist_ok=True)

    created_reports = []
    for bqrs_file in source_dir.glob("*.bqrs"):
        base_name = bqrs_file.stem
        pdf_output = output_dir / f"{base_name}_report.pdf"
        cli_make_pdf_report(bqrs_path=str(bqrs_file), output_pdf=str(pdf_output))
        created_reports.append(str(pdf_output))

    return {"reports": created_reports, "output_dir": str(output_dir)}


def launch_ui():
    ui_path = PROJECT_ROOT / "ui.py"
    if not ui_path.exists():
        raise FileNotFoundError(f"ui.py not found at expected path: {ui_path}")
    result = _run_command([sys.executable, str(ui_path)])
    return {
        "stdout": result.stdout,
        "stderr": result.stderr,
        "returncode": result.returncode,
    }


def main():
    parser = argparse.ArgumentParser(description="Bridge CLI for VS Code extension")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("generate-queries")

    scan_parser = subparsers.add_parser("scan-environment")
    scan_parser.add_argument("--path", required=True)

    subparsers.add_parser("update-db")

    create_db_parser = subparsers.add_parser("create-codeql-db")
    create_db_parser.add_argument("--source-root", required=True)
    create_db_parser.add_argument("--database-path", required=True)
    create_db_parser.add_argument("--build-command", required=False)

    analysis_parser = subparsers.add_parser("run-analysis")
    analysis_parser.add_argument("--database", required=True)
    analysis_parser.add_argument("--output-dir")

    reports_parser = subparsers.add_parser("generate-reports")
    reports_parser.add_argument("--source-dir", required=True)
    reports_parser.add_argument("--output-dir")

    subparsers.add_parser("launch-ui")

    args = parser.parse_args()

    try:
        if args.command == "generate-queries":
            payload = generate_queries()
        elif args.command == "scan-environment":
            payload = scan_environment(args.path)
        elif args.command == "update-db":
            payload = update_db()
        elif args.command == "create-codeql-db":
            payload = create_codeql_database(args.source_root, args.database_path, args.build_command)
        elif args.command == "run-analysis":
            payload = run_codeql_analysis(args.database, args.output_dir)
        elif args.command == "generate-reports":
            payload = generate_reports(args.source_dir, args.output_dir)
        elif args.command == "launch-ui":
            payload = launch_ui()
        else:  # pragma: no cover - argparse guards command
            raise ValueError(f"Unknown command: {args.command}")
        print(json.dumps({"ok": True, "data": payload}, indent=2))
    except FileNotFoundError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        sys.exit(1)
    except Exception as exc:  # pragma: no cover - defensive
        print(json.dumps({"ok": False, "error": str(exc), "traceback": traceback.format_exc()}), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
