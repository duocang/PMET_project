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

export const EXAMPLE_GENE_LIST = `epidermis\tAT1G05650
epidermis\tAT3G21620
epidermis\tAT5G15510
epidermis\tAT5G45840
cortex\tAT1G16630
cortex\tAT3G27490
cortex\tAT5G03040
pericycle\tAT4G11050
pericycle\tAT5G19880
…
`;

export interface FileExample {
  title: string;
  content: string;
  /** A one-sentence hint about the format, shown above the snippet. */
  note?: string;
}
