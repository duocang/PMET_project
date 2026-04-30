import subprocess
import os
import platform
import re
import struct
from pathlib import Path
from typing import Optional

from ..config import config


class PMETExecutor:
    """Execute PMET shell scripts with proper parameter passing"""

    ANSI_ESCAPE_RE = re.compile(r"\x1B\[[0-?]*[ -/]*[@-~]")

    # Paths are relative to PROJECT_ROOT. All three modes run merged
    # audience-agnostic workflows at scripts/workflows/.
    SCRIPT_MAP = {
        "promoters_pre": "scripts/workflows/pair_only.sh",
        "promoters": "scripts/workflows/promoter.sh",
        "intervals": "scripts/workflows/intervals.sh",
    }

    ARCH_ALIASES = {
        "x86_64": "x86_64",
        "amd64": "x86_64",
        "aarch64": "arm64",
        "arm64": "arm64",
    }

    def _required_binaries(self, mode: str) -> list[Path]:
        build_dir = config.PMET_SCRIPTS_DIR / "build"
        if mode == "promoters_pre":
            return [build_dir / "pair_parallel"]
        if mode in {"promoters", "intervals"}:
            return [build_dir / "index_fimo_fused", build_dir / "pair_parallel"]
        return []

    def _normalize_arch(self, arch: str) -> str:
        return self.ARCH_ALIASES.get(arch.lower(), arch.lower())

    def _describe_binary(self, binary_path: Path) -> tuple[str, str]:
        try:
            with binary_path.open("rb") as handle:
                header = handle.read(20)
        except OSError:
            return "unreadable", "unknown"

        if header[:4] == b"\x7fELF":
            if len(header) >= 20:
                e_machine = struct.unpack("<H", header[18:20])[0]
                if e_machine == 0x3E:
                    return "elf", "x86_64"
                if e_machine == 0xB7:
                    return "elf", "arm64"
            return "elf", "unknown"

        if header[:4] in {
            b"\xcf\xfa\xed\xfe",
            b"\xfe\xed\xfa\xcf",
            b"\xca\xfe\xba\xbe",
            b"\xbe\xba\xfe\xca",
        }:
            return "mach-o", "unknown"

        return "unknown", "unknown"

    def _validate_runtime_dependencies(self, mode: str) -> Optional[str]:
        current_system = platform.system().lower()
        current_arch = self._normalize_arch(platform.machine())

        for binary_path in self._required_binaries(mode):
            if not binary_path.exists():
                return f"Required PMET binary is missing: {binary_path}"

            binary_format, binary_arch = self._describe_binary(binary_path)
            if current_system == "linux" and binary_format == "mach-o":
                return (
                    f"Required PMET binary {binary_path} is a macOS Mach-O executable and cannot run inside "
                    "the Linux Docker worker. Rebuild Linux binaries or run the worker on the host."
                )
            if (
                current_system == "linux"
                and binary_format == "elf"
                and binary_arch != "unknown"
                and binary_arch != current_arch
            ):
                return (
                    f"Required PMET binary {binary_path} targets Linux/{binary_arch}, but the worker is "
                    f"running on Linux/{current_arch}. Use matching container platform or rebuild the binary."
                )

        return None

    def preflight_check(self, task_meta: dict) -> Optional[str]:
        mode = task_meta["mode"]
        script_name = self.SCRIPT_MAP.get(mode)

        if not script_name:
            return f"Unknown mode: {mode}"

        script_path = config.PROJECT_ROOT / script_name
        if not script_path.exists():
            return f"Script not found: {script_path}"

        return self._validate_runtime_dependencies(mode)

    def _clean_process_output(self, text: str) -> str:
        return self.ANSI_ESCAPE_RE.sub("", text).strip()

    def execute(self, task_meta: dict) -> dict:
        mode = task_meta["mode"]
        script_name = self.SCRIPT_MAP.get(mode)

        if not script_name:
            return {"success": False, "error": f"Unknown mode: {mode}"}

        script_path = config.PROJECT_ROOT / script_name
        if not script_path.exists():
            return {"success": False, "error": f"Script not found: {script_path}"}

        dependency_error = self._validate_runtime_dependencies(mode)
        if dependency_error:
            return {"success": False, "error": dependency_error}

        # Make script executable
        os.chmod(script_path, 0o755)

        # Build command arguments safely
        if mode == "promoters_pre":
            cmd = self._build_promoters_pre_cmd(task_meta, script_path)
        elif mode == "promoters":
            cmd = self._build_promoters_cmd(task_meta, script_path)
        else:
            cmd = self._build_intervals_cmd(task_meta, script_path)

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                cwd=str(config.PROJECT_ROOT),
                timeout=3600 * 24,  # 24 hours
            )

            if result.returncode != 0:
                clean_stdout = self._clean_process_output(result.stdout)
                clean_stderr = self._clean_process_output(result.stderr)
                return {
                    "success": False,
                    "error": f"Command failed: {clean_stderr or clean_stdout or 'Unknown error'}",
                    "stdout": clean_stdout,
                    "stderr": clean_stderr,
                }

            return {
                "success": True,
                "stdout": self._clean_process_output(result.stdout),
            }
        except subprocess.TimeoutExpired:
            return {"success": False, "error": "Execution timed out"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _task_dirs(self, task_id: str) -> tuple[Path, Path]:
        """Return (indexing_dir, pairing_dir) for a task under the new layout."""
        root = config.RESULT_DIR / task_id
        return root / "indexing", root / "pairing"

    def _build_promoters_pre_cmd(self, meta: dict, script_path: Path) -> list:
        """Build command for promoters_pre mode (pre-computed index)"""
        index_dir = meta.get("premade_index", "")
        genes_file = meta.get("genes_file", "")
        email = meta["email"]
        result_link = meta.get("result_link", "")
        task_id = meta["task_id"]
        _, pair_dir = self._task_dirs(task_id)

        return [
            str(script_path),
            "-d", str(index_dir),
            "-g", str(genes_file),
            "-i", str(meta.get("ic_threshold", 24)),
            "-t", str(config.NCPU),
            "-o", str(pair_dir),
            "-e", email,
            "-l", result_link,
        ]

    def _build_promoters_cmd(self, meta: dict, script_path: Path) -> list:
        """Build command for full promoters mode"""
        task_id = meta["task_id"]
        index_dir, pair_dir = self._task_dirs(task_id)

        # Prepare input file paths
        fasta_file = meta.get("fasta_file", "")
        gff3_file = meta.get("gff3_file", "")
        meme_file = meta.get("meme_file", "")
        genes_file = meta.get("genes_file", "")

        return [
            str(script_path),
            "-r", str(config.PMET_SCRIPTS_DIR),
            "-i", "gene_id=",
            "-o", str(index_dir),
            "-n", str(meta.get("promoter_num", 5000)),
            "-k", str(meta.get("max_match", 5)),
            "-p", str(meta.get("promoter_length", 1000)),
            "-f", str(meta.get("fimo_threshold", 0.05)),
            "-v", meta.get("promoters_overlap", "NoOverlap"),
            "-u", meta.get("utr5", "No"),
            "-t", str(config.NCPU),
            "-c", str(meta.get("ic_threshold", 24)),
            "-x", str(pair_dir),
            "-g", str(genes_file),
            "-e", meta["email"],
            "-l", meta.get("result_link", ""),
            str(fasta_file),
            str(gff3_file),
            str(meme_file),
        ]

    def _build_intervals_cmd(self, meta: dict, script_path: Path) -> list:
        """Build command for intervals mode"""
        task_id = meta["task_id"]
        index_dir, pair_dir = self._task_dirs(task_id)

        fasta_file = meta.get("fasta_file", "")
        meme_file = meta.get("meme_file", "")
        genes_file = meta.get("genes_file", "")

        return [
            str(script_path),
            "-r", str(config.PMET_SCRIPTS_DIR),
            "-o", str(index_dir),
            "-n", str(meta.get("promoter_num", 5000)),
            "-k", str(meta.get("max_match", 5)),
            "-f", str(meta.get("fimo_threshold", 0.05)),
            "-t", str(config.NCPU),
            "-x", str(pair_dir),
            "-g", str(genes_file),
            "-c", str(meta.get("ic_threshold", 24)),
            "-e", meta["email"],
            "-l", meta.get("result_link", ""),
            str(fasta_file),
            str(meme_file),
        ]
