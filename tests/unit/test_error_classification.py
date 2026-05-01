#!/usr/bin/env python3
"""Unit tests for is_retryable_task_error (Problem 3 in TODO.md).

celery's default 3x60s retry backoff is wasted on errors that will
recur every retry — typical case is a user uploading a gene list whose
namespace doesn't match the chosen species index. The worker module
keeps a list of "permanent" substrings; if any appears in the error
message, we skip retry and ship the failure email immediately.

This test pins down what is permanent vs transient. Each new permanent
snippet should land here as a fixture so a future rename in a bash
script or a C++ source file can't silently demote it back to transient.

Run via tests/unit/run.sh.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "apps"))

from pmet_backend.worker.tasks.pmet import (  # noqa: E402
    NON_RETRYABLE_ERROR_SNIPPETS,
    is_retryable_task_error,
)


# Real error messages, lifted verbatim from the source files they emit
# from. If you rename one, this fixture is the canary.
PERMANENT_FIXTURES = {
    # scripts/workflows/pair_only.sh:185
    "no_genes_match_pair_only":
        "ERROR: No genes from the input list match the index universe "
        "(/data/precomputed_indexes/Athaliana/universe.txt)",
    # scripts/workflows/promoter.sh:268 (slightly different wording)
    "no_genes_match_promoter":
        "ERROR: No genes from the input list match the universe "
        "(homotypic stage filtered them all out)",
    # scripts/workflows/intervals.sh:253
    "no_intervals_match":
        "ERROR: No intervals from the input list match the index universe",
    # scripts/workflows/*:check_file (gene file, fimohits dir, etc.)
    "missing_or_empty_gene_file":
        "ERROR: gene_file missing or empty",
    # scripts/workflows/pair_only.sh:142
    "missing_index_dir":
        "ERROR: Index dir not found: /data/precomputed_indexes/UnknownSpecies",
    # scripts/workflows/pair_only.sh:149
    "missing_fimohits_dir":
        "ERROR: Index fimohits/ directory missing: /data/.../UnknownSpecies/fimohits",
    # scripts/workflows/promoter.sh:213
    "chromosome_name_mismatch":
        "ERROR: Chromosome name mismatch: GFF3='chr1' vs FASTA='1'. "
        "Ensure consistent naming.",
    # core/pairing/src/utils.cpp:151 (and motif.cpp:156, motif.cpp:327)
    "gene_not_in_promoter_lengths":
        "Error : Gene ID Os01g0103300 not found in promoter lengths file!",
    # core/pairing/src/utils.cpp:252
    "no_gene_clusters":
        "Error : No gene clusters found!",
    # Existing environment-mismatch snippets (regression check)
    "macho_on_linux_worker":
        "Required PMET binary /app/build/pair_parallel is a macOS Mach-O "
        "executable and cannot run inside the Linux Docker worker. "
        "Rebuild Linux binaries or run the worker on the host.",
    "exec_format_error":
        "OSError: [Errno 8] Exec format error: '/app/build/pair_parallel'",
    "missing_binary":
        "Required PMET binary is missing: /app/build/pair_parallel",
    "wrong_arch":
        "Required PMET binary /app/build/index_fimo_fused targets Linux/aarch64, "
        "but the worker is running on Linux/x86_64.",
}


# Should be retried — these are real-world transient failure modes a
# 60s backoff might actually fix.
TRANSIENT_FIXTURES = {
    "command_failed_generic":
        "Command failed: pair_parallel: unknown error",
    "connection_reset":
        "ConnectionResetError: [Errno 104] Connection reset by peer",
    "disk_io":
        "OSError: [Errno 5] Input/output error: '/tmp/pmet_xyz/temp001.txt'",
    "redis_temporarily_unavailable":
        "redis.exceptions.ConnectionError: Error 111 connecting to redis:6379. "
        "Connection refused.",
    "out_of_memory_killed":
        "subprocess returned non-zero exit status -9",
    # Wrapped form from executor.py for an arbitrary subprocess crash
    "command_failed_segfault":
        "Command failed: pair_parallel: Segmentation fault (core dumped)",
    # Pairing scripts emit this when shards are missing — could be
    # transient (worker killed mid-shard) so we leave it retryable.
    "no_temp_shards":
        "ERROR: pair_parallel produced no temp*.txt shards (see pmet.log)",
    # Empty / falsy
    "empty_string":
        "",
}


class IsRetryableTaskErrorTests(unittest.TestCase):
    def test_all_permanent_fixtures_classified_as_non_retryable(self):
        for label, msg in PERMANENT_FIXTURES.items():
            with self.subTest(case=label):
                self.assertFalse(
                    is_retryable_task_error(msg),
                    f"expected {label!r} to be non-retryable; got retryable",
                )

    def test_all_transient_fixtures_classified_as_retryable(self):
        for label, msg in TRANSIENT_FIXTURES.items():
            with self.subTest(case=label):
                self.assertTrue(
                    is_retryable_task_error(msg),
                    f"expected {label!r} to be retryable; got non-retryable",
                )

    def test_wrapped_executor_message_still_classified_correctly(self):
        """executor.py wraps stderr as 'Command failed: <stderr>'.
        Make sure the wrapping prefix doesn't break substring detection."""
        wrapped = (
            "Command failed: ERROR: No genes from the input list match the "
            "index universe (/data/precomputed_indexes/Athaliana/universe.txt)"
        )
        self.assertFalse(is_retryable_task_error(wrapped))

    def test_snippet_list_has_no_duplicates(self):
        """Lazy guard against accidental duplicate snippets after rebases."""
        snippets = list(NON_RETRYABLE_ERROR_SNIPPETS)
        self.assertEqual(
            len(snippets),
            len(set(snippets)),
            f"duplicate entry in NON_RETRYABLE_ERROR_SNIPPETS: {snippets}",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
