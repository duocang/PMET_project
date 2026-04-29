"""Audit spec for pipeline/workflows/promoter.sh.

Runs the full TAIR10 + Franco-Zorrilla 113-motif index against the
canonical genes_cell_type_treatment cluster list. ~2 minutes wall.
This is the same configuration that produced the recorded baseline
(motif_output.txt sha 4b24906a..., cross-validated against pair_only.sh
in commit d2663c0).
"""
from pathlib import Path
from lib import (
    Check, at_least_check, contract_invariant_checks, equal_check,
    count_dir_files, head_lines, linecount, r_invocation_checks,
    reset_dir, run_workflow, sha256,
)


def run(repo_root: Path, runs_dir: Path) -> dict:
    homo = reset_dir(runs_dir / "01_homotypic")
    het = reset_dir(runs_dir / "02_heterotypic")
    plot = reset_dir(runs_dir / "03_plot")
    log_path = runs_dir / "run.log"
    cmd = [
        "bash", "pipeline/workflows/promoter.sh",
        "-o", str(homo),
        "-x", str(het),
        "-y", str(plot),
        "-t", "4",
    ]
    rc = run_workflow(cmd, repo_root, log_path)

    motif_output = het / "motif_output.txt"
    fimohits = homo / "fimohits"
    binomial = homo / "binomial_thresholds.txt"
    ic = homo / "IC.txt"
    universe = homo / "universe.txt"
    promoter_lengths = homo / "promoter_lengths.txt"

    return {
        "run_label": "promoter",
        "returncode": rc["returncode"],
        "seconds": rc["seconds"],
        "log_tail": rc["log_tail"],
        "homotypic_dir": str(homo.relative_to(repo_root)),
        "heterotypic_dir": str(het.relative_to(repo_root)),
        "plot_dir": str(plot.relative_to(repo_root)),
        "fimohits_count": count_dir_files(fimohits, "*.bin"),
        "binomial_lines": linecount(binomial),
        "ic_lines": linecount(ic),
        "universe_lines": linecount(universe),
        "promoter_lengths_lines": linecount(promoter_lengths),
        "motif_output_lines": linecount(motif_output),
        "motif_output_sha": sha256(motif_output),
        "motif_output_head": head_lines(motif_output, 3),
        "plot_pngs": count_dir_files(plot, "*.png"),
        "command_displayed": " ".join(cmd),
        "_index_dir": homo,
        "_plot_dir": plot,
    }


def checks(data: dict) -> list[Check]:
    n_motifs_in_meme = 113  # data/motifs/Franco-Zorrilla_et_al_2014.meme
    r_checks, _ = r_invocation_checks(data["_plot_dir"])
    return [
        equal_check("script exit code", 0, data["returncode"]),

        equal_check("fimohits/*.bin per motif",
                    n_motifs_in_meme, data["fimohits_count"]),

        equal_check("binomial_thresholds rows == motifs",
                    n_motifs_in_meme, data["binomial_lines"]),

        equal_check("IC.txt rows == motifs",
                    n_motifs_in_meme, data["ic_lines"]),

        at_least_check("universe.txt non-empty (genes with valid promoters)",
                       1, data["universe_lines"],
                       note="TAIR10 with 1 kb promoter + UTR keeps about 30k genes"),

        equal_check("promoter_lengths.txt rows == universe size",
                    data["universe_lines"], data["promoter_lengths_lines"]),

        at_least_check("motif_output.txt non-empty (heterotypic pairs)",
                       1, data["motif_output_lines"]),

        equal_check("motif_output.txt deterministic vs anchor",
                    "4b24906abfe55ebe4ddf42832807a4f8c2ea3e0b6cb8e613a8450e2eedbf7e70",
                    data["motif_output_sha"],
                    note="anchor matches the recorded cli/03_promoter baseline"),

        # Cross-file motif-set invariants — independent of the script's
        # own check_homotypic_contract.py call.
        *contract_invariant_checks(data["_index_dir"],
                                   name_prefix="indexing contract"),

        *r_checks,
    ]
