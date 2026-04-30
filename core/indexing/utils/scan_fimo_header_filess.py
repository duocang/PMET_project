#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
扫描 src 目录中从 fimo.c / fimo.h 出发可达的 #include 头文件依赖：
- 统计系统头文件数量与本地头文件（存在于 src/ 中）数量
- 输出详细列表与汇总到 need_headers.txt
- 清理并重建 ./src_fimo，将 fimo.c/fimo.h 与所有本地头文件及其同名 .c 复制过去（保持相对目录结构）
"""

# === 标准库导入 ===
import os
import re
import shutil
from typing import Set, Tuple, Dict

# 终端颜色（macOS/Linux 支持 ANSI 转义序列）
class Color:
    BOLD = "\033[1m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    CYAN = "\033[36m"
    RESET = "\033[0m"


# === 全局配置 ===
INITIAL_FILES = ['fimo.h', 'fimo.c']  # 扫描起点
SRC_DIR = './src'                # 源代码根目录（修正为当前目录下的 src）
DEST_DIR = './src_fimo'               # 拷贝输出目录
NEED_HEADERS_FILE = 'need_headers.txt'

# 用于匹配 #include 语句：捕获分隔符与文件名（不含尖括号/引号）
INCLUDE_PATTERN = re.compile(
    r'^\s*#\s*include\s*(?P<delim>[<"])\s*(?P<name>[^">]+?)\s*(?:[>"])'
)


# === 工具函数 ===
def find_file_in_src(file_name: str) -> str | None:
    """
    在 SRC_DIR 下查找文件：
    - 若 file_name 含路径分隔符，优先尝试以 SRC_DIR/file_name 直接定位；
    - 否则在 SRC_DIR 里按“同名文件”遍历查找。
    """
    # 先尝试“带相对路径”的直接定位
    norm = os.path.normpath(os.path.join(SRC_DIR, file_name))
    if os.path.sep in file_name and os.path.isfile(norm):
        return norm

    # 再按“同名文件”遍历查找
    base = os.path.basename(file_name)
    for root, _, files in os.walk(SRC_DIR):
        if base in files:
            return os.path.join(root, base)
    return None


def read_includes(file_path: str) -> Set[Tuple[str, bool]]:
    """
    读取单个源/头文件，提取其中的 #include 集合。
    返回集合元素为 (header_name, is_quoted)，其中：
      - header_name: 头文件名（可能带相对路径）
      - is_quoted: 是否为引号包含（True 表示 #include "xxx.h"，False 表示 #include <xxx.h>）
    """
    includes: Set[Tuple[str, bool]] = set()
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                m = INCLUDE_PATTERN.match(line)
                if m:
                    name = m.group('name').strip()
                    is_quoted = (m.group('delim') == '"')
                    includes.add((name, is_quoted))
    except Exception as e:
        print(f"Error reading file {file_path}: {e}")
    return includes

def is_local_header(header_name: str) -> bool:
    """
    判定是否为本地头文件：只要能在 SRC_DIR 中找到同名文件即视为本地。
    """
    return find_file_in_src(header_name) is not None


def is_system_header(header_name: str) -> bool:
    """
    判定是否为系统头文件：在 SRC_DIR 找不到同名文件即视为系统。
    """
    return not is_local_header(header_name)


# === 扫描阶段 ===
def scan_dependencies(initial_files: Set[str]) -> Tuple[Set[str], Set[str], Set[str]]:
    """
    从 initial_files 出发，分层扫描 #include 依赖。
    - 仅对“引号包含”的本地头文件进行递归扫描；
    - 每轮构建 current_tier（本轮新发现的头文件名，含系统与本地），并合并入 all_headers；
    - visited 用于避免重复读取同一个源码文件（按解析到的实际路径去重）。
    返回 (all_headers, system_headers, local_headers)。
    """
    visited_paths: Set[str] = set()      # 已扫描过的“实际文件路径”（.c/.h）
    all_headers: Set[str] = set()        # 所有出现过的 include 名称（去重）
    system_headers: Set[str] = set()     # 系统头文件（尖括号）
    local_headers: Set[str] = set()      # 本地头文件（引号）

    # 本轮需要“读取并解析”的源码文件名集合（初始为 fimo.c / fimo.h）
    files_to_scan: Set[str] = set(initial_files)
    tier_num = 1

    while files_to_scan:
        print(f"\n=== Tier {tier_num} ===")
        # 仅用于展示/记录：本轮新发现的头文件集合
        current_tier_headers: Set[str] = set()
        # 下一轮需要解析的“本地头文件”的文件名集合（仅引号包含）
        next_files_to_scan: Set[str] = set()

        print(f"{Color.BOLD}{Color.RED}Files to scan this tier: {Color.RESET}{sorted(files_to_scan)}")
        for name in sorted(files_to_scan):
            # 解析实际路径并去重
            file_path = find_file_in_src(name)
            if not file_path:
                print(f"File {name} not found in {SRC_DIR}/")
                continue
            if file_path in visited_paths:
                continue
            visited_paths.add(file_path)

            # 解析 include 行
            for inc_name, is_quoted in read_includes(file_path):
                # print(f"  Found include: {'\"' if is_quoted else '<'}{inc_name}{'\"' if is_quoted else '>'} in {name}")
                print(inc_name)
                current_tier_headers.add(inc_name)
                all_headers.add(inc_name)
                if is_quoted:
                    local_headers.add(inc_name)
                    # 仅对“引号”本地头文件递归：加入下一轮扫描
                    next_files_to_scan.add(inc_name)
                    # 同名 .c 文件也需要扫描（如果存在）
                    if inc_name.endswith(".h"):
                        c_candidate = inc_name[:-2] + ".c"
                        if find_file_in_src(c_candidate):
                            next_files_to_scan.add(c_candidate)
                else:
                    system_headers.add(inc_name)

        # print(f"{Color.BOLD}{Color.GREEN}Current tier headers:{Color.RESET}\n{sorted(current_tier_headers)}")
        # print(f"{Color.BOLD}{Color.CYAN}Next files to scan (local only):{Color.RESET} \n{sorted(next_files_to_scan)}")
        # print(f"{Color.BOLD}{Color.CYAN}System headers:{Color.RESET} \n{sorted(system_headers)}")
        # print(f"{Color.BOLD}{Color.RED}Visited paths:{Color.RESET} \n{sorted(visited_paths)}")

        files_to_scan = next_files_to_scan
        tier_num += 1

    return all_headers, system_headers, local_headers


# === 输出与落盘 ===
def print_summary(all_headers: Set[str], system_headers: Set[str], local_headers: Set[str]) -> None:
    """
    控制台打印汇总与详细列表。
    """
    print("\n=== Summary ===")
    print(f"Total unique includes found: {len(all_headers)}")
    print(f"System headers: {len(system_headers)}")
    print(f"Local headers (in src/): {len(local_headers)}")

    print("\n=== System Headers ===")
    print("\n".join(sorted(system_headers)))

    print("\n=== Local Headers ===")
    print("\n".join(sorted(local_headers)))


def write_need_headers(path: str,
                       all_headers: Set[str],
                       system_headers: Set[str],
                       local_headers: Set[str]) -> None:
    """
    将统计信息写入 need_headers.txt。
    """
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write("=== Summary ===\n")
            f.write(f"Total unique includes: {len(all_headers)}\n")
            f.write(f"System headers: {len(system_headers)}\n")
            f.write(f"Local headers: {len(local_headers)}\n\n")

            f.write("=== System Headers ===\n")
            f.write("\n".join(sorted(system_headers)))
            f.write("\n\n=== Local Headers ===\n")
            f.write("\n".join(sorted(local_headers)))
        print(f"\nWrote summary to {path}")
    except Exception as e:
        print(f"Failed to write {path}: {e}")


# === 文件复制阶段 ===
def ensure_clean_dir(path: str) -> None:
    """
    删除已存在的目标目录并重建。
    """
    if os.path.exists(path):
        shutil.rmtree(path)
    os.makedirs(path, exist_ok=True)


def collect_files_to_copy(initial_files: Set[str],
                          local_headers: Set[str]) -> Set[str]:
    """
    需要复制的文件集合：
    - initial_files（fimo.c / fimo.h）
    - 所有“本地头文件”及其对应 .c（优先同目录查找，找不到再在 src 全局查找）
    返回值是源码中的绝对路径集合。
    """
    files: Set[str] = set()

    # 1) 初始文件
    for name in initial_files:
        p = find_file_in_src(name)
        if p:
            files.add(p)

    # 2) 本地头文件及其对应 .c
    for h in local_headers:
        hp = find_file_in_src(h)
        if not hp:
            continue
        files.add(hp)

        stem = os.path.splitext(os.path.basename(hp))[0]
        same_dir_c = os.path.join(os.path.dirname(hp), f"{stem}.c")
        if os.path.exists(same_dir_c):
            files.add(same_dir_c)
        else:
            cp = find_file_in_src(f"{stem}.c")
            if cp:
                files.add(cp)

    return files


def copy_files_to_dest(files: Set[str], src_root: str, dest_root: str) -> None:
    """
    按相对于 src_root 的相对路径复制文件到 dest_root，保持目录层级，避免同名冲突。
    """
    copied = 0
    for src_path in files:
        try:
            rel = os.path.relpath(src_path, start=src_root)
            if rel.startswith('..'):
                # 不在 src_root 下的罕见情况：退化为仅文件名
                rel = os.path.basename(src_path)
        except Exception:
            rel = os.path.basename(src_path)

        out_path = os.path.join(dest_root, rel)
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        try:
            shutil.copy2(src_path, out_path)
            copied += 1
        except Exception as e:
            print(f"Failed to copy {src_path} -> {out_path}: {e}")

    print(f"\nCopied {copied} files into {dest_root}")


# === 主流程 ===
def main() -> None:
    initial_set = set(INITIAL_FILES)

    # 1) 扫描依赖
    all_headers, system_headers, local_headers = scan_dependencies(initial_set)

    # 2) 输出与落盘
    print_summary(all_headers, system_headers, local_headers)
    write_need_headers(NEED_HEADERS_FILE, all_headers, system_headers, local_headers)

    # 3) 清理并复制文件到 src_fimo
    ensure_clean_dir(DEST_DIR)
    files_to_copy = collect_files_to_copy(initial_set, local_headers)
    copy_files_to_dest(files_to_copy, SRC_DIR, DEST_DIR)


if __name__ == "__main__":
    main()
