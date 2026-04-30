#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "FileRead.h"
#include "MemCheck.h"

int main() {
    char* content;
    long lines = readFileAndCountLines("data/test_data/MYB46_2_short.txt", &content);
    printf("Number of lines: %ld\n", lines);
    printf("Content:\n%s", content);

    // 使用sscanf进行解析
    char* line = strtok(content, "\n");  // 忽略标题行
    char motif[100], motifAlt[100], geneID[100], strand[2], matched_sequence[100];
    int start, stop;
    double score, pval, qval;

    while ((line = strtok(NULL, "\n")) != NULL) {
        sscanf(line, "%s\t%s\t%s\t%d\t%d\t%s\t%lf\t%lf\t%lf\t%s",
                motif, motifAlt, geneID, &start, &stop, strand, &score, &pval, &qval, matched_sequence);
        printf("Motif: %s, MotifAlt: %s, GeneID: %s, Start: %d, Stop: %d, Strand: %s, Score: %lf, PVal: %lf, QVal: %lf, Matched_sequence: %s\n",
                motif, motifAlt, geneID, start, stop, strand, score, pval, qval, matched_sequence);
    }

    // Free the allocated memory.
    free(content);

    return 0;
}

// clang -DDEBUG -o test TestFileRead.c FileRead.c MemCheck.c
