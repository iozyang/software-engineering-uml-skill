#!/usr/bin/env python3
"""Collect conservative, read-only source facts for the software-engineering-uml skill."""

from __future__ import annotations

import argparse
import ast
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

EXCLUDED_DIRS = {
    ".git", ".idea", ".vscode", "node_modules", "target", "build", "dist",
    "__pycache__", ".venv", "venv", "bin", "obj", "coverage", "vendor",
}
LANGUAGE_BY_SUFFIX = {
    ".java": "java", ".py": "python", ".c": "c", ".h": "c",
    ".cc": "cpp", ".cpp": "cpp", ".cxx": "cpp", ".hpp": "cpp",
    ".js": "javascript", ".jsx": "javascript", ".ts": "typescript",
    ".tsx": "typescript", ".sql": "sql",
}
SOURCE_SUFFIXES = set(LANGUAGE_BY_SUFFIX)
CLASS_RE = re.compile(r"\b(?:class|interface|struct|enum)\s+([A-Za-z_]\w*)")
FUNCTION_RE = re.compile(
    r"(?:^|\n)\s*(?:(?:public|private|protected|static|virtual|async|const|\w+)\s+)+"
    r"([A-Za-z_]\w*)\s*\([^;{}]*\)\s*(?:const\s*)?[{=]",
)
IMPORT_RE = re.compile(r"^\s*(?:import|from)\s+([^;\n]+)", re.MULTILINE)
INCLUDE_RE = re.compile(r"^\s*#include\s*[<\"]([^>\"]+)[>\"]", re.MULTILINE)
EXTENDS_RE = re.compile(r"\b(?:extends|implements)\s+([A-Za-z_]\w*)")
SQL_TABLE_RE = re.compile(r"\bCREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?[\"`]?([\w]+)", re.I)
SQL_COLUMN_RE = re.compile(r"^\s*[\"`]?([A-Za-z_]\w*)[\"`]?\s+([A-Za-z]+(?:\([^)]*\))?)", re.I)
SQL_FK_RE = re.compile(r"FOREIGN\s+KEY\s*\(([^)]+)\)\s*REFERENCES\s+([\w`\"]+)\s*\(([^)]+)\)", re.I)


def iter_source_files(root: Path):
    for path in root.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in SOURCE_SUFFIXES:
            continue
        if any(part in EXCLUDED_DIRS for part in path.relative_to(root).parts):
            continue
        yield path


def read_text(path: Path) -> tuple[str, str | None]:
    for encoding in ("utf-8", "utf-8-sig", "gb18030", "latin-1"):
        try:
            return path.read_text(encoding=encoding), None
        except UnicodeDecodeError:
            continue
    return "", "unable to decode file"


def python_facts(text: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    classes: list[dict[str, Any]] = []
    functions: list[dict[str, Any]] = []
    warnings: list[str] = []
    try:
        tree = ast.parse(text)
    except SyntaxError as exc:
        return [], [], [f"python syntax error at line {exc.lineno}: {exc.msg}"]
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            classes.append({"name": node.name, "kind": "class", "line": node.lineno,
                            "bases": [ast.unparse(base) for base in node.bases]})
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            functions.append({"name": node.name, "kind": "async" if isinstance(node, ast.AsyncFunctionDef) else "function",
                              "line": node.lineno})
    return classes, functions, warnings


def sql_facts(text: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    tables: list[dict[str, Any]] = []
    relations: list[dict[str, Any]] = []
    for match in SQL_TABLE_RE.finditer(text):
        table = {"name": match.group(1), "line": text.count("\n", 0, match.start()) + 1, "columns": []}
        block_start = text.find("(", match.end())
        block_end = block_start
        depth = 0
        if block_start != -1:
            for index in range(block_start, len(text)):
                if text[index] == "(":
                    depth += 1
                elif text[index] == ")":
                    depth -= 1
                    if depth == 0:
                        block_end = index
                        break
        if block_start != -1 and block_end > block_start:
            for raw_line in text[block_start + 1:block_end].splitlines():
                column = SQL_COLUMN_RE.match(raw_line.strip().rstrip(","))
                if column and column.group(1).upper() not in {"PRIMARY", "FOREIGN", "CONSTRAINT", "UNIQUE", "CHECK"}:
                    table["columns"].append({"name": column.group(1), "type": column.group(2)})
        tables.append(table)
    for match in SQL_FK_RE.finditer(text):
        relations.append({"from_columns": [x.strip() for x in match.group(1).split(",")],
                          "to_table": match.group(2).strip('`"'),
                          "to_columns": [x.strip() for x in match.group(3).split(",")]})
    return tables, relations


def analyze_file(path: Path, root: Path) -> dict[str, Any]:
    text, decode_warning = read_text(path)
    language = LANGUAGE_BY_SUFFIX[path.suffix.lower()]
    relative = path.relative_to(root).as_posix()
    result: dict[str, Any] = {"path": relative, "language": language, "lines": text.count("\n") + (1 if text else 0),
                              "classes": [], "functions": [], "imports": [], "relations": [], "tables": [], "warnings": []}
    if decode_warning:
        result["warnings"].append(decode_warning)
        return result
    if language == "python":
        result["classes"], result["functions"], result["warnings"] = python_facts(text)
    else:
        result["classes"] = [{"name": match.group(1), "kind": "type", "line": text.count("\n", 0, match.start()) + 1}
                             for match in CLASS_RE.finditer(text)]
        result["functions"] = [{"name": match.group(1), "kind": "function",
                                 "line": text.count("\n", 0, match.start()) + 1}
                                for match in FUNCTION_RE.finditer(text)]
        result["imports"] = [match.group(1).strip() for match in IMPORT_RE.finditer(text)]
        result["imports"] += [match.group(1).strip() for match in INCLUDE_RE.finditer(text)]
        result["relations"] = [{"kind": "extends_or_implements", "target": match.group(1)}
                               for match in EXTENDS_RE.finditer(text)]
    if language == "sql":
        result["tables"], result["relations"] = sql_facts(text)
    if not result["classes"] and not result["functions"] and not result["tables"]:
        result["warnings"].append("no recognizable type, function, or table declaration")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project_root", type=Path)
    parser.add_argument("--output", type=Path, default=Path(".uml-analysis"))
    args = parser.parse_args()
    root = args.project_root.resolve()
    output = args.output.resolve()
    files = [analyze_file(path, root) for path in iter_source_files(root)]
    languages = Counter(item["language"] for item in files)
    warnings = [{"path": item["path"], "messages": item["warnings"]}
                for item in files if item["warnings"]]
    report = {"schema_version": "1.0", "project_root": str(root), "read_only": True,
              "files_scanned": len(files), "languages": dict(sorted(languages.items())),
              "files": files, "warnings": warnings,
              "entry_candidates": [item["path"] for item in files
                                   if Path(item["path"]).name.lower() in {"main.java", "main.py", "main.cpp", "app.py", "index.js", "index.ts"}]}
    output.mkdir(parents=True, exist_ok=True)
    (output / "analysis.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(output / "analysis.json"), "files_scanned": len(files), "languages": dict(languages)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
