"""Shared helpers for tests/audit/ workflow audit generation.

Each workflow under tests/audit/workflows/<name>.py exports two callables:

  def run(repo_root: Path, runs_dir: Path) -> dict:
      Execute the workflow against canonical inputs and return a flat
      dict whose keys feed BOTH the verification checks and the
      `<<PLACEHOLDER>>` substitutions in the matching template under
      tests/audit/templates/<name>.md. One key is treated specially by
      the driver: `run_label` (str) is used for the per-run header.

  def checks(data: dict) -> list[Check]:
      The list of expected-vs-observed assertions to render in the
      audit's verification table.

The driver (generate.py) renders the template with the data dict +
checks table, then writes to docs/workflows/<name>.md.

Cross-workflow helpers offered here:

  Check / Check.passing / Check.failing / Check.warning   primitives
  equal_check, at_least_check, file_exists_check          common shapes
  contract_invariant_checks(index_dir)                    cross-file
                                                          motif-set
                                                          sanity over a
                                                          homotypic dir
  r_invocation_checks(plot_dir)                           shared between
                                                          intervals + promoter
  run_workflow / sha256 / linecount / head_lines /
  count_dir_files / reset_dir                             IO helpers
  render_check_table / render_template / overall_verdict
  run_header                                              presentation
"""
from __future__ import annotations

import hashlib
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
RUNS_DIR = REPO_ROOT / "tests" / "audit" / "runs"
TEMPLATES_DIR = REPO_ROOT / "tests" / "audit" / "templates"
DOCS_DIR = REPO_ROOT / "docs" / "workflows"


# ---------------------------------------------------------------------------
# Verification check primitives
# ---------------------------------------------------------------------------
@dataclass
class Check:
    name: str
    expected: str
    actual: str
    verdict: str  # "PASS" | "FAIL" | "WARN"
    note: str = ""

    @classmethod
    def passing(cls, name, expected, actual="ok", note=""):
        return cls(name, str(expected), str(actual), "PASS", note)

    @classmethod
    def failing(cls, name, expected, actual, note=""):
        return cls(name, str(expected), str(actual), "FAIL", note)

    @classmethod
    def warning(cls, name, expected, actual, note=""):
        return cls(name, str(expected), str(actual), "WARN", note)


def equal_check(name: str, expected, actual, note: str = "") -> Check:
    if str(expected) == str(actual):
        return Check.passing(name, expected, actual, note)
    return Check.failing(name, expected, actual, note)


def at_least_check(name: str, lower_bound: int, actual: int, note: str = "") -> Check:
    if actual >= lower_bound:
        return Check.passing(name, f">= {lower_bound}", actual, note)
    return Check.failing(name, f">= {lower_bound}", actual, note)


def file_exists_check(name: str, path: Path, must_be_nonempty: bool = True) -> Check:
    if not path.exists():
        return Check.failing(name, "exists", "missing")
    if must_be_nonempty and path.stat().st_size == 0:
        return Check.failing(name, "non-empty", "empty (0 bytes)")
    size = path.stat().st_size
    return Check.passing(name, "non-empty" if must_be_nonempty else "exists",
                         f"{size:,} bytes")


# ---------------------------------------------------------------------------
# Subprocess + file inspection helpers
# ---------------------------------------------------------------------------
def run_workflow(cmd: list[str], cwd: Path, log_path: Path) -> dict:
    """Run a workflow command, time it, capture full output to log_path.

    Returns a dict with `returncode`, `seconds`, `log_tail` (last 12 lines).
    Raises RuntimeError if the workflow exits non-zero — callers can
    catch and embed the failure into the audit instead of crashing the
    whole generator.
    """
    log_path.parent.mkdir(parents=True, exist_ok=True)
    start = time.monotonic()
    with log_path.open("w") as fh:
        proc = subprocess.run(cmd, cwd=cwd, stdout=fh, stderr=subprocess.STDOUT)
    elapsed = time.monotonic() - start
    log_text = log_path.read_text(errors="replace")
    return {
        "returncode": proc.returncode,
        "seconds": elapsed,
        "log_tail": "\n".join(log_text.splitlines()[-12:]),
    }


