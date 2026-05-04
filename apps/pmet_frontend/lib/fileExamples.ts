// Hand-crafted preview snippets for the four upload fields on the
// 完整启动子流程 (promoters) submit form. Real demo files live under
// data/demos/ and can run into hundreds of MB; these snippets stay
// representative-but-bounded so they fill the side drawer without
// scrolling 100 MB through the user's browser. Lines are pulled from
// the actual demo files so the preview matches what "Use example"
// loads. If real-file fetching is later required, swap the constants
// for fetched-and-trimmed `${demoUrl}?head=N` payloads.

export const EXAMPLE_FASTA = `>1 dna_sm:chromosome chromosome:TAIR10:1:1:30427671:1 REF
ccctaaaccctaaaccctaaaccctaaacctctgaatccttaatccctaaatccctaaat
ctttaaatcctacatccatgaatccctaaatacctaattccctaaacccgaaaccGGTTT
CTCTGGTTGAAAATCATTGTGTATATAATGATAATTTTATCGTTTTTATGTAATTGCTTA
TTGTTGTGTGTAGATTTTTTAAAAATATCATTTGAGGTCAATACAAATCCTATTTCTTGT
GGTTTTCTTTCCTTCACTTAGCTATGGATGGTTTATCTTCATTTGTTATATTGGATACAA
GCTTTGCTACGATCTACATTTGGGAATGTGAGTCTCTTATTGTAACCTTAGGGTTGGTTT
ATCTCAAGAATCTTATTAATTGTTTGGACTGTTTATGTTTGGACATTTATTGTCATTCTT
ACTCCTTTGTGGAAATGTTTGTTCTATCAATTTATCTTTTGTGGGAAAATTATTTAGTTG
TAGGGATGAAGTCTTTCTTCGTTGTTGTTACGCTTGTCATCTCATCTCTCAATGATATGG
GATGGTCCTTTAGCATTTATTCTGAAGTTCTTCTGCTTGATGATTTTATCCTTAGCCAAA
AGGATTGGTGGTTTGAAGACACATCATATCAAAAAAGCTATCGCCTCGACGATGCTCTAT
TTCTATCCTTGTAGCACACATTTTGGCACTCAAAAAAGTATTTTTAGATGTTTGTTTTGC
TTCTTTGAAGTAGTTTCTCTTTGCAAAATTCCTCtttttttAGAGTGATTTGGATGATTC
AAGACTTCTCGGTACTGCAAAGTTCTTCCGCCTGATTAATTATCCATTTTACCTTTGTCG
TAGATATTAGGTAATCTGTAAGTCAACTCATATACAACTCATAATTTAAAATAAAATTAT
GATCGACACACGTTTACACATAAAATCTGTAAATCAACTCATATACCCGTTATTCCCACA
ATCATATGCTTTCTAAAAGCAAAAGTATATGTCAACAATTGGTTATAAATTATTAGAAGT
TTTCCACTTATGACTTAAGAACTTGTGAAGCAGAAAGTGGCAACAccccccacctccccc
ccccccccccaccccccAAATTGAGAAGTCAATTTTATATAATTTAATCAAATAAATAAG
>2 dna_sm:chromosome chromosome:TAIR10:2:1:19698289:1 REF
NNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNN
NNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNN
…
`;

export const EXAMPLE_GFF3 = `##gff-version 3
##sequence-region   1 1 30427671
##sequence-region   2 1 19698289
##sequence-region   3 1 23459830
##sequence-region   4 1 18585056
##sequence-region   5 1 26975502
##sequence-region   Mt 1 366924
##sequence-region   Pt 1 154478
#!genome-build The Arabidopsis Information Resource TAIR10
#!genome-version TAIR10
#!genome-date 2008-04
#!genome-build-accession GCA_000001735.1
#!genebuild-last-updated 2010-09
1\tTAIR10\tchromosome\t1\t30427671\t.\t.\t.\tID=chromosome:1;Alias=Chr1,CP002684.1,NC_003070.9
###
1\taraport11\tgene\t3631\t5899\t.\t+\t.\tID=gene:AT1G01010;Name=NAC001;biotype=protein_coding;description=NAC domain-containing protein 1 [Source:UniProtKB/Swiss-Prot%3BAcc:Q0WV96];gene_id=AT1G01010;logic_name=araport11
1\taraport11\tmRNA\t3631\t5899\t.\t+\t.\tID=transcript:AT1G01010.1;Parent=gene:AT1G01010;biotype=protein_coding;transcript_id=AT1G01010.1
1\taraport11\tfive_prime_UTR\t3631\t3759\t.\t+\t.\tParent=transcript:AT1G01010.1
1\taraport11\texon\t3631\t3913\t.\t+\t.\tParent=transcript:AT1G01010.1;Name=AT1G01010.1.exon1;constitutive=1;ensembl_end_phase=1;ensembl_phase=-1;exon_id=AT1G01010.1.exon1;rank=1
1\taraport11\tCDS\t3760\t3913\t.\t+\t0\tID=CDS:AT1G01010.1;Parent=transcript:AT1G01010.1;protein_id=AT1G01010.1
1\taraport11\texon\t3996\t4276\t.\t+\t.\tParent=transcript:AT1G01010.1;Name=AT1G01010.1.exon2;constitutive=1;ensembl_end_phase=0;ensembl_phase=1;exon_id=AT1G01010.1.exon2;rank=2
1\taraport11\tCDS\t3996\t4276\t.\t+\t2\tID=CDS:AT1G01010.1;Parent=transcript:AT1G01010.1;protein_id=AT1G01010.1
1\taraport11\texon\t4486\t4605\t.\t+\t.\tParent=transcript:AT1G01010.1;Name=AT1G01010.1.exon3;constitutive=1;ensembl_end_phase=0;ensembl_phase=0;exon_id=AT1G01010.1.exon3;rank=3
1\taraport11\tCDS\t4486\t4605\t.\t+\t0\tID=CDS:AT1G01010.1;Parent=transcript:AT1G01010.1;protein_id=AT1G01010.1
1\taraport11\texon\t4706\t5095\t.\t+\t.\tParent=transcript:AT1G01010.1;Name=AT1G01010.1.exon4;constitutive=1;ensembl_end_phase=0;ensembl_phase=0;exon_id=AT1G01010.1.exon4;rank=4
1\taraport11\tCDS\t4706\t5095\t.\t+\t0\tID=CDS:AT1G01010.1;Parent=transcript:AT1G01010.1;protein_id=AT1G01010.1
1\taraport11\texon\t5174\t5326\t.\t+\t.\tParent=transcript:AT1G01010.1;Name=AT1G01010.1.exon5;constitutive=1;ensembl_end_phase=2;ensembl_phase=0;exon_id=AT1G01010.1.exon5;rank=5
1\taraport11\tCDS\t5174\t5326\t.\t+\t0\tID=CDS:AT1G01010.1;Parent=transcript:AT1G01010.1;protein_id=AT1G01010.1
1\taraport11\texon\t5439\t5899\t.\t+\t.\tParent=transcript:AT1G01010.1;Name=AT1G01010.1.exon6;constitutive=1;ensembl_end_phase=-1;ensembl_phase=2;exon_id=AT1G01010.1.exon6;rank=6
1\taraport11\tCDS\t5439\t5630\t.\t+\t1\tID=CDS:AT1G01010.1;Parent=transcript:AT1G01010.1;protein_id=AT1G01010.1
1\taraport11\tthree_prime_UTR\t5631\t5899\t.\t+\t.\tParent=transcript:AT1G01010.1
…
`;

