import json
import os
from pathlib import Path
from dataclasses import dataclass, field


# Subdir of PROJECT_ROOT where task outputs land. Default keeps the
# host-side namespace separate from CLI output (results/app vs results/cli).
# Inside docker the host dir is bind-mounted directly onto /app/results, so
# the container has no use for the trailing /app/ — set PMET_RESULT_DIR_REL
# to "results" in docker-compose to drop it.
_DEFAULT_RESULT_DIR_REL = "results/app"


def _detect_project_root() -> Path:
    """Find the repo root from this file's location.

    Two layouts must both work:
      - host monorepo: apps/pmet_backend/config.py  ->  3 ups
      - docker mount:  /app/pmet_backend/config.py  ->  2 ups
    Pick whichever ancestor has a data/ sibling.
    """
    here = Path(__file__).resolve()
    for ups in (3, 2):
        cand = here.parents[ups - 1]
        if (cand / "data").is_dir():
            return cand
    # Fall back to the docker layout if neither matched (fresh setup).
    return here.parents[1]


@dataclass
class Config:
    PROJECT_ROOT: Path = _detect_project_root()
    # Web-app task outputs. Override via PMET_RESULT_DIR_REL (relative to
    # PROJECT_ROOT). Default = results/app on host so app and CLI outputs are
    # siblings under results/. Docker-compose sets it to "results" because
    # the host's results/app/ is mounted directly onto /app/results/, making
    # the trailing /app/ redundant inside the container.
    RESULT_DIR: Path = field(
        default_factory=lambda: _detect_project_root()
        / os.environ.get("PMET_RESULT_DIR_REL", _DEFAULT_RESULT_DIR_REL)
    )
    # Read-only catalog of pre-computed species/motif databases, populated by
    # scripts/fetch_data.sh. Layout: <species>/<motif_db>/.
    # Top-level: the indexes are reusable scientific resources (CLI's
    # pair_only.sh can target them too), not web-only. The two JSON sidecars
    # under data/app/ describe display labels for the submit form.
    PRECOMPUTED_INDEXING_DIR: Path = PROJECT_ROOT / "data" / "precomputed_indexes"
    PRECOMPUTED_INDEXING_METADATA: Path = PROJECT_ROOT / "data" / "app" / "indexing_metadata.json"
    GENOME_METADATA: Path = PROJECT_ROOT / "data" / "app" / "genome_n_annotation.json"
    # TASKS_DIR is derived from RESULT_DIR in __post_init__ so the env override
    # propagates without each call site re-reading the env.
    TASKS_DIR: Path = field(init=False)
    # Workflows + helpers (bash + python + R) live under scripts/.
    # The "-r" flag the indexer takes equals str(SCRIPTS_DIR).
    SCRIPTS_DIR: Path = PROJECT_ROOT / "scripts"
    # Repo root again — executor uses this for build/ and as the workflow base
    # path. Kept under the existing name to avoid a churn-y rename across the
    # executor and Dockerfile docs.
    PMET_SCRIPTS_DIR: Path = PROJECT_ROOT

    # Email configuration
    EMAIL_USERNAME: str = ""
    EMAIL_PASSWORD: str = ""
    EMAIL_ADDRESS: str = ""
    EMAIL_SERVER: str = ""
    EMAIL_PORT: str = ""

    # Server
    NCPU: int = 4
    NGINX_LINK: str = ""

    # Admin auth + behaviour. ADMIN_TOKEN comes from
    # data/configure/admin_token.txt (gitignored, single line). Empty token
    # means admin features are disabled — no one can log in.
    # NOTIFY_ON_SUBMIT toggles the per-task admin email; default True so
    # existing deployments don't silently change behaviour.
    ADMIN_TOKEN: str = ""
    NOTIFY_ON_SUBMIT: bool = True

    def __post_init__(self):
        self.TASKS_DIR = self.RESULT_DIR / "tasks"
        self.RESULT_DIR.mkdir(parents=True, exist_ok=True)
        self.TASKS_DIR.mkdir(parents=True, exist_ok=True)
        self._load_configs()

    def _load_configs(self):
        cpu_file = self.PROJECT_ROOT / "data" / "configure" / "cpu_configuration.txt"
        if cpu_file.exists():
            self.NCPU = int(cpu_file.read_text().strip().split()[0])

        nginx_file = self.PROJECT_ROOT / "data" / "configure" / "nginx_link.txt"
        if nginx_file.exists():
            self.NGINX_LINK = nginx_file.read_text().strip()

        email_file = self.PROJECT_ROOT / "data" / "configure" / "email_credential.txt"
        if email_file.exists():
            lines = email_file.read_text().strip().split("\n")
            if len(lines) >= 5:
                self.EMAIL_USERNAME = lines[0].strip()
                self.EMAIL_PASSWORD = lines[1].strip()
                self.EMAIL_ADDRESS = lines[2].strip()
                self.EMAIL_SERVER = lines[3].strip()
                self.EMAIL_PORT = lines[4].strip()

        admin_token_file = self.PROJECT_ROOT / "data" / "configure" / "admin_token.txt"
        if admin_token_file.exists():
            self.ADMIN_TOKEN = admin_token_file.read_text().strip()

        admin_settings_file = self.PROJECT_ROOT / "data" / "configure" / "admin_settings.json"
        if admin_settings_file.exists():
            try:
                settings = json.loads(admin_settings_file.read_text())
                if isinstance(settings, dict):
                    if isinstance(settings.get("notify_on_submit"), bool):
                        self.NOTIFY_ON_SUBMIT = settings["notify_on_submit"]
            except (json.JSONDecodeError, OSError):
                # Bad JSON shouldn't break config — keep defaults and let the
                # admin settings page rewrite it.
                pass

    def reload(self):
        """Re-read all *runtime-mutable* config files. Call when admin
        settings get updated through the API so the change is visible
        immediately without restarting the worker.
        """
        self._load_configs()

config = Config()
