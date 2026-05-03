'use client';

import { useState, useMemo, useCallback, useRef, useEffect, Suspense } from 'react';
import dynamic from 'next/dynamic';
import { useSearchParams } from 'next/navigation';
import { useTranslation } from '@/lib/i18n';
import { resultsApi } from '@/lib/api';

const Plot = dynamic(() => import('react-plotly.js'), { ssr: false });

interface ClickedCell {
  cluster?: string;
  motif1: string;
  motif2: string;
  logp: number;
  pAdj: number;
  genes: string[];
  cellColor: string;
  // When set, the cell is an overlap: one entry per contributing cluster so
  // the modal can show them separately (tabs) instead of merging.
  overlapEntries?: Array<{
    cluster: string;
    color: string;
    logp: number;
    pAdj: number;
    genes: string[];
  }>;
}

interface MotifResult {
  cluster: string;
  motif1: string;
  motif2: string;
  gene_num: number;
  total_genes: number;
  cluster_genes: number;
  p_value: number;
  p_adj_bh: number;
  p_adj_bonf: number;
  p_adj_global: number;
  genes: string[];
  motif_pair: string;
}

type ActiveTab = 'heatmap' | 'motifs' | 'data';

const PAGE_SIZE = 20;

// Cluster identity colors — same palette as scripts/r/process_pmet_result.R's
// COLORS constant. Each entry is the "dark" end of the per-cluster gradient
// pair below; using one palette keeps the per-cluster heatmap, the Overlap
// legend, and the Motifs tab visually consistent with the R PNG output.
const CLUSTER_COLORS = [
  '#ed3333', // red
  '#1a94bc', // blue
  '#40a070', // green
  '#fc6315', // orange
  '#f9a633', // mustard
  '#8b2671', // purple
  '#2f2f35', // near-black
];

// Light → dark gradient pairs for the per-cluster heatmap, mirrored from
// scripts/r/motif_pair_plot_homog.R's `colors` list. Indexed by the
// cluster's alphabetical position; modulo wraps for >7 clusters.
const R_COLOR_PAIRS: Array<[string, string]> = [
  ['#fac3c3', '#ed3333'],
  ['#a2d5f5', '#1a94bc'],
  ['#baeed3', '#40a070'],
  ['#fda67a', '#fc6315'],
  ['#f9cb8b', '#f9a633'],
  ['#bb7fa9', '#8b2671'],
  ['#47484c', '#2f2f35'],
];

function parseRow(cols: string[]): MotifResult | null {
  if (cols.length < 8) return null;
  const p_bh = parseFloat(cols[7]);
  if (isNaN(p_bh)) return null;
  return {
    cluster: cols[0] ?? '',
    motif1: cols[1] ?? '',
    motif2: cols[2] ?? '',
    gene_num: parseInt(cols[3]) || 0,
    total_genes: parseInt(cols[4]) || 0,
    cluster_genes: parseInt(cols[5]) || 0,
    p_value: parseFloat(cols[6]) || 1,
    p_adj_bh: p_bh,
    p_adj_bonf: parseFloat(cols[8]) || 1,
    p_adj_global: parseFloat(cols[9]) || 1,
    genes: cols[10] ? cols[10].split(';').filter(Boolean) : [],
    motif_pair: `${cols[1]}^^${cols[2]}`,
  };
}

function parsePmetFile(text: string): MotifResult[] {
  const lines = text.split('\n');
  const results: MotifResult[] = [];
  for (let i = 1; i < lines.length; i++) {
    const line = lines[i].trim();
    if (!line) continue;
    const row = parseRow(line.split('\t'));
    if (row) results.push(row);
  }
  return results;
}

function markDuplicatePairs(results: MotifResult[]): Set<string> {
  const pairCount: Record<string, number> = {};
  for (const r of results) {
    pairCount[r.motif_pair] = (pairCount[r.motif_pair] || 0) + 1;
  }
  const dups = new Set<string>();
  for (const [pair, count] of Object.entries(pairCount)) {
    if (count > 1) dups.add(pair);
  }
  return dups;
}

// Mirror of scripts/r/process_pmet_result.R::ProcessPmetResult. The
// previous "top-N pairs, collect motifs from those pairs" heuristic
// produced a different motif set than the R-rendered PNG used in
// papers / CLI / QuickLook, so the on-screen heatmap was a different
// view of the same data. tests/integration/verify_heatmap_consistency.py
// runs both pipelines on the same fixture and exits non-zero on
// divergence — keep it green when touching this function.
//
// Algorithm (per cluster):
//   1. Filter pairs by p_adj_bonf <= limit AND gene_num > 5% of the
//      cluster's gene count (same upstream filters R uses).
//   2. (optional) drop motif pairs that appear in >1 cluster — the
//      "unique combination" toggle.
//   3. Score every motif by sum( -log10(max(p_adj, 1e-300)) ) across
//      all pairs containing it. The 1e-300 floor protects against
//      BH-adjusted underflow to 0 → -log10(0) = Inf → broken sums.
//   4. Per-cluster quota: floor(max_motifs / n_clusters), with a
//      hard floor of 3 so a crowded plot still shows something for
//      every cluster.
//   5. If the union still exceeds max_motifs, secondary global
//      reshuffle: rank motifs by (n_clusters_present desc, summed
//      score desc), keep the top max_motifs, intersect each
//      cluster's list with the kept set. This is what makes the
//      "All" view's columns line up across clusters.
function processPmetResult(
  raw: MotifResult[],
  pAdjLimit: number,
  maxMotifs: number,
  uniqueCombination: boolean
): { filtered: Record<string, MotifResult[]>; motifs: Record<string, string[]> } {
  // Count genes per cluster for gene_portion filter
  const genesPerCluster: Record<string, Set<string>> = {};
  for (const r of raw) {
    if (!genesPerCluster[r.cluster]) genesPerCluster[r.cluster] = new Set();
    for (const g of r.genes) genesPerCluster[r.cluster].add(g);
  }

  let filtered = raw.filter((r) => {
    if (r.p_adj_bonf > pAdjLimit) return false;
    const geneLimit = 0.05 * (genesPerCluster[r.cluster]?.size || 0);
    if (r.gene_num <= geneLimit) return false;
    return true;
  });

  if (uniqueCombination) {
    const dups = markDuplicatePairs(filtered);
    filtered = filtered.filter((r) => !dups.has(r.motif_pair));
  }

  const splitResult: Record<string, MotifResult[]> = {};
  for (const r of filtered) {
    if (!splitResult[r.cluster]) splitResult[r.cluster] = [];
    splitResult[r.cluster].push(r);
  }

  const clusters = Object.keys(splitResult).sort();

  // Per-cluster motif scoring. negLogP is the cluster-local
  // contribution of a single pair to each of its two motifs.
  const scorePerCluster: Record<string, Map<string, number>> = {};
  for (const clu of clusters) {
    const scores = new Map<string, number>();
    for (const r of splitResult[clu]) {
      const negLogP = -Math.log10(Math.max(r.p_adj_bonf, 1e-300));
      scores.set(r.motif1, (scores.get(r.motif1) ?? 0) + negLogP);
      scores.set(r.motif2, (scores.get(r.motif2) ?? 0) + negLogP);
    }
    scorePerCluster[clu] = scores;
  }

  const perClusterCap = Math.max(3, Math.floor(maxMotifs / Math.max(1, clusters.length)));
  const topPerCluster: Record<string, string[]> = {};
  for (const clu of clusters) {
    const sorted = [...scorePerCluster[clu].entries()]
      .sort((a, b) => b[1] - a[1])
      .slice(0, perClusterCap)
      .map((kv) => kv[0]);
    topPerCluster[clu] = sorted;
  }

  // Secondary trim — only kicks in when clusters share few motifs
  // and the union still exceeds the cap. Motifs hit by more clusters
  // are preferred since they make cross-cluster columns comparable.
  const union = new Set<string>();
  for (const clu of clusters) for (const m of topPerCluster[clu]) union.add(m);
  if (union.size > maxMotifs) {
    type Global = { motif: string; nClu: number; globalScore: number };
    const globalAgg = new Map<string, Global>();
    for (const clu of clusters) {
      for (const m of topPerCluster[clu]) {
        const score = scorePerCluster[clu].get(m) ?? 0;
        const cur = globalAgg.get(m);
        if (cur) {
          cur.nClu += 1;
          cur.globalScore += score;
        } else {
          globalAgg.set(m, { motif: m, nClu: 1, globalScore: score });
        }
      }
    }
    const ranked = [...globalAgg.values()].sort((a, b) => {
      if (b.nClu !== a.nClu) return b.nClu - a.nClu;
      return b.globalScore - a.globalScore;
    });
    const kept = new Set(ranked.slice(0, maxMotifs).map((g) => g.motif));
    for (const clu of clusters) {
      topPerCluster[clu] = topPerCluster[clu].filter((m) => kept.has(m));
    }
  }

  return { filtered: splitResult, motifs: topPerCluster };
}

// Cached 2d context for measuring label widths in real pixels. Falls back to
// a font-width ratio if the canvas is unavailable (e.g. during SSR).
let _measureCtx: CanvasRenderingContext2D | null = null;
function measureLabelPx(label: string, fontSize: number): number {
  if (typeof document === 'undefined') return label.length * fontSize * 0.7;
  if (!_measureCtx) {
    const c = document.createElement('canvas');
    _measureCtx = c.getContext('2d');
  }
  if (!_measureCtx) return label.length * fontSize * 0.7;
  _measureCtx.font = `${fontSize}px system-ui, -apple-system, "Segoe UI", Roboto, sans-serif`;
  return _measureCtx.measureText(label).width;
}