def sha256(path: Path) -> str:
    """16-char SHA-256 prefix (full hash too noisy for the audit table)."""
    if not path.exists() or not path.is_file():
        return "missing"
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def linecount(path: Path) -> int:
    if not path.exists():
        return 0
    n = 0
    with path.open("rb") as fh:
        for _ in fh:
            n += 1
    return n


def head_lines(path: Path, n: int = 3) -> str:
    if not path.exists():
        return "(missing)"
    out = []
    with path.open("r", errors="replace") as fh:
        for i, line in enumerate(fh):
            if i >= n:
                break
            out.append(line.rstrip())
    return "\n".join(out)


def count_dir_files(path: Path, glob: str = "*") -> int:
    if not path.is_dir():
        return 0
    return sum(1 for p in path.glob(glob) if p.is_file())


def reset_dir(path: Path) -> Path:
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)
    return path


# ---------------------------------------------------------------------------
# Cross-file invariant verification (homotypic contract)
# ---------------------------------------------------------------------------
def _read_threshold_motifs(path: Path) -> set[str]:
    """First whitespace-separated field of each non-blank line."""
    motifs = set()
    if not path.exists():
        return motifs
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        motifs.add(line.split()[0])
    return motifs


def _read_ic_motifs(path: Path) -> set[str]:
    """IC.txt has the same shape: <motif><ws><values...>."""
    return _read_threshold_motifs(path)


def _list_fimohits_motifs(fimohits_dir: Path) -> set[str]:
    """Stem of every .bin / .txt file under fimohits/."""
    if not fimohits_dir.is_dir():
        return set()
    return {p.stem for p in fimohits_dir.iterdir()
            if p.is_file() and p.suffix in {".bin", ".txt"}}


def contract_invariant_checks(
    index_dir: Path,
    *,
    name_prefix: str = "homotypic contract",
    severity: str = "fail",
) -> list[Check]:
    """Verify the cross-file motif-set invariants over a homotypic dir.

    Returns three checks:
      - binomial_thresholds.txt motifs == IC.txt motifs
      - binomial_thresholds.txt motifs == fimohits/ basenames
      - IC.txt motifs == fimohits/ basenames

    `severity` controls how a mismatch renders:
      "fail" — emit a FAIL check (use for indexing workflows that own
               the invariant — promoter, intervals, elements).
      "warn" — emit a WARN (use for fixtures that are known partial,
               e.g. data/demos/promoters/pairing/demo which only ships 6 fimohits).
    """
    bin_motifs = _read_threshold_motifs(index_dir / "binomial_thresholds.txt")
    ic_motifs = _read_ic_motifs(index_dir / "IC.txt")
    fhits_motifs = _list_fimohits_motifs(index_dir / "fimohits")

    def make(name: str, lhs: set[str], rhs: set[str], lhs_name: str, rhs_name: str) -> Check:
        if lhs == rhs:
            return Check.passing(name, "set equal", f"|both|={len(lhs)}")
        only_lhs = sorted(lhs - rhs)
        only_rhs = sorted(rhs - lhs)
        diff_summary = f"only_{lhs_name}={only_lhs[:3]}{'...' if len(only_lhs)>3 else ''}, " \
                       f"only_{rhs_name}={only_rhs[:3]}{'...' if len(only_rhs)>3 else ''}"
        if severity == "warn":
            return Check.warning(name, "set equal", diff_summary,
                                 note="motif-set mismatch — see note above")
        return Check.failing(name, "set equal", diff_summary)

    return [
        make(f"{name_prefix}: binomial == IC motifs",
             bin_motifs, ic_motifs, "binomial", "IC"),
        make(f"{name_prefix}: binomial == fimohits motifs",
             bin_motifs, fhits_motifs, "binomial", "fimohits"),
        make(f"{name_prefix}: IC == fimohits motifs",
             ic_motifs, fhits_motifs, "IC", "fimohits"),
    ]


# ---------------------------------------------------------------------------
# R heatmap invocation checks (intervals + promoter share these)
# ---------------------------------------------------------------------------
def _count_histogram_dirs(plot_dir: Path) -> int:
    """draw_heatmap.R unconditionally creates 3 histogram subdirs.
    Their presence is the "did Rscript actually run?" probe."""
    if not plot_dir.is_dir():
        return 0
    return sum(
        1 for sub in ("histogram", "histogram_overlap", "histogram_overlap_unique")
        if (plot_dir / sub).is_dir()
    )


