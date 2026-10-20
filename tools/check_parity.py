#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 Philipp Lopaur <pl@loon.at>
"""Prüft, ob kgift.py und der Android-Port GiftView.kt noch zueinander passen.

Beide Dateien werden in Einheiten zerlegt (Funktionen/Methoden, dazu je Klasse
eine <init>-Einheit für Konstruktor und Felder, plus <top> für Modulebene).
Zueinander gehörende Einheiten werden über ihren Namen gepaart
(draw_flying_lid ↔ drawFlyingLid) und ihre Zahlen- und Farbliterale
als Multimenge verglichen.

Gewollte Unterschiede (plattformspezifische Funktionen, andere Textgrößen …)
stehen in tools/parity-baseline.json. Der Check schlägt fehl, sobald der
aktuelle Stand davon abweicht – also wenn eine Konstante nur auf einer Seite
geändert oder eine Funktion nur auf einer Seite hinzugefügt wurde.

    python3 tools/check_parity.py            # prüfen (Arbeitsverzeichnis)
    python3 tools/check_parity.py --staged   # prüfen (Git-Index, für den Hook)
    python3 tools/check_parity.py --update   # aktuellen Stand als gewollt übernehmen

Logikänderungen ohne geänderte Zahl (z. B. < statt >) erkennt der Check nicht.
"""

import argparse
import ast
import bisect
import io
import json
import os
import re
import subprocess
import sys
import tokenize
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
PY_FILE = "kgift.py"
KT_FILE = "android/app/src/main/java/at/loon/kgift/GiftView.kt"
BASELINE = "tools/parity-baseline.json"

# Python-Klasse → Kotlin-Klasse
CLASS_MAP = {"GiftWidget": "GiftView"}
# Einheiten, deren Namen sich nicht nur in der Schreibweise unterscheiden
ALIASES = {
    "GiftView.paintEvent": "GiftView.onDraw",
    "GiftView.mousePressEvent": "GiftView.performClick",
}

HEX_COLOR = re.compile(r"#[0-9a-fA-F]{6}(?:[0-9a-fA-F]{2})?")


def read(path, staged):
    if staged:
        try:
            return subprocess.run(["git", "show", ":" + path], cwd=ROOT, check=True,
                                  capture_output=True, text=True).stdout
        except subprocess.CalledProcessError:
            pass  # noch nicht im Index → Arbeitsverzeichnis
    with open(os.path.join(ROOT, path), encoding="utf-8") as f:
        return f.read()


def number(text):
    return repr(float(text.rstrip("fFL")))


def camel(name):
    head, *rest = name.split("_")
    return head + "".join(w[:1].upper() + w[1:] for w in rest)


# ------------------------------------------------------------------ Python
def py_units(src):
    """Ordnet jeder Quellzeile einen Einheitennamen zu (in Kotlin-Schreibweise)."""
    line_unit = {}

    def mark(node, name):
        for ln in range(node.lineno, node.end_lineno + 1):
            line_unit[ln] = name

    for node in ast.parse(src).body:
        if isinstance(node, ast.FunctionDef):
            mark(node, camel(node.name))
        elif isinstance(node, ast.ClassDef):
            cls = CLASS_MAP.get(node.name, node.name)
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name != "__init__":
                    mark(item, f"{cls}.{camel(item.name)}")
                else:
                    mark(item, f"{cls}.<init>")
            if not any(ln in line_unit for ln in range(node.lineno, node.end_lineno + 1)):
                line_unit[node.lineno] = f"{cls}.<init>"
        else:
            mark(node, "<top>")

    units = {name: Counter() for name in line_unit.values()}
    for tok in tokenize.generate_tokens(io.StringIO(src).readline):
        unit = line_unit.get(tok.start[0])
        if unit is None:
            continue
        if tok.type == tokenize.NUMBER:
            units[unit][number(tok.string)] += 1
        elif tok.type == tokenize.STRING:
            try:
                value = ast.literal_eval(tok.string)
            except (ValueError, SyntaxError):
                continue
            if isinstance(value, str) and HEX_COLOR.fullmatch(value):
                units[unit][value.lower()] += 1
    return {ALIASES.get(k, k): v for k, v in units.items()}


# ------------------------------------------------------------------ Kotlin
KT_TOKEN = re.compile(r"""
      (?P<comment>//[^\n]*|/\*.*?\*/)
    | (?P<string>"(?:\\.|[^"\\])*")
    | (?P<number>(?<![\w.])\d+(?:\.\d+)?(?:[eE][+-]?\d+)?[fFL]?(?!\w))
""", re.VERBOSE | re.DOTALL)
KT_FUN = re.compile(r"(?:(?:private|internal|public|protected|override|inline)\s+)*"
                    r"fun\s+(?:\w+\.)?(\w+)")