// Shared sizing rules for heatmap rendering — used by both the on-screen
// Plotly layout and the hidden render used for PNG download. Returning one
// object keeps the two paths from drifting apart (fonts, margins, label
// clipping, etc. must match the motif count and longest label length).
function computeHeatmapSizing(n: number, labels: string[], opts: { forDownload?: boolean; hideAxes?: boolean; availWidth?: number } = {}) {
  const forDownload = !!opts.forDownload;
  const hideAxes = !!opts.hideAxes;

  const naturalCellPx = forDownload
    ? n <= 10
      ? 56
      : n <= 20
        ? 44
        : n <= 35
          ? 36
          : n <= 60
            ? 28
            : 22
    : hideAxes
      ? n <= 5
        ? 40
        : n <= 10
          ? 28
          : n <= 20
            ? 22
            : n <= 35
              ? 18
              : n <= 60
                ? 14
                : 12
      : n <= 5
        ? 48
        : n <= 10
          ? 32
          : n <= 20
            ? 24
            : n <= 35
              ? 20
              : n <= 60
                ? 16
                : 13;

  const labelFontSize = forDownload ? (n <= 10 ? 18 : n <= 20 ? 16 : n <= 35 ? 14 : n <= 60 ? 12 : 11) : n <= 10 ? 12 : n <= 20 ? 11 : n <= 35 ? 10 : n <= 60 ? 9 : 8;

  const titleFontSize = forDownload ? Math.round(labelFontSize * 1.6) : 13;
  const cbFontSize = forDownload ? Math.max(11, labelFontSize - 2) : 9;

  // Measure the real rendered width of the widest label so rotated x-axis
  // labels and long y-axis labels never get clipped.
  const maxLabelPx = Math.ceil(Math.max(0, ...labels.map((s) => measureLabelPx(String(s), labelFontSize))));
  // tick mark (outside) + padding Plotly adds between plot edge and label
  const tickBuffer = 16;
  const labelPx = maxLabelPx + tickBuffer;

  // Layout split:
  //   forDownload=true  → title + horizontal colorbar live in the top margin
  //                       (matches the PNG export everyone is used to).
  //   forDownload=false → title is rendered as a JSX <div> above the Plot
  //                       so it can wrap/overflow on narrow panels and never
  //                       collides with the colorbar; the colorbar lives on
  //                       the right (vertical), giving small heatmaps room
  //                       to breathe.
  const colorbarOrientation: 'h' | 'v' = forDownload ? 'h' : 'v';
  const cbThickness = forDownload
    ? Math.max(10, labelFontSize * 0.7)
    : Math.max(10, labelFontSize);
  const topForHeader = forDownload
    ? Math.round(titleFontSize + cbFontSize * 2 + 32)
    : 8;
  const rightForColorbar = forDownload ? 16 : cbThickness + 60; // ticks + cb title

  const margin = hideAxes
    ? { t: topForHeader, b: 8, l: 8, r: rightForColorbar }
    : { t: topForHeader, b: labelPx, l: labelPx, r: rightForColorbar };

  // When an availWidth is provided (on-screen adaptive layout), shrink
  // cellPx to fit that budget — but never below a legibility floor and
  // never above the natural size.
  let cellPx = naturalCellPx;
  if (opts.availWidth && opts.availWidth > 0) {
    const target = Math.floor((opts.availWidth - margin.l - margin.r) / Math.max(1, n));
    const minCell = hideAxes ? 8 : 10;
    cellPx = Math.max(minCell, Math.min(naturalCellPx, target));
  }

  const plotArea = n * cellPx;
  const width = plotArea + margin.l + margin.r;
  const height = plotArea + margin.t + margin.b;

  return {
    cellPx,
    labelFontSize,
    titleFontSize,
    cbFontSize,
    labelPx,
    margin,
    width,
    height,
    naturalCellPx,
    colorbarOrientation,
    cbThickness,
  };
}

function discardSharedMotifs(motifsMap: Record<string, string[]>): Record<string, string[]> {
  const result: Record<string, string[]> = {};
  const clusterNames = Object.keys(motifsMap);
  for (const clu of clusterNames) {
    const others = new Set(clusterNames.filter((c) => c !== clu).flatMap((c) => motifsMap[c]));
    result[clu] = motifsMap[clu].filter((m) => !others.has(m));
  }
  return result;
}

