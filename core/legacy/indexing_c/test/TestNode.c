#include <stdio.h>

#include "MotifHit.h"
#include "MotifHitVector.h"
#include "Node.h"

void testInitNodeStore1()
{
  // Scenario 1: Normal initialization of a NodeStore
  NodeStore *store = malloc(sizeof(NodeStore));
  if (!store)
  {
    fprintf(stderr, "Error: Memory allocation failed for NodeStore in testInitNodeStore.\n");
    exit(1);
  }
  initNodeStore(store);

  assert(store->head == NULL);
  free(store);

  // Scenario 2: Pass a NULL NodeStore to initNodeStore
  // This should print an error message but not crash.
  initNodeStore(NULL);

  printf("All tests passed for initNodeStore!\n");
}

void testFindNodeInStore()
{
  printf("Testing findNodeInStore...\n");
  NodeStore store;
  initNodeStore(&store);

  // Create a node dynamically
  Node *testNode = malloc(sizeof(Node));
  testNode->key = strdup("sampleKey"); // Use dynamic allocation for the key
  testNode->value = NULL;              // for simplicity
  testNode->next = NULL;
  store.head = testNode;

  // Test 1: Normal scenario
  Node *result = findNodeInStore(&store, "sampleKey");
  assert(result == testNode);
  printf("Test 1 Passed!\n");

  // Test 2: Key not present in store
  result = findNodeInStore(&store, "missingKey");
  assert(result == NULL);
  printf("Test 2 Passed!\n");

  // Test 3: Pass NULL as store
  result = findNodeInStore(NULL, "sampleKey");
  assert(result == NULL);
  printf("Test 3 Passed!\n");

  // Test 4: Pass NULL as key
  result = findNodeInStore(&store, NULL);
  assert(result == NULL);
  printf("Test 4 Passed!\n");

  // Clean up dynamically allocated memory
  free(testNode->key); // Free the key
  free(testNode);      // Free the testNode itself
  printf("Memory freed successfully.\n");
}

void testInitNodeStore()
{
  printf("Testing initNodeStore...\n");
  // Test 1: Normal scenario
  NodeStore store;
  initNodeStore(&store);
  assert(store.head == NULL);
  printf("Test 1 Passed!\n");

  // Test 2: Pass a NULL pointer. This should print an error but not crash the program.
  initNodeStore(NULL);
  printf("Test 2 Passed!\n");

  freeNodeStore(&store);
  printf("Memory freed successfully.\n");
}

void test_insertIntoNodeStore1()
{
  printf("Testing insertIntoNodeStore...\n");
  // Initialize a NodeStore
  NodeStore store;
  initNodeStore(&store);
}

void test_insertIntoNodeStore2()
{
  printf("Testing insertIntoNodeStore...\n");
  // Initialize a NodeStore
  NodeStore store;
  initNodeStore(&store);

  // Sample MotifHits to be inserted
  MotifHit hit1 = {.sequence_name = "SEQUENCE_1",
                   .motif_alt_id = "SEQUENCE_1",
                   .motif_id = "SEQUENCE_1",
                   .sequence = "SEQUENCE_1"};
  MotifHit hit2 = {.sequence_name = "SEQUENCE_2",
                   .motif_alt_id = "SEQUENCE_2",
                   .motif_id = "SEQUENCE_2",
                   .sequence = "SEQUENCE_2"};
  MotifHit hit3 = {.sequence_name = "SEQUENCE_1",
                   .motif_alt_id = "SEQUENCE_1",
                   .motif_id = "fasd",
                   .sequence = "SEQUENCE_1"}; // Intentionally using SEQUENCE_1 again

  // // Insert into NodeStore
  insertIntoNodeStore(&store, &hit1);
  insertIntoNodeStore(&store, &hit2);
  insertIntoNodeStore(&store, &hit3);

  // For this test, we'll simply check the counts (this could be more thorough)
  assert(countNodesInStore(&store) == 2);        // Should have two distinct nodes
  assert(countAllMotifHitsInStore(&store) == 3); // Total 3 hits across all nodes
  printf("Memory freed successfully.\n");
}

// void testAreNodeStoresEqual() {
//   printf("\nTesting areNodeStoresEqual...\n");
//     // 1. Initialize hits
//     MotifHit hit1, hit2, hit3, hit4;
//     initMotifHit(&hit1, "AHL12", "孙悟空", "AT1G01020", 614, 621, '+', 7.85401, 0.000559, "AAATAATT", 0);
//     initMotifHit(&hit2, "AHL15", "唐三藏", "AT1G01021", 700, 708, '-', 8.5001, 0.000600, "AAGGTTAA", 1);
//     initMotifHit(&hit3, "AHL18", "猪八戒", "AT1G01022", 800, 808, '+', 6.7000, 0.000700, "TTAACCAA", 2);
//     initMotifHit(&hit4, "AHL20", "沙僧", "AT1G01020", 650, 658, '-', 7.1000, 0.000800, "GGGTTTCC", 3);

//     // 2. Initialize NodeStores
//     NodeStore *store1, *store2, *store3;
//     initNodeStore(store1);
//     initNodeStore(store2);
//     initNodeStore(store3);

//     insertIntoNodeStore(store1, &hit1);
//     insertIntoNodeStore(store1, &hit2);
//     insertIntoNodeStore(store2, &hit3);
//     insertIntoNodeStore(store2, &hit4);
//     // copyNodeStore(store3, store1);

//     // 3. Perform tests
//     assert(!areNodeStoresEqual(store1, store2));  // Expect false since store1 and store2 are different
//     assert(areNodeStoresEqual(store1, store3));   // Expect true since store3 is a copy of store1

