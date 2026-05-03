"""Audit spec for scripts/workflows/elements.sh.

Runs against the canonical TAIR10 + Franco-Zorrilla, with the smallest
viable strategy/element pair (longest + 5'UTR — about 30s for indexing,
plus pairing_parallel for each gene list under data/genes/). Element 5'UTR
keeps roughly 22k of TAIR10's ~30k genes (those that have an annotated
5' UTR).

The new element pipeline (see commit d2663c0) does indexing through
indexing_fimo_fused (binary fimohits, deterministic) and then a Python
helper scripts/python/collapse_element_fimohits.py folds per-interval
hits back to per-gene rows. This audit verifies that fold actually
produced gene-named output, that downstream pairing_parallel can read it,
and that per-task SHAs match recorded anchors (deterministic — the
"C-engine non-determinism" caveat from older docs no longer applies
because elements.sh now uses indexing_fimo_fused).
"""
from pathlib import Path
from lib import (
    Check, at_least_check, contract_invariant_checks, equal_check,
    count_dir_files, head_lines, linecount, reset_dir, run_workflow, sha256,
    worked_example_block,
)


# Per-task motif_output.txt sha-256 anchors, captured against
# TAIR10 + Franco-Zorrilla + data/genes/*.txt with -s longest -e 5UTR.
#
# Three of these are independently verified (full sha was logged from a
# prior end-to-end run). The other three were not captured at full
# precision in earlier runs — left as None so the first audit run after
# this commit will capture the real sha and report it as a "new task,
# please bless" WARN. Update this dict after that first run.
TASK_ANCHORS = {
    "gene_cortex_epidermis_pericycle":
        "821f00782d42e230f5665df83d404ddefe50d498c6974a2667f475a9bb6c5440",
    "genes_cell_type_treatment":
        "0c9ca861133e44011153d6dd3c401040d8184b3c85d23ec965c76791acaf3200",
    "heat_top300":
        "8cb976813f466199eb52fada503c0a2d12d345b4e2d5e6db845aa0647e72395b",
    "random_genes_300":
        "325fc7241b23055d938b2850b3345fe6d7b8512ac79fb5e301017a29bde9a02e",
    "random_genes_topN":
        "3bf2de6907d611f7a8bfbb069c9223def28da97bea78218b5d8792080afb223b",
    "salt_top300":
        "8769c45243a01df255292315df31689b7f8500edc7b80a80560d04d347246254",
}


def run(repo_root: Path, runs_dir: Path) -> dict:
    # elements.sh embeds strategy + element in its OWN output path
    # (results/cli/elements_<strategy>_<element>/) so we can't redirect it
    # via -o; just delete + let the script create.
    canonical_dir = repo_root / "results" / "cli" / "elements_longest_five_prime_UTR"
    if canonical_dir.exists():
        import shutil
        shutil.rmtree(canonical_dir)

    log_path = runs_dir / "run.log"
    cmd = [
        "bash", "scripts/workflows/elements.sh",
        "-s", "longest",
        "-e", "5UTR",
        "-t", "4",
    ]
    rc = run_workflow(cmd, repo_root, log_path)

    homo = canonical_dir / "01_homotypic"
    fimohits = homo / "fimohits"
    binomial = homo / "binomial_thresholds.txt"
    ic = homo / "IC.txt"
    universe = homo / "universe.txt"
    promoter_lengths = homo / "promoter_lengths.txt"

    # gather per-task heterotypic outputs
    het_dirs = sorted([p for p in canonical_dir.glob("02_heterotypic_*") if p.is_dir()])

    task_results = {}  # task name -> (lines, sha)
    motif_outputs_present = 0
    total_het_lines = 0
    for d in het_dirs:
        task = d.name.removeprefix("02_heterotypic_")
        mo = d / "motif_output.txt"
        if mo.exists():
            n = linecount(mo)
            sha = sha256(mo)
            task_results[task] = (n, sha)
            motif_outputs_present += 1
            total_het_lines += n
        else:
            task_results[task] = (None, None)

    # Build the per-task table for the template (with the FULL sha so
    # readers can reproduce + reviewers can update anchors).
    task_table_rows = ["| task | motif_output rows | sha-256 (16) | anchor match |",
                       "|---|---|---|---|"]
    for task in sorted(task_results.keys()):
        n, sha = task_results[task]
        if sha is None:
            task_table_rows.append(f"| `{task}` | _missing_ | — | — |")
            continue
        anchor = TASK_ANCHORS.get(task)
        if anchor is None:
            match = "no anchor recorded"
        elif anchor == sha:
            match = "✅"
        else:
            match = f"❌ (anchor `{anchor[:16]}…`)"
        task_table_rows.append(f"| `{task}` | {n} | `{sha[:16]}` | {match} |")
    task_table = "\n".join(task_table_rows)

    # Worked example: pick the first per-task motif_output.txt that
    # actually exists (some gene lists have zero overlap with the 5'UTR
    # universe → no motif_output written for them).
    worked = "_(no per-task motif_output.txt produced — worked example skipped)_"
    for d in het_dirs:
        mo = d / "motif_output.txt"
        if mo.exists() and mo.stat().st_size > 0:
            worked = worked_example_block(
                motif_output=mo,
                universe=universe,
                binomial_thresholds=binomial,
                workflow_label=f"the elements audit (task `{d.name.removeprefix('02_heterotypic_')}`)",
            )
            break

    return {
        "run_label": "elements",
        "returncode": rc["returncode"],
        "seconds": rc["seconds"],
        "log_tail": rc["log_tail"],
        "result_root": str(canonical_dir.relative_to(repo_root)),
        "fimohits_count": count_dir_files(fimohits, "*.bin"),
        "binomial_lines": linecount(binomial),
        "ic_lines": linecount(ic),
        "universe_lines": linecount(universe),
        "promoter_lengths_lines": linecount(promoter_lengths),
        "het_dir_count": len(het_dirs),
        "motif_outputs_present": motif_outputs_present,
        "total_het_lines": total_het_lines,
        "task_table": task_table,
        "command_displayed": " ".join(cmd),
        "worked_example": worked,
        "_index_dir": homo,
        "_task_results": task_results,
    }


