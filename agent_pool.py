#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Sequential agent pool runner.

- Reads a Python dict named SIMULATION (defined at the bottom) or, optionally,
  a JSON file passed as the first CLI arg (see -- How to run -- below).
- For each entry (in insertion order), runs the given CLI line `n` times.
- Starts the next run only after the previous process exits.
- Streams logs to console and writes per-run log files under ./agent_logs/
- Gracefully handles Ctrl+C (tries to terminate the current child then stops).
"""

import os
import sys
import json
import shlex
import signal
import time
import threading
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Iterable, Tuple, Optional

# ------------- helpers ------------- #

def now_stamp() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")

def slugify(text: str, max_len: int = 40) -> str:
    keep = []
    for ch in text:
        if ch.isalnum() or ch in ("-", "_"):
            keep.append(ch)
        elif ch.isspace() or ch in ("/", "\\", ":", ".", ","):
            keep.append("-")
    s = "".join(keep).strip("-")
    return (s[:max_len] or "job").rstrip("-")

def ensure_dir(p: Path) -> Path:
    p.mkdir(parents=True, exist_ok=True)
    return p

def read_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)

def to_jobs_sequence(sim_cfg: Dict[str, Any]) -> Iterable[Tuple[str, Dict[str, Any]]]:
    """
    Accepts either:
      {"jobs": {"nameA": {...}, "nameB": {...}}}
      or     : {"nameA": {...}, "nameB": {...}}
    Returns an insertion-ordered iterable of (name, job_dict).
    """
    if "jobs" in sim_cfg and isinstance(sim_cfg["jobs"], dict):
        items = sim_cfg["jobs"].items()
    else:
        items = sim_cfg.items()
    # Python 3.7+ preserves insertion order for dicts
    return items

def build_cmd(cli_line: str, use_shell: bool) -> Any:
    """
    If use_shell is True, return the raw string.
    If False, split into argv list safely with shlex.
    """
    if use_shell:
        return cli_line
    # On Windows, use posix=False for proper quoting rules
    posix = (os.name != "nt")
    return shlex.split(cli_line, posix=posix)

def stream_pipe(pipe, sink_file, prefix: str = ""):
    """
    Read lines from a subprocess pipe, write them to console and file.
    """
    for line in iter(pipe.readline, ""):
        # line is str if text=True in Popen
        if not line:
            break
        if prefix:
            print(prefix + line, end="")
        else:
            print(line, end="")
        if sink_file:
            sink_file.write(line)
            sink_file.flush()

# ------------- core runner ------------- #

class Runner:
    def __init__(self,
                 log_root: Path = Path("./agent_logs"),
                 default_timeout_sec: Optional[float] = None,
                 default_sleep_between_runs_sec: float = 0.0,
                 default_retries: int = 0,
                 use_shell: bool = True):
        """
        use_shell=True lets you paste your existing cli_line verbatim.
        Set to False if you prefer argv lists and stricter safety.
        """
        self.log_root = ensure_dir(log_root)
        self.default_timeout = default_timeout_sec
        self.default_sleep = default_sleep_between_runs_sec
        self.default_retries = default_retries
        self.use_shell = use_shell
        self._stop_requested = False
        signal.signal(signal.SIGINT, self._sigint)

    def _sigint(self, *_):
        self._stop_requested = True
        print("\n[runner] Ctrl+C received — will stop after current process.\n")

    def run_job_once(self, job_name: str, job_cfg: Dict[str, Any], run_index: int) -> int:
        cli_line = job_cfg["cli_line"]
        cwd = job_cfg.get("cwd", None)
        timeout = job_cfg.get("timeout_sec", self.default_timeout)
        # JSON can't have None as default easily; allow strings "null"/"None"
        if isinstance(timeout, str) and timeout.lower() in {"none", "null", ""}:
            timeout = None

        # Where to write logs
        stamp = now_stamp()
        safe_name = slugify(job_name)
        custom_agent_id = job_cfg.get("agent_id")
        if custom_agent_id:
            safe_agent_id = os.path.basename(os.path.normpath(str(custom_agent_id)))
            if not safe_agent_id:
                safe_agent_id = f"{stamp}_{safe_name}_{run_index:03d}"
        else:
            safe_agent_id = f"{stamp}_{safe_name}_{run_index:03d}"

        run_dir = ensure_dir(self.log_root / safe_agent_id)
        stdout_path = run_dir / "stdout.log"
        stderr_path = run_dir / "stderr.log"
        meta_path = run_dir / "meta.json"

        cmd = build_cmd(cli_line, use_shell=self.use_shell)

        print(f"\n[runner] Starting {job_name} (run {run_index})")
        if cwd:
            print(f"[runner]  cwd: {cwd}")
        print(f"[runner]  cmd: {cli_line}")
        if timeout:
            print(f"[runner]  timeout: {timeout}s")
        print(f"[runner]  logs: {run_dir}")

        start_ts = time.time()
        timed_out = False

        # Launch process
        # We use text=True so pipes yield str; bufsize=1 for line buffering.
        with open(stdout_path, "w", encoding="utf-8") as fout, \
             open(stderr_path, "w", encoding="utf-8") as ferr:

            env = os.environ.copy()
            extra_env = job_cfg.get("env")
            if isinstance(extra_env, dict):
                env.update({str(k): str(v) for k, v in extra_env.items()})
            env["CUA_AGENT_ID"] = safe_agent_id

            proc = subprocess.Popen(
                cmd,
                shell=self.use_shell,
                cwd=cwd or None,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                env=env
            )

            # Stream stdout/stderr concurrently
            t_out = threading.Thread(target=stream_pipe, args=(proc.stdout, fout, ""), daemon=True)
            t_err = threading.Thread(target=stream_pipe, args=(proc.stderr, ferr, ""), daemon=True)
            t_out.start()
            t_err.start()

            try:
                proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                print(f"[runner]  timeout reached; terminating PID {proc.pid} ...")
                timed_out = True
                proc.terminate()
                try:
                    proc.wait(10)
                except subprocess.TimeoutExpired:
                    print(f"[runner]  terminate hung; killing PID {proc.pid} ...")
                    proc.kill()

            # ensure threads exit
            t_out.join(timeout=1.0)
            t_err.join(timeout=1.0)

            exit_code = proc.returncode if proc.returncode is not None else -1

        end_ts = time.time()

        meta = {
            "job_name": job_name,
            "cli_line": cli_line,
            "cwd": cwd,
            "run_index": run_index,
            "start_time": datetime.fromtimestamp(start_ts).isoformat(),
            "end_time": datetime.fromtimestamp(end_ts).isoformat(),
            "duration_sec": round(end_ts - start_ts, 3),
            "exit_code": exit_code,
            "timed_out": timed_out,
            "log_dir": str(run_dir)
        }
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2)

        status = "OK" if exit_code == 0 and not timed_out else "FAIL"
        print(f"[runner] Finished {job_name} (run {run_index}) -> {status} (exit_code={exit_code})")
        return exit_code

    def run_simulation(self, sim_cfg: Dict[str, Any]) -> None:
        sleep_default = float(sim_cfg.get("sleep_between_runs_sec", self.default_sleep))
        retries_default = int(sim_cfg.get("retries", self.default_retries))

        for job_name, job_cfg in to_jobs_sequence(sim_cfg):
            if not isinstance(job_cfg, dict):
                print(f"[runner] Skipping {job_name}: expected a dict with keys 'cli_line' and 'n'.")
                continue

            cli_line = job_cfg.get("cli_line")
            n = int(job_cfg.get("n", 1))
            if not cli_line:
                print(f"[runner] Skipping {job_name}: missing 'cli_line'.")
                continue
            if n <= 0:
                print(f"[runner] Skipping {job_name}: n={n} (nothing to run).")
                continue

            sleep_between = float(job_cfg.get("sleep_between_runs_sec", sleep_default))
            retries = int(job_cfg.get("retries", retries_default))

            for i in range(1, n + 1):
                if self._stop_requested:
                    print("[runner] Stop requested — aborting remaining runs.")
                    return

                attempt = 0
                while True:
                    attempt += 1
                    exit_code = self.run_job_once(job_name, job_cfg, i)
                    if exit_code == 0 or attempt > (1 + retries):
                        break
                    print(f"[runner] {job_name} (run {i}) failed with exit_code={exit_code}. "
                          f"Retrying [{attempt-1}/{retries}] ...")
                    time.sleep(1.0)

                if i < n and sleep_between > 0:
                    print(f"[runner] Sleeping {sleep_between:.1f}s before next run of {job_name} ...")
                    time.sleep(sleep_between)

        print("\n[runner] All jobs completed.")

# ------------- How to run ------------- #
# Option A: edit SIMULATION below and run:   python agent_pool.py
# Option B: put the same structure in JSON and run:   python agent_pool.py path/to/sim.json
#               e.g. { "jobs": { "task1": {"cli_line": "...", "n": 3, "cwd": "..."}, ... },
#                      "sleep_between_runs_sec": 2 }

def main():
    # Defaults can also be overridden per-job in the SIMULATION / JSON.
    runner = Runner(
        log_root=Path("./agent_logs"),
        default_timeout_sec=None,            # or e.g. 3600 to hard-stop long runs
        default_sleep_between_runs_sec=0.0,  # pause between runs of the same job
        default_retries=0,                   # automatic retries on non-zero exit
        use_shell=True                       # paste cli_line exactly as you run it
    )

    if len(sys.argv) > 1:
        cfg_path = Path(sys.argv[1]).expanduser()
        sim_cfg = read_json(cfg_path)
    else:
        # Fall back to the inline SIMULATION dict below
        sim_cfg = SIMULATION

    runner.run_simulation(sim_cfg)

# ------------- Your simulation goes here ------------- #
# IMPORTANT:
# - Dict insertion order is preserved in Python 3.7+, so the order you define
#   below is the order they will run.
# - If you run from JSON, use {"jobs": { ... }} as shown in the comment above.

SIMULATION: Dict[str, Any] = {
    # Example 1 — your exact GOV.UK command run 2 times, sequentially.
    "agent_1": {
        "cli_line": (
            'python cli.py '
            '--start-url https://www.gov.uk '
            '--stop-on-message '
            '--max-actions 20 '
            '--input "Act fully autonomously without asking guiding questions to the user '
            'until you complete your objective. Objective: Navigate this website to find research '
            'publications from France."'
        ),
        "n": 1,
        # Set cwd to the folder where cli.py lives (uncomment & edit):
        # "cwd": "/absolute/path/to/your/service/folder",
        # Optional per-job overrides:
        "timeout_sec": 400,
        "sleep_between_runs_sec": 1.0,
        # "retries": 0
    }

    # You can add more entries; they will be processed in this order.
    # "third_task": {"cli_line": "...", "n": 3}
}

if __name__ == "__main__":
    main()

