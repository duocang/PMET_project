# Output dimensions for the heatmap are computed from the actual motif
# count and panel layout instead of being hard-coded — keeps cells legible
# (~0.18 in/cell) and stops the figure from blowing past ggsave's 50-inch
# ceiling on crowded inputs (e.g. random_genes_topN.txt with 25+ clusters).
# Top-level so tests/unit/test_heatmap_dim_cap.R can verify the cap holds.
compute_dims <- function(n_motifs, ncol_p, nrow_p, max_inches) {
  cell_inch  <- 0.18
  axis_pad   <- 3.0   # axis labels + tick room
  legend_pad <- 2.0   # right-side legend
  title_pad  <- 0.6   # top title
  panel_w    <- n_motifs * cell_inch + axis_pad
  panel_h    <- n_motifs * cell_inch + axis_pad
  list(
    width  = min(panel_w * ncol_p + legend_pad, max_inches),
    height = min(panel_h * nrow_p + title_pad, max_inches)
  )
}

# Pick axis-label / legend font size proportional to the rendered cell
# size. The previous heuristic (`inch_pre_motif * 30`) capped at 30pt
# for any motif count <= ~20, which is way too large for the ~0.18 in
# (~13 pt tall) cells the heatmap actually draws — text was dwarfing
# the cells it was labelling. The replacement is anchored to cell
# size in points (cell_inch * 72), takes ~55% of cell so rotated x-axis
# labels can still fit between neighbours, and shrinks gracefully when
# the canvas hits max_inches and cells get squeezed.
#
# For very large motif counts the canvas saturates at max_inches and
# cells start shrinking; the ceiling-aware ratio below mirrors the same
# squeeze so the font stays proportional to whatever cell size the
# user actually sees. Floor at 4pt so the labels don't disappear.
#
# Top-level for the same reason as compute_dims: a unit test can pin
# the expected output without re-deriving it from the plot helpers.
compute_font_size <- function(n_motifs,
                              max_inches = 40,
                              cell_inch  = 0.18,
                              axis_pad   = 3.0,
                              cell_ratio = 0.55,
                              floor_pt   = 4.0,
                              ceiling_pt = 14.0) {
  panel_in   <- n_motifs * cell_inch + axis_pad
  scale      <- min(1, max_inches / max(panel_in, 1e-6))
  raw_pt     <- cell_inch * 72 * cell_ratio * scale
  min(ceiling_pt, max(floor_pt, raw_pt))
}

# Title font scales as a multiple of the axis font, so a tiny heatmap
# also gets a tiny title (the previous fixed `size = 30` produced a
# title twice the height of a 5-motif panel).
compute_title_size <- function(font_pt) {
  font_pt * 1.6
}

