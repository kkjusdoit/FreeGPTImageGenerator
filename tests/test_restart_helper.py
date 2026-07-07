import os
import unittest

from utils import restart_helper


class RestartHelperTests(unittest.TestCase):
    def test_build_restart_command_uses_existing_script_and_args(self):
        cmd = restart_helper.build_restart_command(
            argv=["wfxl_openai_regst.py", "--flag"],
            executable="/tmp/python",
        )

        self.assertEqual("/tmp/python", cmd[0])
        self.assertTrue(cmd[1].endswith("wfxl_openai_regst.py"))
        self.assertEqual(["--flag"], cmd[2:])

    def test_build_restart_command_falls_back_to_default_entrypoint(self):
        cmd = restart_helper.build_restart_command(
            argv=["missing-entry.py", "--reload"],
            executable="/tmp/python",
        )

        self.assertEqual(
            ["/tmp/python", restart_helper.DEFAULT_ENTRYPOINT, "--reload"],
            cmd,
        )

    def test_spawn_restart_process_detaches_child_from_terminal(self):
        calls = []

        def fake_popen(*args, **kwargs):
            calls.append((args, kwargs))
            return object()

        cmd = restart_helper.spawn_restart_process(
            argv=["missing-entry.py"],
            executable="/tmp/python",
            cwd="/tmp/project",
            popen=fake_popen,
        )

        self.assertEqual(["/tmp/python", restart_helper.DEFAULT_ENTRYPOINT], cmd)
        self.assertEqual(1, len(calls))
        args, kwargs = calls[0]
        self.assertEqual((cmd,), args)
        self.assertEqual("/tmp/project", kwargs["cwd"])
        self.assertTrue(kwargs["close_fds"])
        self.assertTrue(kwargs["start_new_session"])
        self.assertEqual(os.devnull, kwargs["stdin"].name)
        self.assertEqual(os.devnull, kwargs["stdout"].name)
        self.assertEqual(os.devnull, kwargs["stderr"].name)


if __name__ == "__main__":
    unittest.main()
