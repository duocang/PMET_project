MotifPairPlotHetero <- function(plot.data = NULL,
                                counts    = "p_adj",
                                motifs    = NULL,
                                clusters  = NULL) {

  COLORS <- c("#ed3333", "#1a94bc", "#40a070", "#fc6315",
              "#f9a633", "#813c85", "#2f2f35",
              "#ed3333", "#1a94bc", "#40a070", "#fc6315",
              "#f9a633", "#813c85", "#2f2f35")

  colors <- COLORS[seq_along(clusters)]
  names(colors) <- clusters

  clusters.actual <- unique(plot.data$cluster)
  if (length(clusters) != length(clusters.actual)) {
    colors <- c(colors, "black")
    names(colors) <- c(clusters, "Overlapped")
  }

  plot.data$cluster <- factor(plot.data$cluster, levels = names(colors))

  # Same cell-anchored font sizing as motif_pair_plot_homog.R; see
  # compute_font_size in heatmap.R for the rationale. The legacy
  # branch (length <= 15) used a fixed 20/15*1.5 input which floored
  # the font at 30pt regardless of how few motifs were drawn — that
  # is the proximate cause of "tiny heatmap, huge text" overflow on
  # small Overlap views.
  font_size <- compute_font_size(length(motifs))

  p <- plot.data %>%
    ggplot(aes(motif1, motif2, alpha = p_adj, fill = factor(cluster))) +
    geom_tile(color = "white") +
    scale_alpha(range = c(0.3, 1)) +
    # scale_fill_brewer(palette = "Set1", na.value = "white") +
    # na.translate = FALSE tells ggplot: NAs still get coloured by
    # na.value (white = empty cell, no significant pair in that
    # motif pair × cluster), but do NOT add a separate "NA" slot to
    # the legend. Without this the cluster legend ended up reading
    # "cortex / epidermis / pericycle / Overlapped / NA" — confusing,
    # because NA isn't a cluster.
    scale_fill_manual(values = colors, na.value = "white",
                      na.translate = FALSE) +
    scale_y_discrete(limits = rev, labels = rev(motifs)) +
    theme_bw() +
    theme(
      legend.text = element_text(size = font_size),
      legend.title = element_blank(),
      legend.position = "top",
      axis.line = element_blank(),
      axis.title.x = element_blank(),
      axis.title.y = element_blank(),
      axis.text.x = element_text(angle = 90, size = font_size),  # 设置x轴文本字号
      axis.text.y = element_text(size = font_size)               # 设置y轴文本字号
    ) +
    # guides(fill = "none", alpha = "none") +
    coord_fixed() +
    labs(x = NULL, y = NULL) # , title = "", subtitle = "")
  return(p)
}