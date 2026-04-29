"""Audit spec for pipeline/workflows/intervals.sh.

Runs against the bundled data/demos/intervals fixture (10 motifs,
~25 MB intervals.fa). Same fixture the web app's "Use example" button
loads when a user picks the Intervals mode without uploading anything.
"""
from pathlib import Path
from lib import (
    Check, at_least_check, contract_invariant_checks, equal_check,
    count_dir_files, head_lines, linecount, r_invocation_checks,
    reset_dir, run_workflow, sha256,
)


def run(repo_root: Path, runs_dir: Path) -> dict:
    out_idx = reset_dir(runs_dir / "01_indexing")
    out_pair = reset_dir(runs_dir / "02_pairing")
    log_path = runs_dir / "run.log"
    cmd = [
        "bash", "pipeline/workflows/intervals.sh",
        "-s", "data/demos/intervals/indexing/intervals.fa",
        "-m", "data/demos/intervals/indexing/motif.meme",
        "-g", "data/demos/intervals/indexing/peaks.txt",
        "-o", str(out_idx),
        "-x", str(out_pair),
        "-t", "4",
    ]
    rc = run_workflow(cmd, repo_root, log_path)

    motif_output = out_pair / "motif_output.txt"
    fimohits_dir = out_idx / "fimohits"
    binomial = out_idx / "binomial_thresholds.txt"
    ic = out_idx / "IC.txt"
    universe = out_idx / "universe.txt"
    promoter_lengths = out_idx / "promoter_lengths.txt"
    plot_dir = out_pair / "plot"

    return {
        "run_label": "intervals",
        "returncode": rc["returncode"],
        "seconds": rc["seconds"],
        "log_tail": rc["log_tail"],
        "indexing_dir": str(out_idx.relative_to(repo_root)),
        "pairing_dir": str(out_pair.relative_to(repo_root)),
        "fimohits_count": count_dir_files(fimohits_dir, "*.bin"),
        "binomial_lines": linecount(binomial),
        "ic_lines": linecount(ic),
        "universe_lines": linecount(universe),
        "promoter_lengths_lines": linecount(promoter_lengths),
        "motif_output_lines": linecount(motif_output),
        "motif_output_sha": sha256(motif_output),
        "motif_output_head": head_lines(motif_output, 3),
        "plot_pngs": count_dir_files(plot_dir, "*.png"),
        "command_displayed": " ".join(cmd),
        "_index_dir": out_idx,
        "_plot_dir": plot_dir,
    }


def checks(data: dict) -> list[Check]:
    n_motifs_in_meme = 10  # data/demos/intervals/indexing/motif.meme
    r_checks, _ = r_invocation_checks(data["_plot_dir"])
    return [
        equal_check("script exit code", 0, data["returncode"]),

        equal_check("fimohits/*.bin per motif",
                    n_motifs_in_meme, data["fimohits_count"]),

        equal_check("binomial_thresholds rows == motifs",
                    n_motifs_in_meme, data["binomial_lines"]),

        equal_check("IC.txt rows == motifs",
                    n_motifs_in_meme, data["ic_lines"]),

        at_least_check("universe.txt non-empty (interval names)",
                       1, data["universe_lines"]),

        equal_check("promoter_lengths.txt rows == universe size",
                    data["universe_lines"], data["promoter_lengths_lines"],
                    note="every interval needs a length row"),

        at_least_check("motif_output.txt non-empty (heterotypic pairs)",
                       1, data["motif_output_lines"]),

        equal_check("motif_output.txt deterministic vs anchor",
                    "4858412a09198363305a419af01d47a35ff7cfd63a2169dd01aa545f8ff800c6",
                    data["motif_output_sha"],
                    note="captured against demo_intervals on this host; "
                         "differs if fixture or pair_parallel sort changes"),

        # Cross-file motif-set invariants — independent of the script's
        # own check_homotypic_contract.py call, so a future change that
        # skips the validator would still surface here.
        *contract_invariant_checks(data["_index_dir"],
                                   name_prefix="indexing contract"),

        *r_checks,
    ]