heatmap.func <- function(filename           = NULL,
                         method             = NULL,
                         pmet_out           = NULL,
                         topn               = 5,
                         p_adj_threshold    = 0.05,
                         p_adj_method       = "Adjusted p-value (Bonf)",
                         draw_histgram      = TRUE,
                         unique_cmbination  = TRUE,
                         exclusive_motifs   = TRUE,
                         histgram_ncol      = 2,
                         histgram_width     = 6,
                         heatmap_width      = 20,
                         heatmap_height     = 20,
                         max_motifs_in_plot = 30L,
                         max_fig_inches     = 40)
{

  if (draw_histgram) {
    histgram.path <- filename %>%
    tools::file_path_sans_ext() %>%
    stringr::str_replace("heatmap", "histogram")
  } else {
    histgram.path <- NULL
  }

  pmet.result <- data.table::fread(pmet_out,
    select = c(
      "Cluster",
      "Motif 1",
      "Motif 2",
      "Number of genes in cluster with both motifs",
      p_adj_method,
      "Genes"
    ), verbose = FALSE) %>%
    setNames(c("cluster", "motif1", "motif2", "gene_num", "p_adj", "genes")) %>%
    arrange(desc(p_adj)) %>%
    mutate(`motif_pair` = paste0(motif1, "^^", motif2))

  pmet.result.processed <- ProcessPmetResult( pmet_result        = pmet.result,
                                              p_adj_limt         = p_adj_threshold,
                                              gene_portion       = 0.05,
                                              topn               = topn,
                                              max_motifs_in_plot = max_motifs_in_plot,
                                              histgram_ncol      = 2,
                                              histgram_width     = 6,
                                              histgram_dir       = histgram.path,
                                              unique_cmbination  = unique_cmbination
                                              )

  if (is.null(pmet.result.processed)) {
    cat("No meaningfull data left after filtering!\n")
    return(NULL)
  }

  results   <- pmet.result.processed
  clusters <- names(results$pmet_result) %>% sort()

  motifs.selected <- results$motifs

  if (method == "Overlap") {
    # after filtering, some clusters may be gone and only one cluster is left
    if (length(clusters) == 1) {

      p <- MotifPairPlotHomog(results$pmet_result,
                              motifs.selected,
                              counts            = "p_adj",
                              exclusive.motifs  = exclusive_motifs,
                              by.cluster        = FALSE,
                              show.cluster      = FALSE,
                              legend.title      = "-log10(p.adj)",
                              nrow_             = ceiling(length(clusters)/2),
                              ncol_             = 2,
                              axis.lables       = "",
                              show.axis.text    = TRUE,
                              diff.colors       = TRUE,
                              respective.plot   = TRUE)
      p <- p[[1]]

    } else {
      motifs <- TopMotifsGenerator(pmet.result.processed$motifs, by.cluster = FALSE, exclusive.motifs = exclusive_motifs)
      num.motifs <- length(motifs)

      # expend ggplot with genes for hover information
      dat_list   <- MotifPairGeneDiagonal(pmet.result.processed$pmet_result, motifs, counts = "p_adj")
      clusters   <- names(dat_list) %>% sort()

      # merge data into DF[[1]]
      dat <- dat_list[[1]]
      index.overlapped <- c()
      # move all non-NA values from other DFs to DF[[1]]
      for (i in 2:length(dat_list)) {
        indx                 <- which(!is.na(dat_list[[i]][, "cluster"]))
        dat[indx,          ] <- dat_list[[i]][indx, ]
        dat[indx, "cluster"] <- names(dat_list)[i]
        index.overlapped     <- c(index.overlapped,
                                  intersect(which(!is.na(dat_list[[1]][, "cluster"])),
                                            which(!is.na(dat_list[[i]][, "cluster"]))))
      }

      # mark overlapped cells in the heatmap
      if (length(index.overlapped) > 0) {
        print("Overlapped index:")
        print(index.overlapped)
        dat[index.overlapped,  "p_adj" ] <- max(dat$p_adj, na.rm = TRUE)
        dat[index.overlapped, "cluster"] <- "Overlapped"
      }


      p <- MotifPairPlotHetero(dat,  "p_adj", motifs, clusters)
    }
  } else {
    if (method == "All") {
      respective.plot <- FALSE
    } else if (method %in% clusters) {
      motifs.selected <- list()
      motifs.selected[[method]] <- results$motifs[[method]]
      respective.plot <- TRUE
    }

    print(method)
    print(motifs.selected)

    p <- MotifPairPlotHomog(results$pmet_result,
                            motifs.selected,
                            counts            = "p_adj",
                            exclusive.motifs  = exclusive_motifs,
                            by.cluster        = FALSE,
                            show.cluster      = FALSE,
                            legend.title      = "-log10(p.adj)",
                            nrow_             = ceiling(length(clusters)/2),
                            ncol_             = 2,
                            axis.lables       = "",
                            show.axis.text    = TRUE,
                            diff.colors       = TRUE,
                            respective.plot   = respective.plot
    )

    if (method %in% clusters) {
      p <- p[[method]]
    }
  }

  # Decide motif count drawn and panel layout, then size accordingly.
  if (method == "Overlap") {
    if (length(clusters) == 1) {
      n_drawn <- length(motifs.selected[[1]])
    } else {
      n_drawn <- num.motifs   # union vector built above
    }
    nc <- 1; nr <- 1          # Overlap is one merged panel
  } else if (method == "All") {
    n_drawn <- length(unique(unlist(motifs.selected)))
    nc <- 2; nr <- ceiling(length(clusters) / 2)
  } else { # method %in% clusters
    n_drawn <- length(motifs.selected[[method]])
    nc <- 1; nr <- 1
  }

  dims <- compute_dims(n_drawn, nc, nr, max_fig_inches)
  ggsave(filename, p,
         width  = dims$width,
         height = dims$height,
         dpi    = 320,
         units  = "in",
         limitsize = FALSE)
}
