# PMET glossary

**[English](#en) · [汉文](#cn)**

A one-screen reference for the domain words PMET throws around. If you're an experienced bioinformatician, skim once and skip; if you're not, this saves you ten minutes of googling per term.

---

<a id="en"></a>

## Glossary (English)

### Motif vs hit

- **Motif** — a short DNA pattern (typically 6–20 bp) that a transcription factor recognises and binds. Represented as a position-weight matrix (PWM) in MEME format.
- **Hit** — a specific genomic position where a motif's PWM scores above some threshold. One motif has many hits across a genome; PMET keeps the top `n` hits per motif (genome-wide) and at most `k` hits per gene.

### MEME / FIMO

- **MEME** — both a file format for motif libraries (PWMs + metadata) and the suite of motif-discovery tools that produce them. PMET consumes MEME-format files; it does not discover motifs.
- **FIMO** — "Find Individual Motif Occurrences", part of the MEME suite. Given a motif and a sequence, it scores every position and returns hits above a p-value threshold. PMET wraps FIMO for the indexing stage.

### Indexing vs pairing (homotypic vs heterotypic)

- **Indexing / homotypic search** — for each motif, scan a chosen region (promoters / UTRs / CDS / arbitrary intervals) and record which genes contain at least one good hit. Output: an "index" of motif → gene set. Reusable across many gene lists.
- **Pairing / heterotypic search** — given a target gene list and the index above, ask for every pair of motifs `(m₁, m₂)` whether they co-occur (both hit the same promoter) more often in the target list than in the genome-wide background. The pair test is hypergeometric.

### Cluster vs target gene set vs background (universe)

- **Cluster** — a labelled subset of genes you care about (e.g. the cortex marker genes from a single-cell experiment). Multiple clusters can share one indexing run. The gene list file uses `cluster<TAB>gene_id` per line.
- **Target gene set** — same thing as cluster, just the more general term. Each PMET row is computed for one (cluster, motif pair).
- **Background / universe** — every gene the indexer scanned. PMET measures co-occurrence rate in the cluster against this background; you don't pass it explicitly — it's whatever the index covers.

### IC threshold

- **IC** — information content of a motif's PWM, measured in bits. Roughly: how distinctive is the motif sequence relative to a uniform 25 % A/C/G/T background. Low IC = the motif is mostly N's, hits are scattered everywhere, pair tests against it are noise.
- **IC threshold** — pass `-c <X>` to the pairing stage to drop any motif with `IC < X` from the test universe. Default 4.0; PMET paper reports robust pairs at IC ≥ 4.

### p-value family

- **raw p** — hypergeometric p-value for one (cluster, motif pair), uncorrected.
- **adj_p_BH** — Benjamini-Hochberg FDR-corrected p, adjusted across every pair tested *within the same cluster*. **This is the column to filter on**; treat `adj_p_BH < 0.05` as significant.
- **adj_p_Bonf** — per-cluster Bonferroni correction. Stricter than BH; near 1.0 for almost everything.
- **adj_p_global** — Bonferroni across *every (cluster, pair)* row in the file. Stricter still; useful only when you want one globally-comparable rank.

### Other terms

- **Promoter** — for PMET defaults, the 1 kb upstream of a gene's transcription start site (TSS), optionally including the 5'UTR. Configurable via `promoter.sh -p <bp>` and `-u Yes|No`.
- **TSS** — transcription start site, the first base FANTOM-style pipelines and PMET extract upstream of.
- **Co-occurrence** — both motifs of a pair have ≥1 hit in the same promoter (PMET doesn't care about the relative distance between them, just same-promoter presence).

---

<a id="cn"></a>

## 词典（汉文）

### Motif vs hit

- **Motif** —— 一段短 DNA 模式（一般 6–20 bp），转录因子识别并结合的就是它。在 MEME 格式里用 position-weight matrix (PWM) 表示。
- **Hit** —— motif 的 PWM 在基因组某个具体位置评分超过阈值的那一次命中。一个 motif 在基因组上会有很多 hit；PMET 全基因组保留前 `n` 个，每个基因最多 `k` 个。

### MEME / FIMO

- **MEME** —— 既是 motif 库的文件格式（PWM + 元数据），也是产出这种格式的 motif 发现工具套件。PMET 只消费 MEME 文件，**不**做 motif 发现。
- **FIMO** —— "Find Individual Motif Occurrences"，MEME 套件的一员。给一个 motif 和一段序列，逐位置评分，返回 p-value 阈值以上的命中。PMET 在 indexing 阶段调它。

### Indexing vs pairing（同型 vs 异型）

- **Indexing / 同型搜索** —— 对每个 motif，扫描指定区域（启动子 / UTR / CDS / 任意区间），记录哪些基因里至少有一个好 hit。产出： motif → 基因集合的"索引"。可在多个基因列表间复用。
- **Pairing / 异型搜索** —— 拿到目标基因列表和上面的索引，对每一对 motif `(m₁, m₂)` 问：它们在同一启动子里共现的频率，目标列表里是不是显著高于全基因组背景？检验用超几何。

### Cluster vs target gene set vs 背景（universe）

- **Cluster** —— 你关心的、带标签的一组基因（例如从单细胞实验里挑出来的 cortex marker 基因）。多个 cluster 可以共用一次 indexing。基因列表文件每行 `cluster<TAB>gene_id`。
- **Target gene set** —— 跟 cluster 是一回事，只是更一般的称呼。 PMET 的每一行结果都是针对一个 (cluster, motif 对)。
- **背景 / universe** —— indexer 扫到的每一个基因。PMET 测的是 cluster 内共现率 vs 这个背景；你不用显式传它 —— 索引覆盖到的范围就是它。

### IC 阈值

- **IC** —— motif PWM 的信息量（information content），单位 bit。粗略说：motif 序列相对均匀 25 % A/C/G/T 背景的"特异程度"。低 IC = motif 几乎全是 N，到处都有 hit，对它做 pair 检验全是噪声。
- **IC 阈值** —— 在 pairing 阶段传 `-c <X>`，把 `IC < X` 的 motif 从测试 universe 里剔掉。默认 4.0；PMET 论文报告 IC ≥ 4 出来的 pair 比较稳。

### p-value 族

- **raw p** —— 单个 (cluster, motif 对) 的超几何 p，未校正。
- **adj_p_BH** —— Benjamini-Hochberg FDR 校正后的 p，校正范围是** 同一 cluster 内**的所有 pair。**这是你要过滤的列**， `adj_p_BH < 0.05` 视为显著。
- **adj_p_Bonf** —— per-cluster Bonferroni 校正。比 BH 严，绝大多数都贴近 1.0。
- **adj_p_global** —— 在文件里**所有 (cluster, pair)** 行上做 Bonferroni。最严，仅在想要一个全局可比的排名时才用。

### 其它

- **启动子** —— PMET 默认指基因 TSS 上游 1 kb（可选含 5'UTR）。通过 `promoter.sh -p <bp>` 与 `-u Yes|No` 调。
- **TSS** —— transcription start site，转录起始位点。FANTOM 风格 pipeline 和 PMET 都从它上游抽序列。
- **Co-occurrence / 共现** —— 同一启动子里这对 motif 都有 ≥1 个 hit（PMET 不关心两者距离，只看是否同启动子）。