export const EXAMPLE_MEME = `MEME version 5.4.1

ALPHABET= ACGT

strands: + -

Background letter frequencies (from uniform background):
A 0.25000 C 0.25000 G 0.25000 T 0.25000

MOTIF MYB52 MYB52

letter-probability matrix: alength= 4 w= 8 nsites= 20 E= 0
  0.493200\t  0.300600\t  0.147100\t  0.059100
  0.237500\t  0.519800\t  0.102500\t  0.140200
  0.103890\t  0.106689\t  0.035196\t  0.754225
  0.924900\t  0.013400\t  0.031800\t  0.029900
  0.865913\t  0.096990\t  0.013899\t  0.023198
  0.016900\t  0.923700\t  0.031200\t  0.028200
  0.089100\t  0.053000\t  0.788800\t  0.069100
  0.129400\t  0.022500\t  0.787800\t  0.060300

URL https://pubmed.ncbi.nlm.nih.gov/24477691/

MOTIF WRKY40 WRKY40

letter-probability matrix: alength= 4 w= 7 nsites= 20 E= 0
  0.084100\t  0.041800\t  0.087500\t  0.786600
  0.027200\t  0.039700\t  0.025900\t  0.907200
  0.018400\t  0.014600\t  0.957300\t  0.009700
  0.022300\t  0.018700\t  0.013200\t  0.945800
  0.872400\t  0.024700\t  0.069200\t  0.033700
  0.069100\t  0.781200\t  0.058300\t  0.091400
  0.038600\t  0.043200\t  0.872900\t  0.045300

URL https://pubmed.ncbi.nlm.nih.gov/24477691/
…
`;

// Sample drawn from data/genes/genes_cell_type_treatment.txt — the
// same file the "Use example" button actually downloads. Matching the
// real fixture (rather than a synthetic one) keeps the preview honest:
// users see the same cluster naming, the same delimiter, and the same
// shape they're going to load.
export const EXAMPLE_GENE_LIST = `Epidermis_flg22_up AT1G53080
Epidermis_flg22_up AT5G24550
Epidermis_flg22_up AT4G23550
Epidermis_flg22_up AT3G16530
Epidermis_flg22_up AT1G57630
Epidermis_flg22_up AT4G33020
Epidermis_flg22_up AT1G78460
Epidermis_flg22_up AT5G22910
Cortex_flg22_up AT1G02450
Cortex_flg22_up AT1G05660
Cortex_flg22_up AT2G14610
Cortex_flg22_up AT3G46280
Cortex_flg22_up AT5G24530
Cortex_flg22_up AT4G11890
Epidermis_pep1_up AT1G01180
Epidermis_pep1_up AT1G02340
Epidermis_pep1_up AT1G07135
Epidermis_pep1_up AT2G44490
Cortex_pep1_up AT2G41280
Cortex_pep1_up AT4G02100
Cortex_pep1_up AT3G15530
Cortex_pep1_up AT5G55180
Epidermis_pep1_do AT1G01780
Epidermis_pep1_do AT2G37950
Cortex_pep1_do AT4G34680
Cortex_pep1_do AT3G17600
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
U\t1:40877-42017(-)
U\t1:46789-47234(-)
U\t1:49166-49909(-)
U\t1:50954-51953(-)
U\t1:51210-52239(+)
U\t1:58978-60215(-)
U\t1:63811-64166(-)
U\t1:67512-68774(-)
U\t1:71998-72339(-)
U\t1:72138-72583(+)
U\t1:74443-75390(-)
U\t1:74737-75633(+)
U\t1:78103-79004(-)
U\t1:81654-82515(+)
U\t1:84145-85090(-)
U\t1:87122-88003(+)
U\t1:90244-91317(-)
U\t1:93455-94401(+)
…
`;

export interface FileExample {
  title: string;
  content: string;
  /** A one-sentence hint about the format, shown above the snippet. */
  note?: string;
}