def checks(data: dict) -> list[Check]:
    n_motifs_in_meme = 113
    n_gene_lists = 6  # data/genes/*.txt currently
    base = [
        equal_check("script exit code", 0, data["returncode"]),

        equal_check("fimohits/*.bin per motif",
                    n_motifs_in_meme, data["fimohits_count"]),

        equal_check("binomial_thresholds rows == motifs",
                    n_motifs_in_meme, data["binomial_lines"]),

        equal_check("IC.txt rows == motifs",
                    n_motifs_in_meme, data["ic_lines"]),

        at_least_check("universe.txt non-empty (genes with 5'UTR)",
                       1, data["universe_lines"],
                       note="TAIR10 has ~22k genes with annotated 5' UTRs"),

        equal_check("promoter_lengths.txt rows == universe (post-collapse)",
                    data["universe_lines"], data["promoter_lengths_lines"],
                    note="collapse_element_fimohits.py also folds the per-interval "
                         "promoter_lengths into per-gene sums"),

        equal_check("one heterotypic dir per gene list",
                    n_gene_lists, data["het_dir_count"],
                    note="data/genes/*.txt globbed — bump n_gene_lists in spec "
                         "if you add/remove files"),

        at_least_check("at least 1 task produced motif_output",
                       1, data["motif_outputs_present"],
                       note="some gene lists have zero overlap with the 5'UTR "
                            "universe; that's biology, not failure"),

        at_least_check("total enriched pair rows across tasks",
                       1000, data["total_het_lines"],
                       note="lower bound; canonical run yields ~297k rows total"),
    ]

    # Cross-file invariants over the indexing dir.
    base += contract_invariant_checks(data["_index_dir"],
                                      name_prefix="indexing contract")

    # Per-task motif_output sha anchors. Each known task contributes
    # one check; tasks present in TASK_ANCHORS but absent from the
    # output produce a FAIL (regression — used to produce output but
    # doesn't anymore); tasks present in the output but absent from
    # TASK_ANCHORS produce a WARN (new task added without an anchor).
    for task, (n, sha) in data["_task_results"].items():
        # Use a sentinel: key MISSING from the dict means "new task,
        # never seen". Key present but value None means "task is known
        # but the sha hasn't been blessed yet (waiting for first run)".
        if task not in TASK_ANCHORS:
            base.append(Check.warning(
                f"per-task anchor: {task}", "anchor recorded",
                "task not in TASK_ANCHORS",
                note=f"new task; sha is `{(sha or '—')[:16]}` — add to "
                     f"TASK_ANCHORS in tests/audit/workflows/elements.py"))
            continue
        anchor = TASK_ANCHORS[task]
        if anchor is None:
            base.append(Check.warning(
                f"per-task anchor: {task}", "anchor recorded",
                f"awaiting first capture (current sha `{(sha or '—')[:16]}`)",
                note="anchor was deliberately left None at commit time; bless it "
                     "by pasting the captured sha into TASK_ANCHORS"))
            continue
        if sha is None:
            base.append(Check.failing(
                f"per-task anchor: {task}", "matches anchor",
                "task has no motif_output (was expected to)",
                note="gene list overlaps the universe but the run produced no output"))
        elif sha != anchor:
            base.append(Check.failing(
                f"per-task anchor: {task}", anchor[:16] + "…",
                sha[:16] + "…",
                note="content drift — review the diff before updating the anchor"))
        else:
            base.append(Check.passing(
                f"per-task anchor: {task}", anchor[:16] + "…", sha[:16] + "…"))

    # Tasks that were anchored but disappeared from the output entirely
    # (no 02_heterotypic_<task> dir) — surface as a separate FAIL.
    missing_anchored = [t for t in TASK_ANCHORS
                        if t not in data["_task_results"]]
    for task in missing_anchored:
        base.append(Check.failing(
            f"per-task anchor: {task}", "task ran",
            "no 02_heterotypic dir",
            note="anchored task didn't even start — gene list missing or "
                 "early script failure"))

    return base
