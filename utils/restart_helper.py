import os
import subprocess
import sys
from typing import Callable, Optional


BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_ENTRYPOINT = os.path.join(BASE_DIR, "wfxl_openai_regst.py")


def build_restart_command(
    argv: Optional[list[str]] = None,
    executable: Optional[str] = None,
    default_script: Optional[str] = None,
) -> list[str]:
    argv = list(argv if argv is not None else sys.argv)
    executable = executable or sys.executable
    default_script = default_script or DEFAULT_ENTRYPOINT

    if getattr(sys, "frozen", False):
        return argv or [executable]

    extra_args = argv[1:] if len(argv) > 1 else []
    script_path = os.path.abspath(argv[0]) if argv else ""

    if not script_path or not os.path.exists(script_path):
        script_path = default_script

    return [executable, script_path, *extra_args]


def spawn_restart_process(
    argv: Optional[list[str]] = None,
    executable: Optional[str] = None,
    cwd: Optional[str] = None,
    popen: Optional[Callable[..., subprocess.Popen]] = None,
) -> list[str]:
    cmd = build_restart_command(argv=argv, executable=executable)
    runner = popen or subprocess.Popen
    with open(os.devnull, "ab", buffering=0) as devnull:
        runner(
            cmd,
            cwd=cwd or BASE_DIR,
            stdin=devnull,
            stdout=devnull,
            stderr=devnull,
            close_fds=True,
            start_new_session=True,
        )
    return cmd
