# Dump R-side ProcessPmetResult output as JSON so a sibling test can
# compare it against the frontend's processPmetResult() (which lives in
# apps/pmet_frontend/app/visualize/page.tsx).
#
# Usage:
#   Rscript scripts/r/dump_processed_data.R \
#       <motif_output.txt> <out.json> [p_adj_limit=0.05] \
#       [topn=5] [unique_combination=true] [max_motifs=30]
#
# The two pipelines were known to diverge: R picks motifs by cumulative
# -log10(p_adj) score per cluster (then a global reshuffle when the cap
# is hit), frontend picks motifs from the top-N pairs by p_adj_bonf.
# Same filters up front, different motif-selection rule. The JSON this
# script writes lets tests/integration/verify_heatmap_consistency.py
# diff at the data level instead of staring at PNGs.

suppressPackageStartupMessages({
  library(dplyr)
  library(data.table)
  library(stringr)
  library(jsonlite)

  source("scripts/r/process_pmet_result.R")
})

args <- commandArgs(trailingOnly = TRUE)
if (length(args) < 2) {
  stop("Args: <motif_output.txt> <out.json> [p_adj_limit] [topn] [unique] [max_motifs]")
}
in_path  <- args[1]
out_path <- args[2]
p_adj_limit <- if (length(args) >= 3) as.numeric(args[3]) else 0.05
topn        <- if (length(args) >= 4) as.integer(args[4]) else 5L
unique_cmb  <- if (length(args) >= 5) as.logical(args[5]) else TRUE
max_motifs  <- if (length(args) >= 6) as.integer(args[6]) else 30L

raw <- data.table::fread(in_path,
  select = c(
    "Cluster",
    "Motif 1",
    "Motif 2",
    "Number of genes in cluster with both motifs",
    "Adjusted p-value (Bonf)",
    "Genes"
  ), verbose = FALSE) %>%
  setNames(c("cluster", "motif1", "motif2", "gene_num", "p_adj", "genes")) %>%
  arrange(desc(p_adj)) %>%
  mutate(motif_pair = paste0(motif1, "^^", motif2))

processed <- ProcessPmetResult(
  pmet_result        = raw,
  p_adj_limt         = p_adj_limit,
  gene_portion       = 0.05,
  topn               = topn,
  max_motifs_in_plot = max_motifs,
  histgram_dir       = NULL,
  unique_cmbination  = unique_cmb)

if (is.null(processed)) {
  jsonlite::write_json(list(
    error   = "no_data_after_filter",
    motifs  = setNames(list(), character(0)),
    pairs   = list()
  ), out_path, auto_unbox = TRUE, pretty = TRUE)
  cat("[dump_processed_data.R] No data after filtering.\n")
  quit(status = 0)
}

# Pairs by cluster — what the heatmap will actually plot. Sorted by
# (motif1, motif2) for stable diffs.
pairs_by_cluster <- lapply(processed$pmet_result, function(df) {
  df %>%
    select(motif1, motif2, p_adj, gene_num) %>%
    arrange(motif1, motif2) %>%
    as.data.frame()
})

out <- list(
  parameters = list(
    p_adj_limit = p_adj_limit,
    topn        = topn,
    unique_combination = unique_cmb,
    max_motifs  = max_motifs
  ),
  # Motif lists per cluster, in the order ProcessPmetResult picks them
  # (significance-score ranking with the secondary global reshuffle).
  motifs_per_cluster = processed$motifs,
  pairs_per_cluster  = pairs_by_cluster
)

jsonlite::write_json(out, out_path, auto_unbox = TRUE, pretty = TRUE)
cat("[dump_processed_data.R] wrote", out_path, "\n")
