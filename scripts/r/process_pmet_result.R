COLORS <- c("#ed3333", "#1a94bc", "#40a070", "#fc6315",
            "#f9a633", "#813c85", "#2f2f35",
            "#ed3333", "#1a94bc", "#40a070", "#fc6315",
            "#f9a633", "#813c85", "#2f2f35")

# Get lower triangle of the correlation matrix
GetLowerTriangle <- function(cormat) {
  cormat[upper.tri(cormat)] <- NA
  return(cormat)
}
# Get upper triangle of the correlation matrix
GetUpperTriangle <- function(cormat) {
  cormat[lower.tri(cormat)] <- NA
  return(cormat)
}


ValidatePmetResult <- function(filepath) {

  if (is.null(filepath)) {
    return("NO_FILE")
  }

  if(file.info(filepath)$size == 0) {
    return("NO_CONTENT")
  }

  # read first line
  dat_first_row <- readLines(filepath, n = 1)
  # default header of PMET result
  pmet_result_rowname <- "Cluster\tMotif 1\tMotif 2\tNumber of genes in cluster with both motifs\tTotal number of genes with both motifs\tNumber of genes in cluster\tRaw p-value\tAdjusted p-value (BH)\tAdjusted p-value (Bonf)\tAdjusted p-value (Global Bonf)\tGenes"
  if (!identical(dat_first_row, pmet_result_rowname)) {
    # print("Wrong format of uploaded file")
    # hideFeedback("pmet_result_file")
    # showFeedbackDanger(inputId = "pmet_result_file", text = "Wrong format of uploaded file")
    return("WRONG_HEADER")
  }
  return("OK")
}


#' CreateMotifCombs: Create an empty data.frame with motif-motif combinations
#'
#' This function creates an empty data.frame with all pairs of motif-motif combinations in a long format.
#' The purpose is to be joined with PMET results or to store values associated with each motif combination.
#'
#' @param motifs A character vector specifying the motifs to create combinations from.
#'
#' @return An empty data.frame with motif-motif combinations in a long format.
#'
#' @examples
#' motifs <- c("motif1", "motif2", "motif3")
#' CreateMotifCombs(motifs)
#'         motif1 motif2 value
#'       1 motif1 motif1  NULL
#'       2 motif2 motif1  NULL
#'       3 motif3 motif1  NULL
#'       4 motif1 motif2  NULL
#'       5 motif2 motif2  NULL
#'       6 motif3 motif2  NULL
#'       7 motif1 motif3  NULL
#'       8 motif2 motif3  NULL
#'       9 motif3 motif3  NULL
#'
#' @keywords data.frame, motif combinations
#' @export
CreateMotifCombs <- function(motifs) {
  all <- data.frame(matrix(ncol = length(motifs), nrow = length(motifs))) %>%
    `colnames<-`(motifs) %>%
    `rownames<-`(motifs) %>%
    tibble::add_column(motif2 = motifs, .before = motifs[1]) %>%
    reshape2::melt("motif2") %>%
    setNames(c("motif1", "motif2", "value"))
  return(all)
}

#' MarkDuplicates: Mark elements with duplications
#'
#' This function marks all elements with duplications in a vector.
#'
#' @param vec A vector containing the elements to be checked for duplication.
#'
#' @return A logical vector indicating whether each element has duplicates.
#'
#' @examples
#' vec <- c(1, 2, 3, 2, 4, 2)
#' is_duplicated <- MarkDuplicates(vec)
#' # is_duplicated = FALSE  TRUE FALSE  TRUE FALSE  TRUE
#'
#' @keywords duplication, vector manipulation
#' @export
MarkDuplicates <- function(vec) {
  front <- duplicated(vec)
  back <- duplicated(vec, fromLast = TRUE)
  all_dup <- front + back > 0
  return(all_dup)
}

#' DiscardSharedItems: Remove shared motifs between motif clusters
#'
#' This function removes shared motifs between different motif clusters in a given motifs_list.
#'
#' @param motifs_list A list containing several motif clusters.
#'
#' @return Updated motif list with shared motifs removed between clusters.
#'
#' @examples
#' motifs_list <- list(
#'   cluster1 = c("motif1", "motif2", "motif3"),
#'   cluster2 = c("motif2", "motif3", "motif4"),
#'   cluster3 = c("motif4", "motif5", "motif6")
#' )
#' updated_motifs_list <- DiscardSharedItems(motifs_list)
#' # updated_motifs_list:
#     $cluster1
#     [1] "motif1"