//     // 4. Cleanup (ensure you also have a function to cleanup NodeStores and their content)
//     freeNodeStore(store1);
//     freeNodeStore(store2);
//     freeNodeStore(store3);

//     printf("All tests for areNodeStoresEqual passed!\n");
// }

void testMultipleMotifs(NodeStore *stores)
{
  NodeStore store1 = stores[0];
  initNodeStore(&store1);

  MotifHit hit1, hit2, hit3, hit4;
  initMotifHit(&hit1, "AHL12", "孙悟空", "AT1G01020", 614, 621, '+', 7.85401, 0.000559, "AAATAATT", 0);
  initMotifHit(&hit2, "AHL12", "唐三藏", "AT1G01021", 700, 708, '-', 8.5001, 0.000600, "AAGGTTAA", 1);
  initMotifHit(&hit3, "AHL12", "猪八戒", "AT1G01022", 800, 808, '+', 6.7000, 0.000700, "TTAACCAA", 2);
  initMotifHit(&hit4, "AHL12", "沙和尚", "AT1G01020", 650, 658, '-', 7.1000, 0.000800, "GGGTTTCC", 3);

  // Add the test data to the store
  insertIntoNodeStore(&store1, &hit1);
  insertIntoNodeStore(&store1, &hit2);
  insertIntoNodeStore(&store1, &hit3);
  insertIntoNodeStore(&store1, &hit4);

  printf("Seond NodeStore:\n\n");
  NodeStore store2 = stores[1];
  initNodeStore(&store2);
  initMotifHit(&hit1, "AHL15", "孙悟空1", "AT1G01020", 614, 621, '+', 7.85401, 0.000559, "AAATAATT", 0);
  initMotifHit(&hit2, "AHL15", "唐三藏1", "AT1G01021", 700, 708, '-', 8.5001, 0.000600, "AAGGTTAA", 1);
  initMotifHit(&hit3, "AHL15", "猪八戒1", "AT1G01022", 800, 808, '+', 6.7000, 0.000700, "TTAACCAA", 2);
  initMotifHit(&hit4, "AHL15", "沙和尚1", "AT1G01020", 650, 658, '-', 7.1000, 0.000800, "GGGTTTCC", 3);

  // Add the test data to the store
  insertIntoNodeStore(&store2, &hit1);
  insertIntoNodeStore(&store2, &hit2);
  insertIntoNodeStore(&store2, &hit3);
  insertIntoNodeStore(&store2, &hit4);

  printNodeStore(&store1);
  printNodeStore(&store2);
}

int main()
{
  // testInitNodeStore1();
  // testInitNodeStore();
  // testFindNodeInStore();
  // test_insertIntoNodeStore2();

  // NodeStore store;
  // initNodeStore(&store);

  // MotifHit hit1, hit2, hit3, hit4;
  // initMotifHit(&hit1, "AHL12", "孙悟空", "AT1G01020", 614, 621, '+', 7.85401, 0.000559, "AAATAATT", 0);
  // initMotifHit(&hit2, "AHL15", "唐三藏", "AT1G01021", 700, 708, '-', 8.5001, 0.000600, "AAGGTTAA", 1);
  // initMotifHit(&hit3, "AHL18", "猪八戒", "AT1G01022", 800, 808, '+', 6.7000, 0.000700, "TTAACCAA", 2);
  // initMotifHit(&hit4, "AHL20", "沙僧", "AT1G01020", 650, 658, '-', 7.1000, 0.000800, "GGGTTTCC", 3);

  // // Add the test data to the store
  // insertIntoNodeStore(&store, &hit1);
  // insertIntoNodeStore(&store, &hit2);
  // insertIntoNodeStore(&store, &hit3);
  // insertIntoNodeStore(&store, &hit4);

  // // Print the store content to check if the data has been added correctly.
  // printNodeStore(&store);

  // printf("Test 3 Passed!\n");

  // size_t genesNum = countNodesInStore(&store);
  // size_t hitsNum = countAllMotifHitsInStore(&store);
  // printf("%ld genes and %ld hits found related to %s\n\n", genesNum, hitsNum, "ALH15");

  // printf("Testing deleteNodeByKeyStore\n\n");

  // if (deleteNodeByKeyStore(&store, "AT1G01022"))
  // {
  //   printf("AT1G01022 is deleted\n");
  // }
  // else
  // {
  //   printf("AT1G01022 does not exit.\n");
  // }
  // printNodeStore(&store);

  // printf("Testing writeMotifHitsToFile\n\n");
  // writeMotifHitsToFile(&store, "test_result/TestNode_resut.txt");

  // genesNum = countNodesInStore(&store);
  // hitsNum = countAllMotifHitsInStore(&store);
  // printf("Aftering filtering..\n");
  // printf("%ld genes and %ld hits found related to %s\n\n", genesNum, hitsNum, "ALH15");

  // // Free allocated memory
  // deleteMotifHitContents(&hit1);
  // deleteMotifHitContents(&hit2);
  // deleteMotifHitContents(&hit3);
  // freeNodeStore(&store);
  // printf("Memory freed successfully.\n");

  NodeStore *stores = malloc(2 * sizeof(NodeStore));

  testMultipleMotifs(stores);

  // test_insertIntoNodeStore1();
  return 0;
}

// 编译命令：
// 调试模式: gcc -DDEBUG -o test/TestNode test/TestNode.c src/Node.c src/MotifHit.c src/MotifHitVector.c src/MemCheck.c -I src/
// 普通模式: gcc -o test/TestNode test/TestNode.c src/Node.c src/MotifHit.c src/MotifHitVector.c -I src/