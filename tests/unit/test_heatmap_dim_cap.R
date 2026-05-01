# Unit tests for scripts/r/heatmap.R::compute_dims
#
# Regression cover for the bug fixed in commit 4fd9aa2:
# "fix(heatmap): cap motifs, size figures dynamically"
#
# The original heatmap.R hard-coded `height <- 10 * ceiling(N/2)`. With
# many clusters this pushed the figure past ggplot2::ggsave's 50-inch
# safety limit and aborted the whole task. The fix derives dimensions
# from motif count + panel layout AND caps at `max_inches`. These tests
# verify the cap holds across input ranges that previously triggered
# the bug.
#
# Run via tests/unit/run.sh, which invokes:
#   Rscript tests/unit/test_heatmap_dim_cap.R
# Exits non-zero on any assertion failure.

# Locate this script regardless of cwd.
this_script <- (function() {
  args <- commandArgs(trailingOnly = FALSE)
  m <- grep("--file=", args, value = TRUE)
  if (length(m)) return(normalizePath(sub("--file=", "", m[1])))
  # interactive() / sourced — fallback to environment hint
  Sys.getenv("R_TEST_SELF", unset = NA_character_)
})()
repo_root <- dirname(dirname(dirname(this_script)))
suppressMessages(source(file.path(repo_root, "scripts/r/heatmap.R")))

failures <- 0L
report <- function(name, ok, detail = "") {
  if (isTRUE(ok)) {
    cat(sprintf("  PASS  %s\n", name))
  } else {
    cat(sprintf("  FAIL  %s  %s\n", name, detail))
    failures <<- failures + 1L
  }
}

cat("[unit] heatmap compute_dims\n")

# ---------------------------------------------------------------------------
# Case 1 (the historical break): random_genes_topN had ~25 clusters. With
# the old formula height = 10 * ceiling(25/2) = 130 inches → ggsave abort.
# With the cap we expect the result to stop at max_inches.
# ---------------------------------------------------------------------------
dims <- compute_dims(n_motifs = 30, ncol_p = 2, nrow_p = 13, max_inches = 40)
report("25-cluster grid: height capped at 40",   dims$height <= 40,
       sprintf("(got %.2f)", dims$height))
report("25-cluster grid: width capped at 40",    dims$width  <= 40,
       sprintf("(got %.2f)", dims$width))

# ---------------------------------------------------------------------------
# Case 2: small inputs should not be inflated up to the cap — caller-friendly
# behaviour (cells should remain ~0.18 in regardless of cap).
# ---------------------------------------------------------------------------
dims_small <- compute_dims(n_motifs = 5, ncol_p = 1, nrow_p = 1, max_inches = 40)
report("small input: height stays small (< 10)", dims_small$height < 10,
       sprintf("(got %.2f)", dims_small$height))
report("small input: width stays small (< 10)",  dims_small$width  < 10,
       sprintf("(got %.2f)", dims_small$width))

# ---------------------------------------------------------------------------
# Case 3: scaling is monotonic in motif count up to the cap. A 10-motif grid
# must be smaller than a 30-motif grid (until both saturate the cap).
# ---------------------------------------------------------------------------
d10 <- compute_dims(n_motifs = 10, ncol_p = 2, nrow_p = 2, max_inches = 40)
d30 <- compute_dims(n_motifs = 30, ncol_p = 2, nrow_p = 2, max_inches = 40)
report("monotonic in n_motifs (height)", d30$height >= d10$height,
       sprintf("(d10=%.2f, d30=%.2f)", d10$height, d30$height))
report("monotonic in n_motifs (width)",  d30$width  >= d10$width,
       sprintf("(d10=%.2f, d30=%.2f)", d10$width,  d30$width))

# ---------------------------------------------------------------------------
# Case 4: extreme inputs do not exceed the cap. Even a degenerate request
# with 1000 motifs and 100 rows must respect max_inches.
# ---------------------------------------------------------------------------
d_extreme <- compute_dims(n_motifs = 1000, ncol_p = 4, nrow_p = 100, max_inches = 40)
report("extreme input: height capped",    d_extreme$height <= 40,
       sprintf("(got %.2f)", d_extreme$height))
report("extreme input: width capped",     d_extreme$width  <= 40,
       sprintf("(got %.2f)", d_extreme$width))

# ---------------------------------------------------------------------------
# Case 5: the cap is configurable. Setting max_inches=20 should bind tighter
# than the default 40 on a previously-capped input.
# ---------------------------------------------------------------------------
d_tight <- compute_dims(n_motifs = 30, ncol_p = 2, nrow_p = 13, max_inches = 20)
report("max_inches=20 binds height", d_tight$height <= 20,
       sprintf("(got %.2f)", d_tight$height))
report("max_inches=20 binds width",  d_tight$width  <= 20,
       sprintf("(got %.2f)", d_tight$width))

cat(sprintf("\n[unit] heatmap compute_dims: %s\n",
            if (failures == 0L) "all passed" else sprintf("%d FAILURE(S)", failures)))
quit(status = if (failures == 0L) 0 else 1)