#     $cluster2
#     character(0)
#
#     $cluster3
#     [1] "motif5" "motif6"
#'
#' @keywords motif clusters, shared motifs, list manipulation
#' @export
DiscardSharedItems <- function(motifs_list) {
  # Iterate over each cluster in the motifs_list
  motifs_list <- names(motifs_list) %>%
    lapply(function(clu) {
      motifs_clu <- motifs_list[[clu]]
      # Get motifs from other clusters
      motifs_rest <- motifs_list[setdiff(names(motifs_list), clu)] %>% unlist() %>% unique()
      # Remove shared motifs from the current cluster
      setdiff(motifs_clu, motifs_rest)
    }) %>%
    setNames(names(motifs_list))

  # Return the updated motif list
  return(motifs_list)
}

PmetHistogramPlot <- function(res            = NULL,
                              ncols          = NULL,
                              histgram_width = 6,
                              histgram_path  = "histgram_padj_before_filter.png") {

  clusters <- unique(res$cluster) %>% sort()

  colors <- COLORS[1:length(clusters)]
  names(colors) <- clusters

  if (is.null(ncols)) {
    ncols <- ifelse(length(clusters) > 1, 2, 1)
  }

  p <- lapply(clusters, function(clu) {
    res[, c("cluster", "p_adj")] %>% filter(cluster == clu) %>%
      ggplot( aes(x=p_adj, fill=cluster)) +
      geom_histogram( fill=colors[[clu]], alpha=0.6, position = 'identity') +
      theme_ipsum() +
      theme_bw()    +
      ggtitle(clu)  +
      labs(fill="")
  }) %>%
    ggarrange(plotlist=.,
              ncol=ncols,
              nrow = ceiling(length(clusters)/ncols))

  ggsave(histgram_path,
         p,
         dpi = 300,
         units="in",
         width  = histgram_width,
         height = (histgram_width / 3 ) * ceiling(length(clusters)/ncols),
         create.dir = TRUE)

  return(p)
}


# process PMET result
# 1. filter
# 2. remove duplicated combinations
# 3. split pmet result into different clusters
# 4. get motifs of PMET result in each cluster
# 5. get top motifs based on pvalues of PMET result
ProcessPmetResult <- function(pmet_result        = NULL,
                              p_adj_limt         = 0.05,
                              gene_portion       = 0.05,
                              topn               = 40,
                              max_motifs_in_plot = 30L,
                              histgram_dir       = NULL,
                              histgram_ncol      = 2,
                              histgram_width     = 6,
                              unique_cmbination  = TRUE) {
  # Note on `topn`: kept for backwards compatibility with callers that still
  # pass it; ignored by the new motif-selection path below. Final motif set
  # is bounded by `max_motifs_in_plot` instead.
  suppressMessages({

    clusters <- unique(pmet_result$cluster) %>% sort()
    colors <- COLORS[1:length(clusters)]
    names(colors) <- clusters

    ### 1.1 Histogram of p_adj
    ### 3.1 Histogram of p_adj
    if (!is.null(histgram_dir)) {
      PmetHistogramPlot(
        res            = pmet_result,
        ncols          = histgram_ncol,
        histgram_width = histgram_width,
        histgram_path  = file.path(histgram_dir, "histgram_padj_before_filter.png"))
    } # if

    ## 2. Full genes of each cluster
    genes.list <- clusters %>%
      lapply(function(clu) {
        genes <- pmet_result %>%
          filter(cluster == clu) %>%
          pull(genes) %>%
          paste(collapse = "") %>%
          str_split(pattern = ";")

        genes[[1]] %>% head(-1) %>% unique()
      }) %>%
      setNames(clusters)

    genes_list_length <- sapply(genes.list, length)

    ## 3. Filter data
    #     a. by p-value, < 0.0005
    #     b. by genes, > 5% * cycle genes
    pmet.filtered <- pmet_result
    for (clu in clusters) {
      gene_num_limt <- gene_portion * genes_list_length[[clu]]
      pmet.filtered <- pmet.filtered %>%
        filter(p_adj <= p_adj_limt) %>%
        filter((cluster == clu & gene_num > gene_num_limt) | cluster != clu) %>%
        arrange(desc(p_adj))
    }

    if (length(pmet.filtered$cluster) == 0) {
      return(NULL)
    }

    # update clusters every time after filtering
    clusters <- unique(pmet.filtered$cluster) %>% sort()

    ### 3.1 Histogram of p_adj
    if (!is.null(histgram_dir)) {
      PmetHistogramPlot(
        res            = pmet.filtered,
        ncols          = histgram_ncol,
        histgram_width = histgram_width,
        histgram_path  = file.path(histgram_dir, "histgram_padj_after_filter.png"))
    } # if

    ## 4. find and remove motif pairs that occur in multiple clusters
    if (unique_cmbination) {
      # MarkDuplicates returns a logical vector; previously this read
      # `MarkDuplicates(motif_pair) != "TRUE"`, which coerced both sides
      # to character and so did the right thing by accident. Use a plain
      # negation — same semantics, no implicit coercion.
      pmet.filtered <- pmet.filtered[which(!MarkDuplicates(motif_pair)), ]

      # update clusters every time after filtering
      clusters <- unique(pmet.filtered$cluster) %>% sort()
    }

    ## 5. Split pmet result by cluster (the empty `[, ]` selector was a no-op).
    pmet.filtered.split.list <- pmet.filtered %>% split(pmet.filtered$cluster)

    ## 5b. Score every motif per cluster by cumulative significance.
    ##     score(m | cluster) = sum( -log10(p_adj) ) over pairs containing m.
    ##     Floor p_adj at 1e-300 — BH adjusted values can underflow to 0 on
    ##     very significant pairs and -log10(0)=Inf would break sum().
    score_per_cluster <- clusters %>%
      lapply(function(clu) {
        dat <- pmet.filtered.split.list[[clu]] %>%
          mutate(neg_log_p = -log10(pmax(p_adj, 1e-300)))
        bind_rows(
          dat %>% select(motif = motif1, neg_log_p),
          dat %>% select(motif = motif2, neg_log_p)
        ) %>%
          group_by(motif) %>%
          summarise(score = sum(neg_log_p), .groups = "drop") %>%
          arrange(desc(score))
      }) %>%
      setNames(clusters)

    ## 5c. Per-cluster quota: divide the global cap by cluster count, but
    ##     never drop below 3 so even crowded plots show something for each
    ##     cluster.
    motifs_per_cluster <- max(3L, as.integer(floor(max_motifs_in_plot / length(clusters))))

    motifs_top_list <- score_per_cluster %>%
      lapply(function(scored) head(scored$motif, motifs_per_cluster)) %>%
      setNames(clusters)

    ## 5d. Secondary trim: when clusters share few motifs the union can
    ##     still exceed the cap. Rank globally by (#clusters present,
    ##     summed score) and intersect each cluster's top-K with the kept
    ##     set. Motifs hit by more clusters are preferred — they make the
    ##     cross-cluster comparison readable.
    motif_union <- motifs_top_list %>% unlist() %>% unique()
    if (length(motif_union) > max_motifs_in_plot) {
      global <- bind_rows(score_per_cluster, .id = "cluster") %>%
        filter(motif %in% motif_union) %>%
        group_by(motif) %>%
        summarise(global_score = sum(score),
                  n_clu        = n_distinct(cluster),
                  .groups      = "drop") %>%
        arrange(desc(n_clu), desc(global_score))
      kept <- head(global$motif, max_motifs_in_plot)
      motifs_top_list <- motifs_top_list %>%
        lapply(function(m) intersect(m, kept))
    }

    # keep the plot result to return later
    results <- list()
    results[["pmet_result"]] <- pmet.filtered.split.list
    results[["motifs"     ]] <- motifs_top_list
  })

  return(results)
}