def r_invocation_checks(plot_dir: Path) -> tuple[list[Check], dict]:
    """Pair of (Rscript invoked? + headline PNGs landed?) checks.

    Returns (checks, data) — `data` is a dict with histogram_dirs and
    headline_pngs counts that the caller can also surface in the
    template's run-snapshot section.
    """
    histograms = _count_histogram_dirs(plot_dir)
    pngs = count_dir_files(plot_dir, "*.png")

    if histograms == 3:
        c1 = Check.passing("Rscript invoked (3 histogram subdirs present)",
                           "3", histograms)
    elif histograms == 0:
        c1 = Check.warning("Rscript invoked (3 histogram subdirs present)",
                           "3", "0",
                           note="Rscript may not be installed; data outputs still valid")
    else:
        c1 = Check.failing("Rscript invoked (3 histogram subdirs present)",
                           "3", histograms,
                           note="partial R run — investigate")

    if pngs == 3:
        c2 = Check.passing("3 headline heatmap PNGs rendered", "3", pngs)
    elif pngs == 0 and histograms == 3:
        c2 = Check.warning("3 headline heatmap PNGs rendered", "3", "0",
                           note="R ran but draw_heatmap.R's p-adj filter "
                                "left nothing to plot (expected on small demo data)")
    else:
        c2 = Check.failing("3 headline heatmap PNGs rendered", "3", pngs)

    return [c1, c2], {"histogram_dirs": histograms, "headline_pngs": pngs}


# ---------------------------------------------------------------------------
# Template rendering
# ---------------------------------------------------------------------------
def render_check_table(checks: list[Check]) -> str:
    """Format a list of Check into a markdown table."""
    if not checks:
        return "_(no checks recorded)_"
    badge = {"PASS": "✅ PASS", "FAIL": "❌ FAIL", "WARN": "⚠️ WARN"}
    rows = ["| # | Check | Expected | Observed | Verdict |",
            "|---|---|---|---|---|"]
    for i, c in enumerate(checks, 1):
        note_part = f" — {c.note}" if c.note else ""
        rows.append(f"| {i} | {c.name} | `{c.expected}` | `{c.actual}` | {badge[c.verdict]}{note_part} |")
    return "\n".join(rows)


def render_template(template_path: Path, variables: dict[str, str]) -> str:
    """Substitute <<KEY>> placeholders in a markdown template.

    Keys are case-insensitive on the placeholder side: <<MOTIF_OUTPUT_SHA>>
    looks up `motif_output_sha` (lowercased) in `variables`. Any
    unsubstituted placeholder is left as `<<UNRESOLVED:KEY>>` so it
    surfaces in review rather than silently rendering empty.
    """
    text = template_path.read_text()
    import re
    PLACEHOLDER = re.compile(r"<<([A-Z0-9_]+)>>")

    def sub(match: re.Match) -> str:
        key = match.group(1).lower()
        if key in variables:
            return str(variables[key])
        return f"<<UNRESOLVED:{match.group(1)}>>"

    return PLACEHOLDER.sub(sub, text)


def overall_verdict(checks: list[Check]) -> str:
    fails = sum(1 for c in checks if c.verdict == "FAIL")
    warns = sum(1 for c in checks if c.verdict == "WARN")
    passes = sum(1 for c in checks if c.verdict == "PASS")
    if fails:
        return f"❌ **FAIL** — {fails} check(s) failed, {warns} warning(s), {passes} pass(es)"
    if warns:
        return f"⚠️ **PASS WITH WARNINGS** — {warns} warning(s), {passes} pass(es)"
    return f"✅ **PASS** — all {passes} check(s) passed"


# ---------------------------------------------------------------------------
# Convenience: stamp the run header
# ---------------------------------------------------------------------------
def run_header(label: str, returncode: int, seconds: float) -> str:
    """One-line "ran on <date>, exit=N, took Xs" stamp."""
    import datetime as _dt
    timestamp = _dt.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    rc_part = f"exit {returncode}" if returncode != 0 else "exit 0"
    return f"_Audit refreshed {timestamp} on this machine — workflow `{label}`, {rc_part}, {seconds:.1f}s_"
