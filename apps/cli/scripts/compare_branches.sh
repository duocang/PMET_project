#!/bin/bash
#############################################
# 对比当前工作区与 HEAD 提交的运行结果
# 覆盖生产引擎: indexing (fused) + pairing (parallel)
# 结果存放在项目根目录 branch-compare/ 下
#############################################

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
PROJECT_ROOT="$REPO_ROOT"
# NOTE: this script builds binaries from a git worktree of the repo.
# Inner path assumptions (now core/ instead of PMET_project/src/) need
# revisiting; not part of baseline regression coverage.
COMPARE_DIR="$PROJECT_ROOT/branch-compare"
WORKTREE_DIR="/tmp/pmet-head-worktree"

INDEXING_VERSIONS="fused"
PAIRING_VERSIONS="parallel"

echo -e "${BLUE}========================================${NC}"
echo -e "${GREEN}PMET 全引擎分支结果对比${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""
echo -e "Indexing 引擎: ${YELLOW}$INDEXING_VERSIONS${NC}"
echo -e "Pairing  引擎: ${YELLOW}$PAIRING_VERSIONS${NC}"
echo -e "对比目录:      ${YELLOW}$COMPARE_DIR${NC}"
echo ""

rm -rf "$COMPARE_DIR"
for side in current head; do
  for v in $INDEXING_VERSIONS; do
    mkdir -p "$COMPARE_DIR/$side/indexing"
  done
  for v in $PAIRING_VERSIONS; do
    mkdir -p "$COMPARE_DIR/$side/pairing"
  done
done

# ── 辅助函数 ──

build_and_run() {
  local label="$1"   # current 或 head
  local root="$2"    # 项目根目录

  cd "$root"

  echo -e "${BLUE}[$label] 构建生产引擎${NC}"
  make build 2>&1 | tail -8

  echo -e "${BLUE}[$label] 运行 Indexing${NC}"
  for v in $INDEXING_VERSIONS; do
    echo -e "  ${YELLOW}indexing-$v${NC}"
    bash apps/cli/scripts/run_indexing.sh -v "$v" -o "$COMPARE_DIR/$label/indexing" 2>&1 | tail -2
  done

  echo -e "${BLUE}[$label] 运行 Pairing${NC}"
  for v in $PAIRING_VERSIONS; do
    echo -e "  ${YELLOW}pairing-$v${NC}"
    bash apps/cli/scripts/run_pairing.sh -o "$COMPARE_DIR/$label/pairing" 2>&1 | tail -2
  done
}

# ── 步骤 1: 当前工作区 ──

echo -e "${BLUE}━━━ 当前工作区 ━━━${NC}"
build_and_run "current" "$PROJECT_ROOT"

# ── 步骤 2: HEAD worktree ──

echo ""
echo -e "${BLUE}━━━ HEAD 提交 ━━━${NC}"
rm -rf "$WORKTREE_DIR"
HEAD_SHA=$(git rev-parse HEAD)
git worktree add "$WORKTREE_DIR" "$HEAD_SHA" --detach 2>&1 | head -2

# 将 FIMO 预计算结果复制到 worktree（C/C++ indexing 需要）
if [ -d "$PROJECT_ROOT/results/cli/demo/fimo_official" ]; then
  mkdir -p "$WORKTREE_DIR/results/cli/demo"
  cp -r "$PROJECT_ROOT/results/cli/demo/fimo_official" "$WORKTREE_DIR/results/cli/demo/"
fi

build_and_run "head" "$WORKTREE_DIR"

# ── 清理 worktree ──

cd "$PROJECT_ROOT"
git worktree remove --force "$WORKTREE_DIR" 2>/dev/null || true

# ── 对比摘要 ──

echo ""
echo -e "${BLUE}========================================${NC}"
echo -e "${GREEN}对比摘要${NC}"
echo -e "${BLUE}========================================${NC}"

all_identical=true

for v in $INDEXING_VERSIONS; do
  echo ""
  echo -e "${YELLOW}Indexing [$v]${NC}"

  cur_dir="$COMPARE_DIR/current/indexing/$v"
  head_dir="$COMPARE_DIR/head/indexing/$v"

  if [ ! -d "$cur_dir" ] || [ ! -d "$head_dir" ]; then
    echo -e "  ${RED}SKIPPED (目录缺失)${NC}"
    continue
  fi

  # binomial_thresholds.txt
  if [ -f "$cur_dir/binomial_thresholds.txt" ]; then
    if diff -q "$cur_dir/binomial_thresholds.txt" "$head_dir/binomial_thresholds.txt" > /dev/null 2>&1; then
      echo -e "  binomial_thresholds.txt: ${GREEN}IDENTICAL${NC}"
    else
      echo -e "  binomial_thresholds.txt: ${RED}DIFFERENT${NC}"
      diff "$cur_dir/binomial_thresholds.txt" "$head_dir/binomial_thresholds.txt" || true
      all_identical=false
    fi
  fi

  # fimohits/
  if [ -d "$cur_dir/fimohits" ]; then
    fimo_diff=0
    fimo_total=0
    for f in "$cur_dir/fimohits"/*.txt; do
      name=$(basename "$f")
      fimo_total=$((fimo_total + 1))
      if ! diff -q "$f" "$head_dir/fimohits/$name" > /dev/null 2>&1; then
        fimo_diff=$((fimo_diff + 1))
      fi
    done
    if [ "$fimo_diff" -eq 0 ]; then
      echo -e "  fimohits/ ($fimo_total 文件): ${GREEN}ALL IDENTICAL${NC}"
    else
      echo -e "  fimohits/ ($fimo_total 文件): ${RED}$fimo_diff DIFFERENT${NC}"
      all_identical=false
    fi
  fi
done

for v in $PAIRING_VERSIONS; do
  echo ""
  echo -e "${YELLOW}Pairing [$v]${NC}"

  cur_file="$COMPARE_DIR/current/pairing/$v/motif_output.txt"
  head_file="$COMPARE_DIR/head/pairing/$v/motif_output.txt"

  if [ ! -f "$cur_file" ] || [ ! -f "$head_file" ]; then
    echo -e "  ${RED}SKIPPED (文件缺失)${NC}"
    continue
  fi

  cur_lines=$(wc -l < "$cur_file")
  if diff -q "$cur_file" "$head_file" > /dev/null 2>&1; then
    echo -e "  motif_output.txt ($cur_lines 行): ${GREEN}IDENTICAL${NC}"
  else
    echo -e "  motif_output.txt ($cur_lines 行): ${RED}DIFFERENT${NC}"
    diff "$cur_file" "$head_file" | head -10
    all_identical=false
  fi
done

echo ""
echo -e "${BLUE}========================================${NC}"
if $all_identical; then
  echo -e "${GREEN}结论: 全部 5 个引擎的输出完全一致${NC}"
else
  echo -e "${RED}结论: 存在差异，请检查上方详情${NC}"
fi
echo -e "结果: ${YELLOW}$COMPARE_DIR${NC}"
echo -e "清理: ${YELLOW}rm -rf $COMPARE_DIR${NC}"
echo -e "${BLUE}========================================${NC}"
