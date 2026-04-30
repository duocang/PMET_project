suppressPackageStartupMessages({
  library(dplyr)
  library(data.table)
  library(stringr)
  library(ggplot2)
  library(ggpubr)
  library(hrbrthemes)

  source("scripts/r/process_pmet_result.R")
  source("scripts/r/motif_pair_gene_diagonal.R")
  source("scripts/r/motif_pair_diagonal.R")
  source("scripts/r/motif_pair_plot_hetero.R")
  source("scripts/r/motif_pair_plot_homog.R")
  source("scripts/r/heatmap.R")
})

args <- commandArgs(trailingOnly = TRUE)
# Positional args:
#   1 method            "All" | "Overlap" | <cluster name>
#   2 filename          output png path
#   3 pmet.out          motif_output.txt
#   4 topn              legacy, kept for backwards compatibility (ignored)
#   5 histgram_ncol
#   6 histgram_width
#   7 unique_cmbination "TRUE" | "FALSE"
#   8 max_motifs        optional, default 30. Cap on motifs drawn — bounds
#                       both readability (cell size) and figure size.
#   9 max_fig_inches    optional, default 40. Hard ceiling on figure
#                       width/height in inches.
if (length(args) < 7 || length(args) > 9) {
  stop("Args: method filename pmet.out topn ncol width unique [max_motifs] [max_fig_inches]")
}
method            <- args[1]
filename          <- args[2]
pmet.out          <- args[3]
topn              <- as.integer(args[4])
histgram_ncol     <- as.integer(args[5])
histgram_width    <- as.integer(args[6])
unique_cmbination <- as.logical(args[7])
max_motifs        <- if (length(args) >= 8) as.integer(args[8]) else 30L
max_fig_inches    <- if (length(args) >= 9) as.numeric(args[9]) else 40

heatmap.func(filename           = filename,
             method             = method,
             topn               = topn,
             p_adj_threshold    = 0.05,
             p_adj_method       = "Adjusted p-value (Bonf)",
             pmet_out           = pmet.out,
             draw_histgram      = TRUE,
             unique_cmbination  = unique_cmbination,
             exclusive_motifs   = FALSE,
             histgram_ncol      = histgram_ncol,
             histgram_width     = histgram_width,
             max_motifs_in_plot = max_motifs,
             max_fig_inches     = max_fig_inches)
