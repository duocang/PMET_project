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
# 1. method
# 2. filename
# 3. pmet.out
if (length(args) != 7) {
  stop("You need to provide exactly 5 arguments: method, filename, and pmet.out.")
}
method         <- args[1]
filename       <- args[2]
pmet.out       <- args[3]
topn           <- as.integer(args[4])
histgram_ncol  <- as.integer(args[5])
histgram_width <- as.integer(args[6])
unique_cmbination <- as.logical(args[7])

# # method       <- "All"
# method       <- "Overlap"
# filename     <- "results/05_plot/heatmap.png"
# pmet.out     <- "data/motif_output.txt"



heatmap.func(filename          = filename,
             method            = method,
             topn              = topn,
             p_adj_threshold   = 0.05,
             p_adj_method      = "Adjusted p-value (Bonf)",
             pmet_out          = pmet.out,
             draw_histgram     = TRUE,
             unique_cmbination = unique_cmbination, # if true, remove motif pairs not unique in different clusters
             exclusive_motifs  = FALSE,
             histgram_ncol     = histgram_ncol,
             histgram_width    = histgram_width)
