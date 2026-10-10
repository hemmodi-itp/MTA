"""
app_server.py — start / stop a benchmark app in a subprocess with chosen bug flags.

    with AppServer(app, port=8765, bugs=["BUG_07"]) as srv:
        ...  # srv.base_url is healthy here

Every bug flag the app knows is cleared from the child's environment first, so a
flag left in the parent shell can never leak into a "bug-free" run.
"""

import os
import subprocess
import sys
import time
import urllib.request
from typing import Iterable, Optional

from tools.benchmark.apps import REPO_ROOT, BenchmarkApp


class AppServerError(RuntimeError):
    pass


def child_env(bugs: Iterable[str], base: Optional[dict] = None) -> dict:
    env = dict(base if base is not None else os.environ)
    for key in list(env):
        if key == "BUGS" or (key.startswith("BUG_") and key[4:].isdigit()):
            env.pop(key)
    for bug in bugs:
        env[bug] = "1"
    return env


class AppServer:
    def __init__(self, app: BenchmarkApp, port: int, bugs: Iterable[str] = (),
                 startup_timeout_s: float = 30.0, log_path: Optional[str] = None):
        self.app = app
        self.port = port
        self.bugs = list(bugs)
        self.startup_timeout_s = startup_timeout_s
        self.log_path = log_path
        self.proc: Optional[subprocess.Popen] = None
        self._log = None

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def _healthy(self) -> bool:
        try:
            with urllib.request.urlopen(self.base_url + self.app.health_path, timeout=2) as r:
                return r.status == 200
        except Exception:
            return False

    def start(self) -> "AppServer":
        if self._healthy():
            raise AppServerError(f"port {self.port} is already serving something — stop it or pick --port")
        self._log = open(self.log_path, "a", encoding="utf-8") if self.log_path else subprocess.DEVNULL
        self.proc = subprocess.Popen(
            [sys.executable, "-m", self.app.module, "--port", str(self.port)],
            cwd=REPO_ROOT, env=child_env(self.bugs), stdout=self._log, stderr=subprocess.STDOUT,
        )
        deadline = time.monotonic() + self.startup_timeout_s
        while time.monotonic() < deadline:
            if self.proc.poll() is not None:
                raise AppServerError(f"{self.app.name} exited during startup (code {self.proc.returncode})")
            if self._healthy():
                return self
            time.sleep(0.25)
        self.stop()
        raise AppServerError(f"{self.app.name} not healthy on {self.base_url} after {self.startup_timeout_s}s")

    def stop(self) -> None:
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait(timeout=10)
        self.proc = None
        if self._log not in (None, subprocess.DEVNULL):
            self._log.close()
        self._log = None

    def __enter__(self) -> "AppServer":
        return self.start()

    def __exit__(self, *exc) -> None:
        self.stop()
