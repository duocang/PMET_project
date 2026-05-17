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
            return [build_dir / "pairing_parallel"]
        if mode in {"promoters", "intervals"}:
            return [build_dir / "indexing_fimo_fused", build_dir / "pairing_parallel"]
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

        # Track the subprocess PID in the task dir so /api/tasks/<id>/cancel
        # can find and kill the entire tree (the shell pipelines fork their
        # own children, so we need a process-group-aware kill via psutil).
        # Use a new session/process group for clean tree-kill semantics.
        task_id = task_meta.get("task_id", "")
        pid_file = config.RESULT_DIR / task_id / "worker.pid" if task_id else None
        if pid_file is not None:
            pid_file.parent.mkdir(parents=True, exist_ok=True)

        # Tell the workflow scripts where to drop progress.json. They source
        # scripts/lib/progress.sh which reads PROGRESS_FILE; if unset, the
        # emit_progress calls are no-ops (CLI runs).
        env = os.environ.copy()
        if task_id:
            env["PROGRESS_FILE"] = str(config.RESULT_DIR / task_id / "progress.json")

        # Admin-configurable MinHash threshold (see deploy/configure/
        # admin_settings.json). When set, this overrides the container
        # env / hardcoded default that scripts/lib/minhash.sh would
        # otherwise see. Unset / None falls back to the env value, so
        # docker-compose remains the source of truth in default deploys.
        if config.MINHASH_THRESHOLD is not None and config.MINHASH_THRESHOLD > 0:
            env["PMET_MINHASH_THRESHOLD"] = str(config.MINHASH_THRESHOLD)

        proc = None
        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                cwd=str(config.PROJECT_ROOT),
                env=env,
                start_new_session=True,
            )
            if pid_file is not None:
                pid_file.write_text(str(proc.pid))

            try:
                stdout, stderr = proc.communicate(timeout=3600 * 24)  # 24 h
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.communicate()
                return {"success": False, "error": "Execution timed out"}

            if proc.returncode != 0:
                clean_stdout = self._clean_process_output(stdout)
                clean_stderr = self._clean_process_output(stderr)
                # Persist stderr to disk so the admin debug endpoint can
                # tail it after the worker has long moved on. Best-effort
                # — write failure shouldn't mask the original command
                # failure we're already reporting.
                if task_id:
                    try:
                        log_path = config.RESULT_DIR / task_id / "stderr.log"
                        log_path.parent.mkdir(parents=True, exist_ok=True)
                        log_path.write_text(clean_stderr or "")
                    except OSError:
                        pass
                return {
                    "success": False,
                    "error": f"Command failed: {clean_stderr or clean_stdout or 'Unknown error'}",
                    "stdout": clean_stdout,
                    "stderr": clean_stderr,
                }

            return {
                "success": True,
                "stdout": self._clean_process_output(stdout),
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
        finally:
            if pid_file is not None:
                try:
                    pid_file.unlink()
                except FileNotFoundError:
                    pass
            # Always remove the progress sentinel — the shell script's own
            # `clear_progress` only fires on the success branch, so a crash,
            # a SIGTERM from the cancel endpoint, or a timeout would leave
            # a stale progress.json that makes the UI render the progress
            # bar forever. This finally guarantees cleanup.
            if task_id:
                progress_file = config.RESULT_DIR / task_id / "progress.json"
                try:
                    progress_file.unlink()
                except FileNotFoundError:
                    pass
                except OSError:
                    pass

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
