"""IITPAVE Installation and Configuration persistence manager."""
from __future__ import annotations

import json
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from app.config import USER_DATA_DIR
from .runner_config import IITPaveRunnerConfig, iitpave_runner_config_from_mapping

CONFIG_PATH = USER_DATA_DIR / "iitpave_config.json"
RUNS_DIR = USER_DATA_DIR / "iitpave_runs"

def load_persisted_config() -> IITPaveRunnerConfig:
    """Load the persisted IITPAVE configuration, falling back safely if missing."""
    if CONFIG_PATH.is_file():
        try:
            data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            return iitpave_runner_config_from_mapping(data)
        except Exception:
            pass
    return IITPaveRunnerConfig()

def save_persisted_config(cfg: IITPaveRunnerConfig) -> None:
    """Save the IITPAVE configuration to the user data directory."""
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(
        json.dumps(cfg.as_dict(), indent=4),
        encoding="utf-8"
    )

def detect_iitpave_version(exe_path: Path | str) -> str:
    """Probe the executable to extract version info from its stdout banner, or file metadata."""
    path = Path(exe_path)
    if not path.is_file():
        return "Not found"
    
    # Try running the executable with empty inputs to check if a banner is printed
    try:
        completed = subprocess.run(
            [str(path)],
            input="\n\n",  # send newlines to pass any prompt
            capture_output=True,
            text=True,
            timeout=2.0,
            shell=False,
        )
        output = (completed.stdout or "") + "\n" + (completed.stderr or "")
        for line in output.splitlines():
            clean = line.strip()
            if any(term in clean.upper() for term in ("IITPAVE", "IRC:37", "VERSION")):
                return clean
    except Exception:
        pass
    
    # Fallback to file size description
    try:
        size_kb = path.stat().st_size / 1024
        return f"IITPAVE executable ({size_kb:.0f} KB)"
    except Exception:
        return "Unknown IITPAVE binary"

def get_last_run_info() -> dict[str, Any] | None:
    """Get status and logs of the last run from the runs directory."""
    if not RUNS_DIR.is_dir():
        return None
    
    # Sort run folders chronologically by name (which starts with timestamp)
    subdirs = sorted(
        [d for d in RUNS_DIR.iterdir() if d.is_dir() and d.name.startswith("run_")],
        key=lambda d: d.name,
        reverse=True
    )
    if not subdirs:
        return None
    
    last_dir = subdirs[0]
    status_path = last_dir / "run_status.json"
    if not status_path.is_file():
        return None
        
    try:
        info = json.loads(status_path.read_text(encoding="utf-8"))
        info["run_id"] = last_dir.name
        info["run_dir"] = str(last_dir)
        
        # Read logs
        stdout_path = last_dir / "stdout.log"
        stderr_path = last_dir / "stderr.log"
        inp_path = last_dir / "iitp_inp.dat"
        out_path = last_dir / "iitp_out.dat"
        
        info["stdout"] = stdout_path.read_text(encoding="utf-8") if stdout_path.is_file() else ""
        info["stderr"] = stderr_path.read_text(encoding="utf-8") if stderr_path.is_file() else ""
        info["input"] = inp_path.read_text(encoding="utf-8") if inp_path.is_file() else ""
        info["output"] = out_path.read_text(encoding="utf-8") if out_path.is_file() else ""
        
        return info
    except Exception:
        return None