function VisualizePageContent() {
  const { t } = useTranslation();
  const [allResults, setAllResults] = useState<MotifResult[]>([]);
  const [fileName, setFileName] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [dragOver, setDragOver] = useState(false);

  const [uniquePairs, setUniquePairs] = useState(true);
  const [selectedCluster, setSelectedCluster] = useState('All');
  // Total motif cap on the heatmap. Was previously called `topN` and
  // defaulted to 5, matching the old "top-N pair" semantics; with the
  // new scoring algorithm (see processPmetResult) it's a global motif
  // cap and 30 is the same default R uses everywhere else.
  const [maxMotifs, setMaxMotifs] = useState(30);
  const [pAdj, setPAdj] = useState(0.05);
  const [activeTab, setActiveTab] = useState<ActiveTab>('heatmap');
  const [showAxes, setShowAxes] = useState(true);
  const [tablePage, setTablePage] = useState(0);
  const [pageSize, setPageSize] = useState(PAGE_SIZE);
  const [searchQuery, setSearchQuery] = useState('');
  const [sortCol, setSortCol] = useState<string>('p_adj_bh');
  const [sortAsc, setSortAsc] = useState(true);
  const [clickedCell, setClickedCell] = useState<ClickedCell | null>(null);
  const [modalTabIdx, setModalTabIdx] = useState(0);
  const plotRefs = useRef<Map<string, any>>(new Map());
  const contentRef = useRef<HTMLDivElement | null>(null);
  const [contentWidth, setContentWidth] = useState(0);

  useEffect(() => {
    const el = contentRef.current;
    if (!el) return;
    const ro = new ResizeObserver((entries) => {
      for (const entry of entries) setContentWidth(entry.contentRect.width);
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, [allResults.length]);

  const handleFile = useCallback((file: File) => {
    setError(null);
    const lower = file.name.toLowerCase();
    if (!lower.endsWith('.txt') && !lower.endsWith('.tsv')) {
      setError(t('viz.err.bad_type'));
      return;
    }
    const reader = new FileReader();
    reader.onload = () => {
      const results = parsePmetFile(reader.result as string);
      if (results.length === 0) {
        setError(t('viz.err.no_rows'));
        return;
      }
      setAllResults(results);
      setFileName(file.name);
      setSelectedCluster('All');
      setTablePage(0);
    };
    reader.readAsText(file);
  }, [t]);

  const loadExample = useCallback(async () => {
    setError(null);
    try {
      const API_URL = process.env.NEXT_PUBLIC_API_URL ?? '';
      const res = await fetch(`${API_URL}/api/demo/example-result`);
      if (!res.ok) throw new Error(t('viz.err.example_load'));
      const text = await res.text();
      const results = parsePmetFile(text);
      if (results.length === 0) throw new Error(t('viz.err.example_empty'));
      setAllResults(results);
      setFileName('example_pmet_result.txt');
      setSelectedCluster('All');
      setTablePage(0);
    } catch {
      setError(t('viz.err.example_failed'));
    }
  }, [t]);

  const onDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setDragOver(false);
      const dropped = e.dataTransfer.files[0];
      if (dropped) handleFile(dropped);
    },
    [handleFile]
  );

  // Task source: when the page is opened as `/visualize?task=<id>` (from
  // the task detail page's "Open in Viewer" CTA), fetch the raw
  // motif_output.txt and feed it through the same parsePmetFile() the
  // upload-zone path uses. Earlier this went through resultsApi.get
  // (paginated JSON), but that endpoint caps at 5000 rows in pair_parallel's
  // file-order layout; large tasks (e.g. pmet_04359f067bbd, 18984 rows
  // with 360 Bonf-significant pairs spread throughout) saw truncated
  // input → wrong motif scoring → wrong heatmap vs the R-rendered PNG.
  // The raw endpoint streams the full file, no cap, and parsePmetFile
  // is the same function the upload zone already uses → both paths
  // are now byte-for-byte equivalent.
  const searchParams = useSearchParams();
  const taskParam = searchParams?.get('task') ?? null;
  useEffect(() => {
    if (!taskParam) return;
    let cancelled = false;
    (async () => {
      try {
        const text = await resultsApi.raw(taskParam);
        if (cancelled) return;
        const results = parsePmetFile(text);
        if (results.length === 0) {
          setError(t('viz.err.no_rows'));
          return;
        }
        setAllResults(results);
        setFileName(`Task ${taskParam}`);
        setSelectedCluster('All');
        setTablePage(0);
      } catch {
        if (!cancelled) setError(t('viz.err.task_load'));
      }
    })();
    return () => { cancelled = true; };
  }, [taskParam, t]);

  // Process data
  const processed = useMemo(() => {
    if (allResults.length === 0) return null;
    return processPmetResult(allResults, pAdj, maxMotifs, uniquePairs);
  }, [allResults, pAdj, maxMotifs, uniquePairs]);

  const clusters = useMemo(() => (processed ? Object.keys(processed.filtered).sort() : []), [processed]);

  // Stable cluster → color map shared by heatmap, motifs tab, and data viewer.
  const clusterColorMap = useMemo(() => {
    const map: Record<string, string> = {};
    clusters.forEach((c, i) => {
      map[c] = CLUSTER_COLORS[i % CLUSTER_COLORS.length];
    });
    return map;
  }, [clusters]);

  // Cluster → [light, dark] gradient pair for per-cluster heatmaps, in the
  // same alphabetical-cluster-order R uses (see motif_pair_plot_homog.R).
  const clusterPairMap = useMemo(() => {
    const map: Record<string, [string, string]> = {};
    clusters.forEach((c, i) => {
      map[c] = R_COLOR_PAIRS[i % R_COLOR_PAIRS.length];
    });
    return map;
  }, [clusters]);

  const clusterOptions = useMemo(() => {
    if (!processed) return [];
    if (uniquePairs) {
      return ['Overlap', 'All', ...clusters];
    }
    return ['All', ...clusters];
  }, [processed, uniquePairs, clusters]);

  // Validate p_adj
  const pAdjWarning = useMemo(() => {
    if (allResults.length === 0 || !processed) return null;
    const allFiltered = Object.values(processed.filtered).flat();
    if (allFiltered.length === 0) {
      return t('viz.err.no_filter_data');
    }
    return null;
  }, [allResults, processed, t]);

  // Build heatmap data
  const heatmapData = useMemo(() => {
    if (!processed) return null;

    const motifsMap = processed.motifs;

    // Match R's TopMotifsGenerator(by.cluster=FALSE, exclusive.motifs=FALSE):
    // axis = union of every cluster's top motifs, sorted alphabetically.
    // Shared motifs across clusters are kept — R's draw_heatmap.R passes
    // exclusive_motifs=FALSE.
    const allMotifs = [...new Set(Object.values(motifsMap).flat())].sort();
    if (allMotifs.length === 0) return null;

    const clusterColors = clusterColorMap;

    // Helper: build z and hovertext matrices with lower-triangle masking.
    // In the matrix z[yi][xi], lower triangle = yi >= xi (including diagonal).
    // Upper triangle values are set to null so they render as blank.
    const buildMatrices = (motifList: string[], lookup: Map<string, { p: number; genes: string[]; cluster?: string }>, showCluster = false) => {
      const z: (number | null)[][] = [];
      const hovertext: string[][] = [];
      const customdata: (any | null)[][] = [];
      for (let yi = 0; yi < motifList.length; yi++) {
        const zRow: (number | null)[] = [];
        const hRow: string[] = [];
        const cdRow: (any | null)[] = [];
        for (let xi = 0; xi < motifList.length; xi++) {
          if (yi < xi) {
            zRow.push(null);
            hRow.push('');
            cdRow.push(null);
          } else {
            const m1 = motifList[xi];
            const m2 = motifList[yi];
            const v = lookup.get(`${m1}|${m2}`) || lookup.get(`${m2}|${m1}`);
            if (v && v.p < 1) {
              const logp = -Math.log10(Math.max(v.p, 1e-300));
              zRow.push(logp);
              // Keep the hover tooltip compact — the full gene list and
              // adjusted p-value live in the click modal. A small tooltip
              // avoids obscuring the chart under the cursor.
              const header = showCluster && v.cluster ? `<b>${v.cluster}</b> · ${m1} × ${m2}` : `${m1} × ${m2}`;
              hRow.push(`${header}<br>-log10(p): ${logp.toFixed(2)}  ·  ${v.genes.length} genes`);
              cdRow.push({
                motif1: m1,
                motif2: m2,
                logp,
                pAdj: v.p,
                genes: v.genes,
                cluster: showCluster ? v.cluster : undefined,
              });
            } else {
              // No significant entry for this cell — render transparent so
              // the gradient's low end isn't reused for "missing data"
              // (matches R's na.value = "white" behaviour).
              zRow.push(null);
              hRow.push('');
              cdRow.push(null);
            }
          }
        }
        z.push(zRow);
        hovertext.push(hRow);
        customdata.push(cdRow);
      }
      return { z, hovertext, customdata };
    };

    if (selectedCluster === 'Overlap') {
      // Overlap mode:
      //   - axes = union of each cluster's *exclusive* top motifs
      //   - cells contributed by exactly one cluster → that cluster's color,
      //     shaded by -log10(p.adj)
      //   - cells contributed by 2+ clusters → uniform black ("Overlapped"),
      //     with hover info listing every contributing cluster
      //
      // Implementation note: we render ONE heatmap trace so Plotly's hover
      // always picks the correct cell (stacking multiple traces hides the
      // hover of lower layers under null cells of higher layers). The cluster
      // identity is encoded into the z value's integer band, and a
      // multi-band colorscale turns each band into white→cluster_color, with
      // the final band being a solid black for overlaps.
      type Entry = { cluster: string; p: number; genes: string[] };
      const cellEntries = new Map<string, Entry[]>();
      for (const clu of clusters) {
        for (const r of processed.filtered[clu] || []) {
          if (allMotifs.includes(r.motif1) && allMotifs.includes(r.motif2)) {
            const key = `${r.motif1}|${r.motif2}`;
            const list = cellEntries.get(key) || [];
            if (!list.some((e) => e.cluster === clu)) {
              list.push({ cluster: clu, p: r.p_adj_bonf, genes: r.genes });
            }
            cellEntries.set(key, list);
          }
        }
      }

      // Global max -log10(p) across singly-assigned cells — drives intensity.
      let maxLogp = 0;
      for (const entries of cellEntries.values()) {
        if (entries.length !== 1) continue;
        const lp = -Math.log10(Math.max(entries[0].p, 1e-300));
        if (lp > maxLogp) maxLogp = lp;
      }
      if (!(maxLogp > 0)) maxLogp = 1;

      const clusterIdx: Record<string, number> = {};
      clusters.forEach((c, i) => { clusterIdx[c] = i; });

      const N = clusters.length;
      const BANDS = N + 1;              // N cluster bands + 1 overlap band
      const OVERLAP_BAND = N;           // last band
      const INTENSITY_FLOOR = 0.35;     // keep weak signals visible (echoes R's alpha 0.3–1)

      const z: (number | null)[][] = [];
      const hovertext: string[][] = [];
      const customdata: (any | null)[][] = [];

      for (let yi = 0; yi < allMotifs.length; yi++) {
        const zRow: (number | null)[] = [];
        const hRow: string[] = [];
        const cdRow: (any | null)[] = [];
        for (let xi = 0; xi < allMotifs.length; xi++) {
          if (yi < xi) { zRow.push(null); hRow.push(''); cdRow.push(null); continue; }
          const m1 = allMotifs[xi];
          const m2 = allMotifs[yi];
          const entries = cellEntries.get(`${m1}|${m2}`) || cellEntries.get(`${m2}|${m1}`);
          if (!entries || entries.length === 0) {
            zRow.push(null); hRow.push(''); cdRow.push(null); continue;
          }
          if (entries.length === 1) {
            const e = entries[0];
            const band = clusterIdx[e.cluster];
            const logp = -Math.log10(Math.max(e.p, 1e-300));
            const frac = INTENSITY_FLOOR + (1 - INTENSITY_FLOOR) * 0.95 * Math.min(1, logp / maxLogp);
            zRow.push(band + frac);
            hRow.push(
              `<b>${e.cluster}</b> · ${m1} × ${m2}<br>` +
              `-log10(p): ${logp.toFixed(2)}  ·  ${e.genes.length} genes`,
            );
            cdRow.push({
              motif1: m1, motif2: m2, logp, pAdj: e.p, genes: e.genes, cluster: e.cluster,
            });
          } else {
            // Overlap cell: uniform black, hover lists every contributing cluster.
            zRow.push(OVERLAP_BAND + 0.5);
            const lines = entries.map((e) => {
              const lp = -Math.log10(Math.max(e.p, 1e-300));
              const col = clusterColors[e.cluster] || '#475569';
              return `<span style="color:${col}">■</span> <b>${e.cluster}</b> — -log10(p): ${lp.toFixed(2)}, ${e.genes.length} genes`;
            });
            hRow.push(`<b>Overlapped</b> · ${m1} × ${m2}<br>${lines.join('<br>')}`);
            cdRow.push({
              motif1: m1, motif2: m2,
              logp: Math.max(...entries.map((e) => -Math.log10(Math.max(e.p, 1e-300)))),
              pAdj: Math.min(...entries.map((e) => e.p)),
              genes: Array.from(new Set(entries.flatMap((e) => e.genes))),
              cluster: `Overlapped: ${entries.map((e) => e.cluster).join(', ')}`,
              isOverlap: true,
              overlapEntries: entries,
            });
          }
        }
        z.push(zRow); hovertext.push(hRow); customdata.push(cdRow);
      }

      // Multi-band colorscale: each cluster band = white→cluster_color,
      // overlap band = solid black. Adjacent stops at the same normalized
      // value create sharp band boundaries (no bleeding between clusters).
      const stops: Array<[number, string]> = [];
      for (let i = 0; i < N; i++) {
        stops.push([i / BANDS, '#ffffff']);
        stops.push([(i + 1) / BANDS, clusterColors[clusters[i]]]);
      }
      stops.push([OVERLAP_BAND / BANDS, '#000000']);
      stops.push([1, '#000000']);

      const legendItems = [
        ...clusters.map((c) => ({ cluster: c, color: clusterColors[c] })),
        { cluster: 'Overlapped', color: '#000000' },
      ];

      return {
        x: allMotifs, y: allMotifs,
        z, hovertext, customdata,
        colorscale: stops,
        zmin: 0, zmax: BANDS,
        legendItems,
        // Surface the intensity range so the JSX legend can show users the
        // -log10(p.adj) span the cell shading covers.
        intensityMax: maxLogp,
        intensityFloor: INTENSITY_FLOOR,
        mode: 'overlap' as const,
      };
    }

    if (selectedCluster === 'All') {
      // R: respective.plot = FALSE — every cluster gets a panel on the
      // shared `allMotifs` axis. No exclusive-motif gating, so a cluster
      // whose top motifs are all shared with others still renders.
      const perCluster = clusters.map((clu) => {
        const lookup = new Map<string, { p: number; genes: string[] }>();
        for (const r of processed.filtered[clu] || []) {
          if (allMotifs.includes(r.motif1) && allMotifs.includes(r.motif2)) {
            lookup.set(`${r.motif1}|${r.motif2}`, { p: r.p_adj_bonf, genes: r.genes });
          }
        }
        const { z, hovertext, customdata } = buildMatrices(allMotifs, lookup);
        return {
          cluster: clu,
          z,
          hovertext,
          customdata,
          color: clusterColors[clu],
          pair: clusterPairMap[clu] || R_COLOR_PAIRS[0],
        };
      });

      // Shared color limits across every panel — matches R's
      // motif_pair_plot_homog.R where `value.min`/`value.max` are computed
      // from rbind'd plot_data_list and reused as `limits` for every panel.
      let zmin = Infinity;
      let zmax = -Infinity;
      for (const pc of perCluster) {
        for (const row of pc.z) {
          for (const v of row) {
            if (v == null) continue;
            if (v < zmin) zmin = v;
            if (v > zmax) zmax = v;
          }
        }
      }
      if (!isFinite(zmin) || !isFinite(zmax)) {
        zmin = 0;
        zmax = 1;
      } else if (zmin === zmax) {
        // Single-value edge case — give Plotly a non-degenerate range so
        // the cell renders at the dark end rather than mid-gradient.
        zmax = zmin + 1;
      }

      return { x: allMotifs, y: allMotifs, perCluster, zmin, zmax, mode: 'all' as const };
    }

    // Single cluster
    const clu = selectedCluster;
    const cluMotifs = [...new Set([...(motifsMap[clu] || [])])].sort();
    if (cluMotifs.length === 0) return null;
    const lookup = new Map<string, { p: number; genes: string[] }>();
    for (const r of processed.filtered[clu] || []) {
      lookup.set(`${r.motif1}|${r.motif2}`, { p: r.p_adj_bonf, genes: r.genes });
    }
    const { z, hovertext, customdata } = buildMatrices(cluMotifs, lookup);
    return {
      x: cluMotifs,
      y: cluMotifs,
      z,
      hovertext,
      customdata,
      mode: 'single' as const,
      color: clusterColors[clu],
      pair: clusterPairMap[clu] || R_COLOR_PAIRS[0],
      clusterName: clu,
    };
  }, [processed, selectedCluster, clusters, clusterColorMap, clusterPairMap]);

  // Motifs tab: per-cluster list + which motifs are exclusive to each cluster.
  const motifsByCluster = useMemo(() => {
    if (!processed) return null;
    const names = Object.keys(processed.motifs).sort();
    const exclusive = discardSharedMotifs(processed.motifs);
    return names.map((clu) => {
      const all = [...processed.motifs[clu]].sort();
      const exclSet = new Set(exclusive[clu]);
      return {
        cluster: clu,
        color: clusterColorMap[clu] || '#64748b',
        all,
        exclusiveCount: exclSet.size,
        isExclusive: (m: string) => exclSet.has(m),
      };
    });
  }, [processed, clusterColorMap]);

  const copyClusterMotifs = useCallback((motifs: string[]) => {
    navigator.clipboard?.writeText(motifs.join('\n'));
  }, []);

  const downloadMotifsTsv = useCallback(() => {
    if (!motifsByCluster) return;
    const rows: string[] = ['cluster\tmotif\texclusive'];
    for (const c of motifsByCluster) {
      for (const m of c.all) {
        rows.push(`${c.cluster}\t${m}\t${c.isExclusive(m) ? 'yes' : 'no'}`);
      }
    }
    const blob = new Blob([rows.join('\n')], { type: 'text/tab-separated-values' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    const base = fileName.replace(/\.(txt|tsv)$/i, '') || 'pmet';
    a.download = `${base}_top_motifs.tsv`;
    a.click();
    URL.revokeObjectURL(url);
  }, [motifsByCluster, fileName]);

  // Data viewer
  const tableData = useMemo(() => {
    if (!processed) return [];
    let data: MotifResult[];
    if (selectedCluster === 'All' || selectedCluster === 'Overlap') {
      data = Object.values(processed.filtered).flat();
    } else {
      data = processed.filtered[selectedCluster] || [];
    }
    if (searchQuery) {
      const q = searchQuery.toLowerCase();
      data = data.filter(
        (r) => r.cluster.toLowerCase().includes(q) || r.motif1.toLowerCase().includes(q) || r.motif2.toLowerCase().includes(q) || r.genes.some((g) => g.toLowerCase().includes(q))
      );
    }
    const dir = sortAsc ? 1 : -1;
    data = [...data].sort((a, b) => {
      const av = a[sortCol as keyof MotifResult];
      const bv = b[sortCol as keyof MotifResult];
      if (typeof av === 'number' && typeof bv === 'number') return (av - bv) * dir;
      return String(av).localeCompare(String(bv)) * dir;
    });
    return data;
  }, [processed, selectedCluster, searchQuery, sortCol, sortAsc]);

  const tablePages = Math.ceil(tableData.length / pageSize);
  const pageData = tableData.slice(tablePage * pageSize, (tablePage + 1) * pageSize);

  const handleSort = (col: string) => {
    if (sortCol === col) {
      setSortAsc(!sortAsc);
    } else {
      setSortCol(col);
      setSortAsc(true);
    }
    setTablePage(0);
  };
  const sortIcon = (col: string) => (sortCol === col ? (sortAsc ? ' ▲' : ' ▼') : '');

  const downloadHeatmap = useCallback(async () => {
    // plotRefs entries are now { gd, title, color } — older path stored the
    // raw graph div directly, so fall back when an entry is a plain DOM node.
    const entries = Array.from(plotRefs.current.entries())
      .map(([k, v]) => {
        const gd = v && v.gd ? v.gd : v;
        const title: string | undefined = v && v.gd ? v.title : undefined;
        const color: string | undefined = v && v.gd ? v.color : undefined;
        return [k, { gd, title, color }] as const;
      })
      .filter(([, v]) => v.gd && document.body.contains(v.gd) && v.gd.data && v.gd.layout);
    if (entries.length === 0) return;
    const Plotly: any = (await import('plotly.js/dist/plotly' as any)).default ?? (window as any).Plotly;
    if (!Plotly?.toImage || !Plotly?.newPlot) {
      alert(t('viz.alert.plot_not_ready'));
      return;
    }
    const base = fileName.replace(/\.(txt|tsv)$/i, '') || 'pmet';
    const SCALE = 2; // device-pixel multiplier for the final PNG

    // Render each heatmap into a hidden div with a layout sized to the
    // motif count, so axis labels stay legible at any scale.
    const renderTile = async (gd: any, tileTitle?: string, tileColor?: string): Promise<{ img: HTMLImageElement; w: number; h: number }> => {
      const srcData = gd.data || [];
      const xLabels: string[] = (srcData[0]?.x as string[]) || [];
      const yLabels: string[] = (srcData[0]?.y as string[]) || [];
      const n = Math.max(xLabels.length, yLabels.length, 1);
      const s = computeHeatmapSizing(n, [...xLabels, ...yLabels], { forDownload: true });
      const { labelFontSize, titleFontSize, cbFontSize, margin, width: w, height: h } = s;

      const data = JSON.parse(JSON.stringify(srcData));
      if (data[0]) {
        data[0].colorbar = {
          ...(data[0].colorbar || {}),
          title: {
            text: '-log10(p.adj)',
            side: 'right',
            font: { size: cbFontSize },
          },
          orientation: 'h',
          x: 0.5,
          xanchor: 'center',
          y: 1.04,
          yanchor: 'bottom',
          len: 0.45,
          thickness: Math.max(10, labelFontSize * 0.7),
          tickfont: { size: cbFontSize - 1 },
        };
      }

      const baseLayout = gd.layout || {};
      // On-screen renders the panel title in JSX (so it can wrap on narrow
      // panels). For the PNG we re-attach it as a Plotly annotation so the
      // image is self-contained.
      const baseAnnotations = (baseLayout.annotations || []).map((a: any) => ({
        ...a,
        font: { ...(a.font || {}), size: titleFontSize },
        y: 1.12,
      }));
      const titleAnnotation = tileTitle
        ? [{
            text: `<b>${tileTitle}</b>`,
            font: { size: titleFontSize, color: tileColor || '#334155' },
            xref: 'paper' as const,
            yref: 'paper' as const,
            x: 0,
            y: 1.14,
            xanchor: 'left' as const,
            yanchor: 'bottom' as const,
            showarrow: false,
          }]
        : [];
      const annotations = [...baseAnnotations, ...titleAnnotation];

      const layout = {
        ...baseLayout,
        width: w,
        height: h,
        margin,
        annotations,
        xaxis: {
          ...(baseLayout.xaxis || {}),
          showticklabels: true,
          ticks: 'outside',
          tickangle: 90,
          tickfont: { size: labelFontSize },
          side: 'bottom',
          automargin: false,
          constrain: 'domain',
        },
        yaxis: {
          ...(baseLayout.yaxis || {}),
          showticklabels: true,
          ticks: 'outside',
          tickfont: { size: labelFontSize },
          autorange: 'reversed',
          scaleanchor: 'x',
          scaleratio: 1,
          automargin: false,
          constrain: 'domain',
        },
      };

      const hidden = document.createElement('div');
      hidden.style.position = 'fixed';
      hidden.style.left = '-100000px';
      hidden.style.top = '0';
      hidden.style.width = `${w}px`;
      hidden.style.height = `${h}px`;
      hidden.style.pointerEvents = 'none';
      document.body.appendChild(hidden);

      try {
        await Plotly.newPlot(hidden, data, layout, { displayModeBar: false, staticPlot: true });
        const url: string = await Plotly.toImage(hidden, {
          format: 'png',
          width: w,
          height: h,
          scale: SCALE,
        });
        const img = new Image();
        await new Promise<void>((resolve, reject) => {
          img.onload = () => resolve();
          img.onerror = () => reject(new Error('image load failed'));
          img.src = url;
        });
        return { img, w: w * SCALE, h: h * SCALE };
      } finally {
        try {
          Plotly.purge(hidden);
        } catch {
          /* ignore */
        }
        if (hidden.parentNode) hidden.parentNode.removeChild(hidden);
      }
    };

    const tiles = await Promise.all(
      entries.map(([, v]) => renderTile(v.gd, v.title, v.color))
    );

    // Single heatmap — download the rendered tile directly
    if (tiles.length === 1) {
      const { img } = tiles[0];
      const a = document.createElement('a');
      a.href = img.src;
      a.download = `${base}_heatmap.png`;
      a.click();
      return;
    }

    // Multiple heatmaps — composite into a grid on one canvas
    const n = tiles.length;
    const cols = n <= 3 ? n : Math.ceil(Math.sqrt(n));
    const rows = Math.ceil(n / cols);
    const tileW = Math.max(...tiles.map((t) => t.w));
    const tileH = Math.max(...tiles.map((t) => t.h));
    const gap = Math.round(24 * SCALE);
    const outerPad = Math.round(40 * SCALE);
    const headerH = Math.round(80 * SCALE);

    const canvasW = outerPad * 2 + cols * tileW + (cols - 1) * gap;
    const canvasH = outerPad * 2 + headerH + rows * tileH + (rows - 1) * gap;
    const canvas = document.createElement('canvas');
    canvas.width = canvasW;
    canvas.height = canvasH;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    ctx.fillStyle = '#ffffff';
    ctx.fillRect(0, 0, canvasW, canvasH);

    ctx.fillStyle = '#0f172a';
    ctx.font = `bold ${Math.round(28 * SCALE)}px system-ui, -apple-system, sans-serif`;
    ctx.textBaseline = 'top';
    ctx.fillText('PMET Motif-Pair Enrichment Heatmaps', outerPad, outerPad);
    ctx.fillStyle = '#64748b';
    ctx.font = `${Math.round(16 * SCALE)}px system-ui, -apple-system, sans-serif`;
    ctx.fillText(fileName || 'results', outerPad, outerPad + Math.round(36 * SCALE));

    tiles.forEach(({ img, w, h }, i) => {
      const r = Math.floor(i / cols);
      const c = i % cols;
      // Center each tile within its cell when sizes vary slightly
      const x = outerPad + c * (tileW + gap) + Math.round((tileW - w) / 2);
      const y = outerPad + headerH + r * (tileH + gap) + Math.round((tileH - h) / 2);
      ctx.drawImage(img, x, y, w, h);
    });

    canvas.toBlob((blob) => {
      if (!blob) return;
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${base}_heatmaps.png`;
      a.click();
      URL.revokeObjectURL(url);
    }, 'image/png');
  }, [fileName, t]);

  const downloadTsv = useCallback(() => {
    if (tableData.length === 0) return;
    const header = ['Cluster', 'Motif1', 'Motif2', 'Genes', 'Total_Genes', 'Cluster_Genes', 'P_value', 'P_adj_BH', 'P_adj_Bonf', 'P_adj_Global', 'Gene_List'];
    const rows = tableData.map((r) =>
      [r.cluster, r.motif1, r.motif2, r.gene_num, r.total_genes, r.cluster_genes, r.p_value, r.p_adj_bh, r.p_adj_bonf, r.p_adj_global, r.genes.join(';')].join('\t')
    );
    const blob = new Blob([header.join('\t') + '\n' + rows.join('\n')], { type: 'text/tab-separated-values' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `pmet_filtered_${selectedCluster}.tsv`;
    a.click();
    URL.revokeObjectURL(url);
  }, [tableData, selectedCluster]);

  // Upload view
  if (allResults.length === 0) {
    return (
      <div className="max-w-5xl mx-auto py-8">
        <h1 className="text-2xl font-bold mb-2">{t('viz.title')}</h1>
        <p className="text-slate-600 mb-8">{t('viz.intro')}</p>

        <div className="card">
          <h3 className="font-semibold mb-1 text-red-600">{t('viz.choose.heading')}</h3>
          <div
            className={`border-2 border-dashed rounded-lg p-10 text-center transition-colors ${
              dragOver ? 'border-teal-400 bg-teal-50' : 'border-slate-300 hover:border-slate-400'
            }`}
            onDragOver={(e) => {
              e.preventDefault();
              setDragOver(true);
            }}
            onDragLeave={() => setDragOver(false)}
            onDrop={onDrop}
          >
            <div className="space-y-3">
              <div className="text-4xl">&#128202;</div>
              <p className="text-slate-600">
                {t('viz.dnd.before')}{' '}
                <label className="text-teal-700 hover:text-teal-800 underline cursor-pointer">
                  {t('viz.dnd.browse')}
                  <input
                    type="file"
                    className="hidden"
                    accept=".txt,.tsv"
                    onChange={(e) => {
                      const f = e.target.files?.[0];
                      if (f) handleFile(f);
                    }}
                  />
                </label>
              </p>
              <p className="text-xs text-slate-400">{t('viz.dnd.accepts')}</p>
            </div>
          </div>

          <button onClick={loadExample} className="mt-3 text-sm text-teal-700 hover:text-teal-800 underline">
            {t('viz.example')}
          </button>

          {error && <div className="mt-4 text-sm text-red-600 bg-red-50 rounded p-3">{error}</div>}
        </div>
      </div>
    );
  }

  return (
    <div className="flex gap-6">
      {/* Sidebar */}
      <div className="w-80 shrink-0 space-y-5">
        <div className="card">
          <h3 className="font-semibold text-sm mb-3">{t('viz.side.file')}</h3>
          <p className="text-sm text-slate-700 truncate" title={fileName}>
            {fileName}
          </p>
          <p className="text-xs text-slate-400">{allResults.length.toLocaleString()} {t('viz.side.rows')}</p>
          <div className="mt-3 flex gap-3">
            <button
              className="text-xs text-slate-500 hover:text-slate-700 underline"
              onClick={() => {
                setAllResults([]);
                setFileName('');
              }}
            >
              {t('viz.side.upload_another')}
            </button>
            <button onClick={loadExample} className="text-xs text-teal-700 hover:text-teal-800 underline">
              {t('viz.example')}
            </button>
          </div>
        </div>

        <div className="card space-y-4">
          {/* Help accordion — collapsible explanation of what the
              controls below do, including the motif-selection
              algorithm (sum-of -log10(p_adj) score per motif, with
              cross-cluster harmonisation) and the unique-pair
              toggle's semantics. Closed by default; one-time
              orientation rather than something users want to read
              every visit. */}
          <details className="-mx-2 -mt-1 rounded-md bg-slate-50 px-3 py-2 text-xs text-slate-700">
            <summary className="cursor-pointer select-none font-semibold text-slate-800">
              {t('viz.help.title')}
            </summary>
            <div className="mt-2 space-y-2.5 leading-relaxed">
              <p>
                <span className="font-semibold text-teal-700">
                  {t('viz.filter.maxMotifs')}
                </span>{' '}
                — {t('viz.help.maxMotifs')}
              </p>
              <p>
                <span className="font-semibold text-teal-700">
                  {t('viz.filter.padj')}
                </span>{' '}
                — {t('viz.help.padj')}
              </p>
              <p>
                <span className="font-semibold text-teal-700">
                  {t('viz.filter.unique')}
                </span>{' '}
                — {t('viz.help.unique')}
              </p>
              <p className="rounded bg-amber-50 px-2 py-1.5 text-amber-900">
                <span className="font-semibold">{t('viz.help.algo.label')}</span>{' '}
                {t('viz.help.algo.body')}
              </p>
            </div>
          </details>

          <div>
            <label className="block text-sm font-semibold mb-1">{t('viz.filter.unique')}</label>
            <select
              className="w-full border rounded px-3 py-1.5 text-sm"
              value={uniquePairs ? 'TRUE' : 'FALSE'}
              onChange={(e) => {
                setUniquePairs(e.target.value === 'TRUE');
                setTablePage(0);
              }}
            >
              <option value="TRUE">TRUE</option>
              <option value="FALSE">FALSE</option>
            </select>
          </div>

          <div>
            <label className="block text-sm font-semibold mb-1">{t('viz.filter.cluster')}</label>
            <select
              className="w-full border rounded px-3 py-1.5 text-sm"
              value={selectedCluster}
              onChange={(e) => {
                setSelectedCluster(e.target.value);
                setTablePage(0);
              }}
            >
              {clusterOptions.map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-sm font-semibold mb-1">{t('viz.filter.maxMotifs')}</label>
            <input
              type="number"
              className="w-full border rounded px-3 py-1.5 text-sm"
              value={maxMotifs}
              min={3}
              step={1}
              onChange={(e) => {
                const v = parseInt(e.target.value);
                if (v >= 3) {
                  setMaxMotifs(v);
                  setTablePage(0);
                }
              }}
            />
          </div>

          <div>
            <label className="block text-sm font-semibold mb-1">{t('viz.filter.padj')}</label>
            <input
              type="number"
              className="w-full border rounded px-3 py-1.5 text-sm"
              value={pAdj}
              min={0}
              max={1}
              step={0.001}
              onChange={(e) => {
                const v = parseFloat(e.target.value);
                if (v > 0 && v <= 1) {
                  setPAdj(v);
                  setTablePage(0);
                }
              }}
            />
            {pAdjWarning && <p className="text-xs text-red-500 mt-1">{pAdjWarning}</p>}
          </div>
        </div>
      </div>

      {/* Main content with tabs */}
      <div className="flex-1 min-w-0" ref={contentRef}>
        {/* Tabs */}
        <div className="border-b mb-4 flex gap-0">
          {(
            [
              ['heatmap', t('viz.tabs.heatmap')],
              ['motifs', t('viz.tabs.motifs')],
              ['data', t('viz.tabs.data')],
            ] as [ActiveTab, string][]
          ).map(([key, label]) => (
            <button
              key={key}
              onClick={() => setActiveTab(key)}
              className={`px-4 py-2 text-sm font-medium border-b-2 -mb-px transition-colors ${
                activeTab === key ? 'border-teal-600 text-teal-700' : 'border-transparent text-slate-500 hover:text-slate-700'
              }`}
            >
              {label}
            </button>
          ))}
        </div>

        <div key={activeTab} className="tab-panel">
        {/* Heat map tab */}
        {activeTab === 'heatmap' &&
          (() => {
            if (!heatmapData || pAdjWarning) {
              return <div className="text-center py-12 text-slate-500">{pAdjWarning || t('viz.empty.filtered')}</div>;
            }

            const axisBase = {
              constrain: 'domain' as const,
              zeroline: false,
              showline: false,
              showgrid: false,
            };

            const hoverlabelCfg = {
              bgcolor: 'rgba(255,255,255,0.82)',
              bordercolor: 'rgba(15,23,42,0.35)',
              font: { size: 11, color: '#1e293b', family: 'system-ui, sans-serif' },
              align: 'left' as const,
              namelength: -1,
            };

            const renderHeatmap = (
              plotKey: string,
              z: any,
              x: string[],
              y: string[],
              hovertext: any,
              customdata: any,
              colorscale: any,
              title?: string,
              color?: string,
              availWidth?: number,
              zmin?: number,
              zmax?: number
            ) => {
              const n = Math.max(x.length, y.length, 1);
              const s = computeHeatmapSizing(n, [...x, ...y], {
                forDownload: false,
                hideAxes: !showAxes,
                availWidth,
              });

              const axisStyle = showAxes
                ? {
                    xaxis: { ...axisBase, tickangle: 90, tickfont: { size: s.labelFontSize }, side: 'bottom' as const, ticks: 'outside' as const },
                    yaxis: {
                      ...axisBase,
                      tickfont: { size: s.labelFontSize },
                      autorange: 'reversed' as const,
                      scaleanchor: 'x' as const,
                      scaleratio: 1,
                      ticks: 'outside' as const,
                    },
                  }
                : {
                    xaxis: { ...axisBase, showticklabels: false, ticks: '' as const },
                    yaxis: { ...axisBase, showticklabels: false, autorange: 'reversed' as const, scaleanchor: 'x' as const, scaleratio: 1, ticks: '' as const },
                  };

              // Vertical colorbar on the right — fixed position relative to
              // the plot area, decoupled from the panel title (which lives
              // outside the Plotly canvas as a JSX node).
              const colorbarCfg = {
                title: { text: '-log10(p.adj)', side: 'right' as const, font: { size: s.cbFontSize + 1 } },
                orientation: 'v' as const,
                x: 1.02,
                xanchor: 'left' as const,
                y: 0.5,
                yanchor: 'middle' as const,
                len: 1.0,
                thickness: s.cbThickness,
                tickfont: { size: Math.max(8, s.cbFontSize) },
                outlinewidth: 0,
              };

              return (
                <div style={{ width: s.width }}>
                  {title && (
                    <div
                      style={{
                        fontSize: `${s.titleFontSize}px`,
                        fontWeight: 600,
                        color: color || '#334155',
                        padding: '6px 4px 4px',
                        textAlign: 'left',
                        wordBreak: 'break-word',
                        lineHeight: 1.25,
                      }}
                    >
                      {title}
                    </div>
                  )}
                  <div style={{ width: s.width, height: s.height }}>
                    <Plot
                      data={[
                        {
                          z,
                          x,
                          y,
                          type: 'heatmap' as const,
                          colorscale,
                          hovertext,
                          customdata,
                          hoverinfo: 'text',
                          hoverlabel: hoverlabelCfg,
                          showscale: true,
                          colorbar: colorbarCfg,
                          // Apply shared limits when given (R parity: every
                          // per-cluster panel uses the global value range).
                          ...(zmin !== undefined && zmax !== undefined
                            ? { zmin, zmax, zauto: false }
                            : {}),
                        } as any,
                      ]}
                      layout={{
                        autosize: true,
                        ...axisStyle,
                        margin: s.margin,
                        shapes: [
                          {
                            type: 'line',
                            x0: -0.5,
                            y0: -0.5,
                            x1: n - 0.5,
                            y1: n - 0.5,
                            xref: 'x',
                            yref: 'y',
                            line: { color: 'rgba(0,0,0,0.12)', width: 1, dash: 'dot' },
                          },
                        ],
                      }}
                      config={{ responsive: true, displayModeBar: false }}
                      onInitialized={(_fig, gd) => {
                        plotRefs.current.set(plotKey, { gd, title, color });
                      }}
                      onUpdate={(_fig, gd) => {
                        plotRefs.current.set(plotKey, { gd, title, color });
                      }}
                      onClick={(evt: any) => {
                        const pt = evt?.points?.[0];
                        const cd = pt?.customdata;
                        if (!cd) return;
                        setClickedCell({
                          cluster: cd.cluster || title || undefined,
                          motif1: cd.motif1,
                          motif2: cd.motif2,
                          logp: cd.logp,
                          pAdj: cd.pAdj,
                          genes: cd.genes,
                          cellColor: color || '#0f766e',
                        });
                      }}
                      style={{ width: '100%', height: '100%' }}
                    />
                  </div>
                </div>
              );
            };

            const renderOverlapHeatmap = (plotKey: string, data: any, availWidth?: number) => {
              const { x, y, z, hovertext, customdata, colorscale, zmin, zmax, legendItems, intensityMax, intensityFloor } = data;
              const n = Math.max(x.length, y.length, 1);
              const s = computeHeatmapSizing(n, [...x, ...y], {
                forDownload: false,
                hideAxes: !showAxes,
                availWidth,
              });

              const axisStyle = showAxes
                ? {
                    xaxis: { ...axisBase, tickangle: 90, tickfont: { size: s.labelFontSize }, side: 'bottom' as const, ticks: 'outside' as const },
                    yaxis: { ...axisBase, tickfont: { size: s.labelFontSize }, autorange: 'reversed' as const, scaleanchor: 'x' as const, scaleratio: 1, ticks: 'outside' as const },
                  }
                : {
                    xaxis: { ...axisBase, showticklabels: false, ticks: '' as const },
                    yaxis: { ...axisBase, showticklabels: false, autorange: 'reversed' as const, scaleanchor: 'x' as const, scaleratio: 1, ticks: '' as const },
                  };

              // Cluster legend (JSX) — wraps naturally on narrow panels and
              // never collides with the plot. The "Overlapped" black swatch
              // signals cells contributed by 2+ clusters.
              const legendNode = (
                <div
                  style={{
                    display: 'flex',
                    flexWrap: 'wrap',
                    gap: '4px 12px',
                    padding: '6px 4px 4px',
                    fontSize: `${s.labelFontSize + 1}px`,
                    color: '#334155',
                    lineHeight: 1.3,
                  }}
                >
                  {legendItems.map((l: any) => (
                    <span key={l.cluster} style={{ display: 'inline-flex', alignItems: 'center', gap: '4px' }}>
                      <span
                        style={{
                          display: 'inline-block',
                          width: '12px',
                          height: '12px',
                          background: l.color,
                          border: l.color === '#000000' ? 'none' : '1px solid rgba(0,0,0,0.1)',
                        }}
                      />
                      <span>{l.cluster}</span>
                    </span>
                  ))}
                </div>
              );

              // Intensity scale — alpha-equivalent of R's scale_alpha(c(0.3, 1)):
              // weak signal at the floor, strong signal at the cluster's full
              // colour. Render as a CSS gradient using a representative cluster
              // colour so users can read the -log10(p.adj) range every cell
              // shade is mapped against (this is the "min/max" legend that
              // was previously missing for overlap mode).
              const sampleColor = legendItems.find((l: any) => l.color !== '#000000')?.color || '#334155';
              const floorPct = Math.round((intensityFloor || 0.35) * 100);
              const intensityNode = (
                <div style={{ padding: '0 4px 6px', display: 'flex', alignItems: 'center', gap: '8px', fontSize: `${s.labelFontSize}px`, color: '#475569' }}>
                  <span style={{ whiteSpace: 'nowrap' }}>-log10(p.adj)</span>
                  <div
                    style={{
                      flex: '0 1 160px',
                      height: '10px',
                      borderRadius: '2px',
                      background: `linear-gradient(to right, ${sampleColor}${Math.round(floorPct * 2.55).toString(16).padStart(2, '0')}, ${sampleColor})`,
                      border: '1px solid rgba(0,0,0,0.1)',
                    }}
                  />
                  <span style={{ whiteSpace: 'nowrap', fontVariantNumeric: 'tabular-nums' }}>
                    0 — {Number(intensityMax || 0).toFixed(2)}
                  </span>
                </div>
              );

              return (
                <div style={{ width: s.width }}>
                  {legendNode}
                  {intensityNode}
                  <div style={{ width: s.width, height: s.height }}>
                    <Plot
                      data={[
                        {
                          z, x, y,
                          type: 'heatmap' as const,
                          colorscale,
                          zmin, zmax,
                          zauto: false,
                          hovertext,
                          customdata,
                          hoverinfo: 'text',
                          hoverlabel: hoverlabelCfg,
                          showscale: false,
                        } as any,
                      ]}
                      layout={{
                        autosize: true,
                        ...axisStyle,
                        margin: s.margin,
                        shapes: [
                          {
                            type: 'line',
                            x0: -0.5, y0: -0.5, x1: n - 0.5, y1: n - 0.5,
                            xref: 'x', yref: 'y',
                            line: { color: 'rgba(0,0,0,0.12)', width: 1, dash: 'dot' },
                          },
                        ],
                      }}
                      config={{ responsive: true, displayModeBar: false }}
                      onInitialized={(_fig, gd) => { plotRefs.current.set(plotKey, { gd, title: undefined, color: undefined }); }}
                      onUpdate={(_fig, gd) => { plotRefs.current.set(plotKey, { gd, title: undefined, color: undefined }); }}
                      onClick={(evt: any) => {
                        const pt = evt?.points?.[0];
                        const cd = pt?.customdata;
                        if (!cd) return;
                        const accent = cd.isOverlap
                          ? '#000000'
                          : (clusterColorMap[cd.cluster] || '#334155');
                        const overlapEntries = cd.isOverlap && Array.isArray(cd.overlapEntries)
                          ? cd.overlapEntries.map((e: any) => ({
                              cluster: e.cluster,
                              color: clusterColorMap[e.cluster] || '#334155',
                              logp: -Math.log10(Math.max(e.p, 1e-300)),
                              pAdj: e.p,
                              genes: e.genes,
                            }))
                          : undefined;
                        setModalTabIdx(0);
                        setClickedCell({
                          cluster: cd.cluster,
                          motif1: cd.motif1,
                          motif2: cd.motif2,
                          logp: cd.logp,
                          pAdj: cd.pAdj,
                          genes: cd.genes,
                          cellColor: accent,
                          overlapEntries,
                        });
                      }}
                      style={{ width: '100%', height: '100%' }}
                    />
                  </div>
                </div>
              );
            };

            const isMulti = heatmapData.mode === 'all' && 'perCluster' in heatmapData;
            const isOverlap = heatmapData.mode === 'overlap';

            return (
              <div>
                {/* Toolbar */}
                <div className="flex items-center justify-end gap-2 mb-2">
                  <button
                    onClick={() => setShowAxes(!showAxes)}
                    className={`px-3 py-1 text-xs rounded border transition-colors ${
                      showAxes ? 'bg-white text-slate-600 border-slate-300 hover:bg-slate-50' : 'bg-teal-50 text-teal-700 border-teal-300 hover:bg-teal-100'
                    }`}
                    title={showAxes ? t('viz.heat.axes.hide.tip') : t('viz.heat.axes.show.tip')}
                  >
                    {showAxes ? t('viz.heat.axes.hide.label') : t('viz.heat.axes.show.label')}
                  </button>
                  <button
                    onClick={downloadHeatmap}
                    className="px-3 py-1 text-xs rounded border border-teal-600 bg-teal-600 text-white hover:bg-teal-700"
                    title={t('viz.heat.download.tip')}
                  >
                    {t('viz.heat.download.button')}
                  </button>
                </div>

                {(() => {
                  if (isOverlap) {
                    return (
                      <div className="flex justify-center">
                        {renderOverlapHeatmap('main', heatmapData, contentWidth || undefined)}
                      </div>
                    );
                  }
                  if (!isMulti) {
                    // Single-cluster panel: light → dark gradient from R's
                    // per-cluster pair (motif_pair_plot_homog.R).
                    const pair = (heatmapData as any).pair as [string, string] | undefined;
                    const colorscale = pair
                      ? [[0, pair[0]], [1, pair[1]]]
                      : [[0, '#ffffff'], [1, (heatmapData as any).color || '#0f766e']];
                    return (
                      <div className="flex justify-center">
                        {renderHeatmap(
                          'main',
                          (heatmapData as any).z,
                          heatmapData.x!,
                          heatmapData.y!,
                          (heatmapData as any).hovertext,
                          (heatmapData as any).customdata,
                          colorscale,
                          heatmapData.mode === 'single' ? (heatmapData as any).clusterName : undefined,
                          heatmapData.mode === 'single' ? (heatmapData as any).color : undefined
                        )}
                      </div>
                    );
                  }
                  // Adaptive cols: pick the largest cols in [1..3] whose resulting
                  // cellPx is within 70% of natural — otherwise fall back to fewer
                  // cols so cells stay legible.
                  const gridGap = 12;
                  const tiles = heatmapData.perCluster!;
                  const nTiles = tiles.length;
                  const xy = [...heatmapData.x, ...heatmapData.y];
                  const n = Math.max(heatmapData.x.length, heatmapData.y.length, 1);
                  const natural = computeHeatmapSizing(n, xy, { hideAxes: !showAxes });
                  const cellFloor = Math.max(10, Math.ceil(natural.naturalCellPx * 0.7));
                  const maxCols = Math.min(nTiles, 3);
                  const W = contentWidth || 0;
                  let cols = 1;
                  if (W > 0) {
                    for (let c = maxCols; c >= 1; c--) {
                      const per = (W - gridGap * (c - 1)) / c;
                      const probe = computeHeatmapSizing(n, xy, {
                        hideAxes: !showAxes,
                        availWidth: per,
                      });
                      if (c === 1 || probe.cellPx >= cellFloor) {
                        cols = c;
                        break;
                      }
                    }
                  }
                  const perWidth = cols > 0 ? (W - gridGap * (cols - 1)) / cols : natural.width;
                  return (
                    <div
                      className="grid justify-center"
                      style={{
                        gridTemplateColumns: `repeat(${cols}, minmax(0, max-content))`,
                        gap: `${gridGap}px`,
                      }}
                    >
                      {tiles.map((item: any) => {
                        // R parity: light → dark gradient pair per cluster
                        // (motif_pair_plot_homog.R), shared zmin/zmax across
                        // every panel (heatmapData.zmin / heatmapData.zmax).
                        const pair = item.pair as [string, string] | undefined;
                        const colorscale = pair
                          ? [[0, pair[0]], [1, pair[1]]]
                          : [[0, '#ffffff'], [1, item.color]];
                        return (
                          <div key={item.cluster}>
                            {renderHeatmap(
                              `cluster-${item.cluster}`,
                              item.z,
                              heatmapData.x,
                              heatmapData.y,
                              item.hovertext,
                              item.customdata,
                              colorscale,
                              item.cluster,
                              item.color,
                              perWidth,
                              (heatmapData as any).zmin,
                              (heatmapData as any).zmax
                            )}
                          </div>
                        );
                      })}
                    </div>
                  );
                })()}
              </div>
            );
          })()}

        {/* Motifs tab */}
        {activeTab === 'motifs' && (
          <div className="card">
            <div className="flex items-center justify-between mb-4 gap-3 flex-wrap">
              <div>
                <h3 className="font-semibold">{t('viz.motifs.heading')}</h3>
                <p className="text-xs text-slate-500 mt-0.5">{t('viz.motifs.subhead')}</p>
              </div>
              <button
                onClick={downloadMotifsTsv}
                disabled={!motifsByCluster || motifsByCluster.length === 0}
                className="px-3 py-1.5 text-sm border rounded bg-teal-600 text-white hover:bg-teal-700 disabled:opacity-40 whitespace-nowrap"
              >
                {t('viz.motifs.download')}
              </button>
            </div>

            {motifsByCluster && motifsByCluster.length > 0 ? (
              <div className="space-y-4">
                {motifsByCluster.map((c) => (
                  <div key={c.cluster} className="border border-slate-200 rounded-lg overflow-hidden">
                    <div className="flex items-center justify-between px-4 py-2.5 border-b" style={{ backgroundColor: `${c.color}12`, borderLeft: `4px solid ${c.color}` }}>
                      <div className="flex items-baseline gap-3 flex-wrap">
                        <span className="font-semibold text-sm" style={{ color: c.color }}>
                          {c.cluster}
                        </span>
                        <span className="text-xs text-slate-500">
                          {c.all.length} motif{c.all.length === 1 ? '' : 's'}
                          {c.exclusiveCount > 0 && (
                            <span>
                              {' '}
                              · <span className="font-medium text-slate-700">{c.exclusiveCount}</span> {t('viz.motifs.exclusive_suffix')}
                            </span>
                          )}
                        </span>
                      </div>
                      <button onClick={() => copyClusterMotifs(c.all)} className="text-xs text-teal-700 hover:text-teal-800 underline whitespace-nowrap">
                        {t('viz.motifs.copy')}
                      </button>
                    </div>
                    <div className="flex flex-wrap gap-1.5 p-3 bg-white">
                      {c.all.map((m) => {
                        const excl = c.isExclusive(m);
                        return (
                          <span
                            key={m}
                            title={excl ? t('viz.motifs.tip.exclusive') : t('viz.motifs.tip.shared')}
                            className="text-xs font-mono rounded px-2 py-0.5 border"
                            style={
                              excl
                                ? {
                                    color: c.color,
                                    borderColor: `${c.color}55`,
                                    backgroundColor: `${c.color}0d`,
                                    fontWeight: 600,
                                  }
                                : {
                                    color: '#94a3b8',
                                    borderColor: '#e2e8f0',
                                    backgroundColor: '#f8fafc',
                                  }
                            }
                          >
                            {m}
                          </span>
                        );
                      })}
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-slate-500">{t('viz.motifs.empty')}</p>
            )}
          </div>
        )}

        {/* Data viewer tab */}
        {activeTab === 'data' && (
          <div className="card">
            <div className="flex items-center justify-between mb-4 gap-3 flex-wrap">
              <h3 className="font-semibold">{t('viz.data.heading_prefix')} ({tableData.length.toLocaleString()} {t('viz.data.rows_suffix')})</h3>
              <div className="flex items-center gap-3">
                <input
                  type="text"
                  placeholder={t('viz.data.search')}
                  className="border rounded px-3 py-1.5 text-sm w-56"
                  value={searchQuery}
                  onChange={(e) => {
                    setSearchQuery(e.target.value);
                    setTablePage(0);
                  }}
                />
                <button
                  onClick={downloadTsv}
                  disabled={tableData.length === 0}
                  className="px-3 py-1.5 text-sm border rounded bg-teal-600 text-white hover:bg-teal-700 disabled:opacity-40 whitespace-nowrap"
                >
                  {t('viz.data.download')}
                </button>
              </div>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b bg-slate-50">
                    {(
                      [
                        ['cluster', t('viz.data.col.cluster'), 'text-left', t('viz.data.tooltip.cluster')],
                        ['motif1', t('viz.data.col.motif1'), 'text-left', ''],
                        ['motif2', t('viz.data.col.motif2'), 'text-left', ''],
                        ['gene_num', t('viz.data.col.genes'), 'text-right', t('viz.data.tooltip.genes')],
                        ['p_value', t('viz.data.col.pvalue'), 'text-right', t('viz.data.tooltip.pvalue')],
                        ['p_adj_bh', t('viz.data.col.padj_bh'), 'text-right', t('viz.data.tooltip.padj_bh')],
                        ['p_adj_bonf', t('viz.data.col.padj_bonf'), 'text-right', t('viz.data.tooltip.padj_bonf')],
                      ] as [string, string, string, string][]
                    ).map(([col, label, align, tip]) => (
                      <th
                        key={col}
                        title={tip || undefined}
                        className={`${align} py-2 px-3 cursor-pointer select-none hover:text-teal-700 transition-colors whitespace-nowrap`}
                        onClick={() => handleSort(col)}
                      >
                        {label}
                        {sortIcon(col)}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {pageData.map((r, i) => {
                    const clusterColor = clusterColorMap[r.cluster] || '#64748b';
                    return (
                      <tr key={`${tablePage}-${i}`} className="border-b hover:bg-slate-50">
                        <td className="py-2 px-3">
                          <span className="inline-block rounded px-2 py-0.5 text-xs font-medium" style={{ color: clusterColor, backgroundColor: `${clusterColor}14` }}>
                            {r.cluster}
                          </span>
                        </td>
                        <td className="py-2 px-3 font-mono text-xs">{r.motif1}</td>
                        <td className="py-2 px-3 font-mono text-xs">{r.motif2}</td>
                        <td className="py-2 px-3 text-right font-mono text-xs">
                          <span className="font-semibold text-slate-800">{r.gene_num}</span>
                          <span className="text-slate-400">/{r.total_genes}</span>
                        </td>
                        <td className="py-2 px-3 text-right font-mono text-xs">{r.p_value.toExponential(2)}</td>
                        <td className="py-2 px-3 text-right font-mono text-xs">{r.p_adj_bh.toExponential(2)}</td>
                        <td className="py-2 px-3 text-right font-mono text-xs">{r.p_adj_bonf.toExponential(2)}</td>
                      </tr>
                    );
                  })}
                  {pageData.length === 0 && (
                    <tr>
                      <td colSpan={7} className="py-8 text-center text-slate-500">
                        {t('viz.data.empty')}
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
            <div className="flex items-center justify-between mt-4 pt-4 border-t">
              <div className="flex items-center gap-2 text-sm text-slate-500">
                <span>{t('viz.page.show')}</span>
                <select
                  className="border rounded px-2 py-1 text-sm"
                  value={pageSize}
                  onChange={(e) => {
                    setPageSize(Number(e.target.value));
                    setTablePage(0);
                  }}
                >
                  {[5, 10, 20, 50, 100].map((n) => (
                    <option key={n} value={n}>
                      {n}
                    </option>
                  ))}
                </select>
                <span>{t('viz.page.per_page')}</span>
              </div>
              <div className="flex items-center gap-3">
                <button className="px-3 py-1 text-sm border rounded hover:bg-slate-50 disabled:opacity-40" disabled={tablePage === 0} onClick={() => setTablePage(tablePage - 1)}>
                  {t('viz.page.prev')}
                </button>
                <span className="text-sm text-slate-500">
                  {t('viz.page.page_of_prefix')} {tablePage + 1} {t('viz.page.page_of_mid')} {Math.max(tablePages, 1).toLocaleString()}
                </span>
                <button
                  className="px-3 py-1 text-sm border rounded hover:bg-slate-50 disabled:opacity-40"
                  disabled={tablePage >= tablePages - 1}
                  onClick={() => setTablePage(tablePage + 1)}
                >
                  {t('viz.page.next')}
                </button>
              </div>
            </div>
          </div>
        )}
        </div>
      </div>

      {/* Cell detail modal */}
      {clickedCell && (() => {
        const overlap = clickedCell.overlapEntries;
        const hasTabs = overlap && overlap.length > 1;
        const view = hasTabs
          ? overlap![Math.min(modalTabIdx, overlap!.length - 1)]
          : { cluster: clickedCell.cluster || '', color: clickedCell.cellColor,
              logp: clickedCell.logp, pAdj: clickedCell.pAdj, genes: clickedCell.genes };
        const headerAccent = hasTabs ? view.color : clickedCell.cellColor;
        return (
          <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4" onClick={() => setClickedCell(null)}>
            <div className="bg-white rounded-lg shadow-xl max-w-2xl w-full max-h-[85vh] flex flex-col" onClick={(e) => e.stopPropagation()}>
              <div
                className="px-6 py-4 border-b flex items-start justify-between"
                style={{ borderTopLeftRadius: '0.5rem', borderTopRightRadius: '0.5rem', borderTop: `4px solid ${headerAccent}` }}
              >
                <div>
                  {hasTabs ? (
                    <div className="text-xs uppercase tracking-wide text-slate-500 mb-1">
                      {t('viz.modal.overlap_in')}{' '}
                      <span className="font-semibold text-slate-700">{overlap!.length} {t('viz.modal.clusters_suffix')}</span>
                    </div>
                  ) : view.cluster && (
                    <div className="text-xs uppercase tracking-wide text-slate-500 mb-1">
                      {t('viz.modal.cluster_label')}{' '}
                      <span className="font-semibold" style={{ color: view.color }}>
                        {view.cluster}
                      </span>
                    </div>
                  )}
                  <h3 className="font-semibold text-lg font-mono break-all">
                    {clickedCell.motif1} <span className="text-slate-400">×</span> {clickedCell.motif2}
                  </h3>
                </div>
                <button onClick={() => setClickedCell(null)} className="text-slate-400 hover:text-slate-700 text-2xl leading-none ml-4">
                  &times;
                </button>
              </div>

              {hasTabs && (
                <div className="border-b bg-slate-50 px-3 overflow-x-auto">
                  <div className="flex gap-0">
                    {overlap!.map((e, i) => {
                      const active = i === Math.min(modalTabIdx, overlap!.length - 1);
                      return (
                        <button
                          key={e.cluster}
                          onClick={() => setModalTabIdx(i)}
                          className="px-4 py-2 text-sm font-medium border-b-2 -mb-px transition-colors whitespace-nowrap"
                          style={{
                            color: active ? e.color : '#64748b',
                            borderColor: active ? e.color : 'transparent',
                          }}
                        >
                          <span className="inline-block w-2 h-2 rounded-sm mr-2 align-middle" style={{ backgroundColor: e.color }} />
                          {e.cluster}
                        </button>
                      );
                    })}
                  </div>
                </div>
              )}

              <div className="px-6 py-4 overflow-y-auto">
                <div className="grid grid-cols-3 gap-4 mb-5">
                  <div className="bg-slate-50 rounded p-3">
                    <div className="text-xs text-slate-500 mb-1">{t('viz.modal.metric.logp')}</div>
                    <div className="text-xl font-bold text-slate-800">{view.logp.toFixed(3)}</div>
                  </div>
                  <div className="bg-slate-50 rounded p-3">
                    <div className="text-xs text-slate-500 mb-1">{t('viz.modal.metric.padj')}</div>
                    <div className="text-xl font-bold text-slate-800 font-mono">{view.pAdj.toExponential(2)}</div>
                  </div>
                  <div className="bg-slate-50 rounded p-3">
                    <div className="text-xs text-slate-500 mb-1">{t('viz.modal.metric.genes')}</div>
                    <div className="text-xl font-bold text-slate-800">{view.genes.length}</div>
                  </div>
                </div>

                <div>
                  <div className="flex items-center justify-between mb-2">
                    <h4 className="font-semibold text-sm text-slate-700">{t('viz.modal.gene_list')}</h4>
                    <button
                      onClick={() => { navigator.clipboard?.writeText(view.genes.join('\n')); }}
                      className="text-xs text-teal-700 hover:text-teal-800 underline"
                    >
                      {t('viz.modal.copy')}
                    </button>
                  </div>
                  <div className="flex flex-wrap gap-1.5 bg-slate-50 rounded p-3 max-h-64 overflow-y-auto">
                    {view.genes.map((g) => (
                      <span key={g} className="text-xs font-mono bg-white border border-slate-200 rounded px-2 py-0.5 text-slate-700">
                        {g}
                      </span>
                    ))}
                  </div>
                </div>
              </div>

              <div className="px-6 py-3 border-t bg-slate-50 flex justify-end rounded-b-lg">
                <button onClick={() => setClickedCell(null)} className="px-4 py-1.5 text-sm border rounded bg-white hover:bg-slate-100">
                  {t('viz.modal.close')}
                </button>
              </div>
            </div>
          </div>
        );
      })()}
    </div>
  );
}

// Suspense wrapper required because VisualizePageContent calls
// useSearchParams() to read the optional ?task=<id> source. Without the
// boundary Next.js refuses to prerender the page statically.
function VisualizeFallback() {
  const { t } = useTranslation();
  return (
    <div className="max-w-5xl mx-auto py-8 text-slate-500">
      {t('quicklook.loading')}
    </div>
  );
}

export default function VisualizePage() {
  return (
    <Suspense fallback={<VisualizeFallback />}>
      <VisualizePageContent />
    </Suspense>
  );
}