KT_CLASS = re.compile(r"(?:(?:private|internal|public|data|open|abstract)\s+)*class\s+(\w+)")


def kt_units(src):
    """Wie py_units, aber zeilenbasiert über die Einrückung (Kotlin ohne Parser)."""
    line_unit = {}
    classes = []   # [(Einrückung, Name)]
    fun = None     # (Einrückung, Name)

    def closes(scope_indent, indent, stripped):
        return indent < scope_indent or (indent == scope_indent and not stripped.startswith("}"))

    for ln, line in enumerate(src.splitlines(), 1):
        stripped = line.strip()
        if not stripped:
            continue
        indent = len(line) - len(line.lstrip())
        if fun and closes(fun[0], indent, stripped):
            fun = None
        while classes and closes(classes[-1][0], indent, stripped):
            classes.pop()
        owner = classes[-1][1] + "." if classes else ""
        if fun is None:
            m = KT_FUN.match(stripped)
            if m:
                fun = (indent, owner + m.group(1))
            else:
                m = KT_CLASS.match(stripped)
                if m:
                    owner = m.group(1) + "."
                    if stripped.endswith("{"):
                        classes.append((indent, m.group(1)))
        if fun:
            line_unit[ln] = fun[1]
        elif owner:
            line_unit[ln] = owner + "<init>"
        else:
            line_unit[ln] = "<top>"

    starts = [0] + [i + 1 for i, ch in enumerate(src) if ch == "\n"]
    units = {name: Counter() for name in line_unit.values()}
    for m in KT_TOKEN.finditer(src):
        unit = line_unit.get(bisect.bisect_right(starts, m.start()))
        if unit is None or m.group("comment"):
            continue
        if m.group("number"):
            units[unit][number(m.group("number"))] += 1
        elif m.group("string") and HEX_COLOR.fullmatch(m.group("string")[1:-1]):
            units[unit][m.group("string")[1:-1].lower()] += 1
    return units


# ------------------------------------------------------------------ Vergleich
def compare(py, kt):
    numbers = {}
    for name in sorted(py.keys() & kt.keys()):
        only_py = sorted((py[name] - kt[name]).elements())
        only_kt = sorted((kt[name] - py[name]).elements())
        if only_py or only_kt:
            numbers[name] = {"py": only_py, "kt": only_kt}
    return {
        "only_py": sorted(py.keys() - kt.keys()),
        "only_kt": sorted(kt.keys() - py.keys()),
        "numbers": numbers,
    }


def fmt(values):
    return " ".join(values) if values else "–"


def report(current, accepted):
    problems = []
    for key, label in (("only_py", "nur in kgift.py"), ("only_kt", "nur in GiftView.kt")):
        for name in sorted(set(current[key]) - set(accepted.get(key, []))):
            problems.append(f"  {name}: neu, {label}")
        for name in sorted(set(accepted.get(key, [])) - set(current[key])):
            problems.append(f"  {name}: nicht mehr {label} (Baseline veraltet)")
    old = accepted.get("numbers", {})
    for name in sorted(current["numbers"].keys() | old.keys()):
        now = current["numbers"].get(name, {"py": [], "kt": []})
        was = old.get(name, {"py": [], "kt": []})
        if now == was:
            continue
        problems.append(f"  {name}:")
        problems.append(f"      nur in kgift.py:     {fmt(now['py'])}")
        problems.append(f"      nur in GiftView.kt:  {fmt(now['kt'])}")
        if was["py"] or was["kt"]:
            problems.append(f"      bisher akzeptiert:   py {fmt(was['py'])} / kt {fmt(was['kt'])}")
    return problems


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--staged", action="store_true", help="Dateien aus dem Git-Index lesen")
    ap.add_argument("--update", action="store_true",
                    help="aktuelle Unterschiede als gewollt in die Baseline schreiben")
    args = ap.parse_args()

    current = compare(py_units(read(PY_FILE, args.staged)), kt_units(read(KT_FILE, args.staged)))

    if args.update:
        with open(os.path.join(ROOT, BASELINE), "w", encoding="utf-8") as f:
            json.dump(current, f, indent=2, ensure_ascii=False)
            f.write("\n")
        print(f"{BASELINE} aktualisiert.")
        return 0

    try:
        accepted = json.loads(read(BASELINE, args.staged))
    except FileNotFoundError:
        accepted = {}
    problems = report(current, accepted)
    if not problems:
        print("kgift.py ↔ GiftView.kt: synchron.")
        return 0
    print("kgift.py und GiftView.kt sind auseinandergelaufen:\n", file=sys.stderr)
    print("\n".join(problems), file=sys.stderr)
    print("\nÄnderung im anderen Port nachziehen – oder, falls gewollt, übernehmen mit\n"
          "    python3 tools/check_parity.py --update\n"
          f"und {BASELINE} mit committen.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
