#!/bin/bash
# Compile and run all unit tests

# Change to project root
cd "$(dirname "${BASH_SOURCE[0]}")/.."

PASSED=0
FAILED=0
FAILED_TESTS=""

# Test runner function
run_test() {
    local name="$1"
    local cmd="$2"

    printf "%-30s" "$name"
    if eval "$cmd" 2>/dev/null && ./test/$name >/dev/null 2>&1; then
        echo "PASS"
        PASSED=$((PASSED + 1))
    else
        echo "FAIL"
        FAILED=$((FAILED + 1))
        FAILED_TESTS="$FAILED_TESTS $name"
    fi
}

echo "Running tests..."
echo "========================================"

run_test "TestFileRead" \
    "gcc -o test/TestFileRead test/TestFileRead.c src/FileRead.c src/MemCheck.c -I src/"

run_test "TestFimoFile" \
    "gcc -o test/TestFimoFile test/TestFimoFile.c src/FimoFile.c src/FileRead.c src/HashTable.c src/MotifHit.c src/MotifHitVector.c src/PromoterLength.c src/ScoreLabelPairVector.c src/utils.c src/MemCheck.c -I src/"

run_test "TestHashTable" \
    "gcc -o test/TestHashTable test/TestHashTable.c src/HashTable.c src/MotifHit.c src/MotifHitVector.c src/MemCheck.c -I src/"

run_test "TestMemCheck" \
    "gcc -DDEBUG -o test/TestMemCheck test/TestMemCheck.c src/MemCheck.c -I src/"

run_test "TestMotifHit" \
    "gcc -DDEBUG -o test/TestMotifHit test/TestMotifHit.c src/MotifHit.c src/MemCheck.c -I src/"

run_test "TestMotifHitVector" \
    "gcc -DDEBUG -o test/TestMotifHitVector test/TestMotifHitVector.c src/MotifHitVector.c src/MotifHit.c src/MemCheck.c -I src/"

run_test "TestNode" \
    "gcc -DDEBUG -o test/TestNode test/TestNode.c src/Node.c src/MotifHit.c src/MotifHitVector.c src/MemCheck.c -I src/"

run_test "TestPromoterLength" \
    "gcc -DDEBUG -o test/TestPromoterLength test/TestPromoterLength.c src/PromoterLength.c src/FileRead.c src/MemCheck.c -I src/"

run_test "TestScoreLabelPairVector" \
    "gcc -DDEBUG -o test/TestScoreLabelPairVector test/TestScoreLabelPairVector.c src/ScoreLabelPairVector.c src/MemCheck.c -I src/"

run_test "TestUtils" \
    "gcc -DDEBUG -o test/TestUtils test/TestUtils.c src/utils.c src/MemCheck.c -I src/"

# Summary
echo "========================================"
echo "Passed: $PASSED, Failed: $FAILED"
if [ -n "$FAILED_TESTS" ]; then
    echo "Failed tests:$FAILED_TESTS"
fi

# Cleanup test executables
rm -f test/Test*[!.c]

# Exit with error if any test failed
[ $FAILED -eq 0 ]