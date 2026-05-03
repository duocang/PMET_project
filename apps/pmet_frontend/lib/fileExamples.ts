// Hand-crafted preview snippets for the four upload fields on the
// 完整启动子流程 (promoters) submit form. Real demo files live under
// data/demos/ and can run into hundreds of MB; these snippets stay small
// and readable so a user previewing the format can grasp the shape at a
// glance. If real-file fetching is later required, swap the constants for
// fetched-and-trimmed `${demoUrl}?head=20` payloads.

export const EXAMPLE_FASTA = `>AT1G01010
TATTGCTATTTCTGCCAATATTAAAACTTCACTTAGGAAGACTTGAACCTACCACACGTT
AGTGACTAATGAGAGCCACTAGATAATTGCATGCATCCCACACTAGTACTAATTTTCTAG
GGATATTAGAGTTTTCTAATCACCTACTTCCTACTATGTGTATGTTATCTACTGGCGTGG
ATGCTTTTAAAGATGTTACGTTATTATTTTGTTCGGTTTGGAAAACGGCTCAATCGTTAT
>AT1G01020
AGATAAATATATGAACCTACATCATTATAAGTAGGGTTAAGTGTGTATGATTGTGTATGC
GTATAAAAATACTCCCTTGACCGTAAACATGAAACATGTAATATATAAGATATATAGACA
TGGAGACTATATCATATAAACATACATATATATATATATGTTAGTTATATGTGTAGCCCA
>AT1G01030
TTGAACAAACAGACACGTATTGATTATAGTATTTCTGCTATTGATAAGTTTTTAAACAAA
ATTTAGTGTGCAATAGCACGCACGATTAAGTGAATCAATACACATAATTTACACCGTTTG
…
`;

export const EXAMPLE_GFF3 = `##gff-version 3
##sequence-region   1 1 30427671
1\tAraport11\tgene\t3631\t5899\t.\t+\t.\tID=gene:AT1G01010;Name=NAC001;biotype=protein_coding
1\tAraport11\tmRNA\t3631\t5899\t.\t+\t.\tID=transcript:AT1G01010.1;Parent=gene:AT1G01010;biotype=protein_coding
1\tAraport11\tfive_prime_UTR\t3631\t3759\t.\t+\t.\tParent=transcript:AT1G01010.1
1\tAraport11\texon\t3631\t3913\t.\t+\t.\tParent=transcript:AT1G01010.1
1\tAraport11\tCDS\t3760\t3913\t.\t+\t0\tID=CDS:AT1G01010.1;Parent=transcript:AT1G01010.1
1\tAraport11\texon\t3996\t4276\t.\t+\t.\tParent=transcript:AT1G01010.1
1\tAraport11\tCDS\t3996\t4276\t.\t+\t2\tID=CDS:AT1G01010.1;Parent=transcript:AT1G01010.1
…
`;

export const EXAMPLE_MEME = `MEME version 4.4

ALPHABET= ACGT
strands: + -

Background letter frequencies
A 0.30000 C 0.20000 G 0.20000 T 0.30000

MOTIF ABI3VP1_tnt.AT5G18090

letter-probability matrix: alength= 4 w= 15 nsites= 147 E= 2.1e-117
  0.244898  0.163265  0.401361  0.190476
  0.414966  0.149660  0.238095  0.197279
  0.312925  0.176871  0.129252  0.380952
  0.000000  0.000000  1.000000  0.000000
  1.000000  0.000000  0.000000  0.000000
  0.000000  0.000000  0.000000  1.000000
…
`;

// Sample drawn from data/genes/genes_cell_type_treatment.txt — the
// same file the "Use example" button actually downloads. Matching the
// real fixture (rather than a synthetic one) keeps the preview honest:
// users see the same cluster naming, the same delimiter, and the same
// shape they're going to load. Two lines per cluster so the 6-cluster
// structure of the real file is visible in the preview.
export const EXAMPLE_GENE_LIST = `Epidermis_flg22_up AT1G53080
Epidermis_flg22_up AT5G24550
Cortex_flg22_up AT1G02450
Cortex_flg22_up AT1G05660
Epidermis_pep1_up AT1G01180
Epidermis_pep1_up AT1G02340
Cortex_pep1_up AT2G41280
Cortex_pep1_up AT4G02100
Epidermis_pep1_do AT1G01780
Cortex_pep1_do AT4G34680
…
`;

// Same two-column shape as the gene list, but the second column is a
// genomic interval name (chr:start-end(strand)) rather than a gene ID.
// Drawn from data/demos/intervals/indexing/peaks.txt so users see the
// exact form the indexing pipeline expects.
export const EXAMPLE_PEAK_LIST = `U\t1:2631-3760(+)
U\t1:8666-10130(-)
U\t1:12940-14714(-)
U\t1:22121-23519(+)
U\t1:32670-33365(-)
U\t1:37061-38444(-)
…
`;

export interface FileExample {
  title: string;
  content: string;
  /** A one-sentence hint about the format, shown above the snippet. */
  note?: string;
}