#' Generate Top Motifs List
#'
#' This function generates a list of top motifs based on the input motif list.
#' The generated list can be further processed for analysis.
#'
#' @param motifs.list A list of motifs.
#' @param by.cluster A logical value indicating whether to group motifs by cluster.
#' @param exclusive.motifs A logical value indicating whether to remove shared motifs.
#' @return A list of top motifs.
#'
#' @examples
#' motifs_list <- list(cluster1 = c("motif1", "motif2", "motif10"),
#'                     cluster2 = c("motif1", "motif5", "motif6"))
#' top_motifs <- TopMotifsGenerator(motifs.list = motifs_list, by.cluster = TRUE)
#'
#' @importFrom dplyr %>%
#' @importFrom dplyr unlist
#' @importFrom dplyr unname
#' @importFrom dplyr unique
#' @importFrom dplyr sort
#' @importFrom . DiscardSharedItems
#'
#' @export
TopMotifsGenerator <- function( motifs.list = NULL,
                                by.cluster = FALSE,
                                exclusive.motifs = TRUE) {

  # remove shared motifs, if exclusive.motifs is TRUE
  if (exclusive.motifs) {
    motifs.list <- DiscardSharedItems(motifs.list)
  }
  # If parameters "by.cluster" and exclusive.motifs are set to TRUE, motifs
  # from the same cluster will be grouped together.
  if (by.cluster & exclusive.motifs) {
    motifs.top <- motifs.list %>% unlist() %>% unname()
  } else {
    # if not exclusive, motifs can be present in more than one cluster,
    # it is a problem to group together in the same cluster. So they will be
    # ordered by alphabet
    motifs.top <- motifs.list %>% unlist() %>% unique() %>% sort() %>% unname()
  }
  return(motifs.top)
}
