"""The hook client: harness adapters and token counting (client/tokibot_client.py)."""
import importlib.util
import json
import os
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location(
    "tokibot_client", os.path.join(HERE, "..", "..", "client", "tokibot_client.py"))
client = importlib.util.module_from_spec(spec)
spec.loader.exec_module(client)


def adapt(harness, data, event="", cfg=None):
    out = client.adapt(harness, data, event, cfg)
    return out and out[0]


class AdapterTest(unittest.TestCase):
    def test_claude_passes_through(self):
        ev = adapt("claude", {"hook_event_name": "PreToolUse", "session_id": "s1",
                              "tool_name": "Bash", "cwd": "/home/me/proj"})
        self.assertEqual(ev["hook_event_name"], "PreToolUse")
        self.assertEqual(ev["session_id"], "s1")
        self.assertEqual(ev["project"], "proj")
        self.assertNotIn("harness", ev)

    def test_codex_uses_claude_names(self):
        ev, command = client.adapt("codex", {
            "hook_event_name": "PostToolUse", "session_id": "abc", "tool_name": "Bash",
            "tool_input": {"command": "git commit -m x"}, "cwd": "/w/app"})
        self.assertEqual((ev["hook_event_name"], ev["harness"], ev["session_id"]),
                         ("PostToolUse", "codex", "codex-abc"))
        self.assertEqual(client.classify(command), ["commit"])

    def test_command_as_argument_list(self):
        ev, command = client.adapt("codex", {"hook_event_name": "PostToolUse", "tool_name": "shell",
                                             "tool_input": {"command": ["bash", "-lc", "git push"]}})
        self.assertEqual((ev["tool_name"], client.classify(command)), ("Bash", ["push"]))

    def test_copilot_camel_case_events(self):
        ev = adapt("copilot", {"sessionId": "x", "cwd": "/w/p", "toolName": "bash"},
                   event="agentStop")
        self.assertEqual(ev["hook_event_name"], "Stop")
        self.assertEqual(ev["session_id"], "copilot-x")
        ev = adapt("copilot", {"sessionId": "x", "error": {"message": "boom"}}, event="errorOccurred")
        self.assertEqual((ev["hook_event_name"], ev["error_type"]), ("StopFailure", "unknown"))
        self.assertIsNone(adapt("copilot", {"notificationType": "x"}, event="notification"))

    def test_gemini_tool_failure_and_shell(self):
        ev, command = client.adapt("gemini", {
            "hook_event_name": "AfterTool", "session_id": "g", "tool_name": "run_shell_command",
            "tool_input": {"command": "pytest -q"}, "tool_response": {"error": "exit 1"}})
        self.assertEqual((ev["hook_event_name"], ev["tool_name"]), ("PostToolUseFailure", "Bash"))
        self.assertEqual(client.classify(command), ["test"])
        self.assertEqual(adapt("gemini", {"hook_event_name": "AfterAgent"})["hook_event_name"], "Stop")
        self.assertIsNone(adapt("gemini", {"hook_event_name": "AfterModel"}))

    def test_cursor_stop_status_and_workspace(self):
        ev = adapt("cursor", {"hook_event_name": "stop", "status": "error",
                              "conversation_id": "c1", "workspace_roots": ["/w/site"]})
        self.assertEqual((ev["hook_event_name"], ev["project"], ev["session_id"]),
                         ("StopFailure", "site", "cursor-c1"))
        ev = adapt("cursor", {"hook_event_name": "preToolUse", "tool_name": "Shell",
                              "conversation_id": "c1"})
        self.assertEqual(ev["tool_name"], "Bash")

    def test_cursor_running_claude_hooks(self):
        data = {"hook_event_name": "Stop", "session_id": "s", "cursor_version": "2.1"}
        self.assertEqual(adapt("claude", data)["harness"], "cursor")
        # With Cursor's own hooks installed, the copy from the Claude settings is dropped
        self.assertIsNone(adapt("claude", data, cfg={"harnesses": ["cursor"]}))

    def test_devin_run_command(self):
        ev, command = client.adapt("devin", {
            "agent_action_name": "post_run_command", "trajectory_id": "t",
            "tool_info": {"command_line": "git push", "cwd": "/w/api"}})
        self.assertEqual((ev["hook_event_name"], ev["tool_name"], ev["project"]),
                         ("PostToolUse", "Bash", "api"))
        self.assertEqual(client.classify(command), ["push"])


    def test_kiro_old_and_new_names(self):
        ev, command = client.adapt("kiro", {"hook_event_name": "postToolUse", "session_id": "k1",
                                            "cwd": "/w/shop", "tool_name": "execute_bash",
                                            "tool_input": {"command": "pytest -q"}})
        self.assertEqual((ev["hook_event_name"], ev["tool_name"], ev["session_id"], ev["project"]),
                         ("PostToolUse", "Bash", "kiro-k1", "shop"))
        self.assertEqual(client.classify(command), ["test"])
        self.assertEqual(adapt("kiro", {"hook_event_name": "Stop"})["hook_event_name"], "Stop")
        self.assertEqual(adapt("kiro", {"hook_event_name": "agentSpawn"})["hook_event_name"], "SessionStart")

    def test_cline_nested_payload(self):
        ev, command = client.adapt("cline", {
            "hookName": "PostToolUse", "taskId": "t9", "workspaceRoots": ["/w/api"],
            "postToolUse": {"toolName": "execute_command", "parameters": {"command": "git push"},
                            "success": False}})
        self.assertEqual((ev["hook_event_name"], ev["tool_name"], ev["session_id"], ev["project"]),
                         ("PostToolUseFailure", "Bash", "cline-t9", "api"))
        self.assertEqual(client.classify(command), ["push"])
        self.assertEqual(adapt("cline", {"hookName": "TaskComplete", "taskId": "t9"})["hook_event_name"], "Stop")

    def test_opencode_plugin_brings_tokens(self):
        ev = adapt("opencode", {"hook_event_name": "Stop", "session_id": "ses_1", "cwd": "/w/x",
                                "tokens": {"input": 1200, "output": 300, "cache_read": "9000",
                                           "cache_write": None, "evil": 5}})
        self.assertEqual(ev["tokens"], {"input": 1200, "output": 300, "cache_write": 0, "cache_read": 9000})
        self.assertNotIn("tokens", adapt("codex", {"hook_event_name": "Stop", "tokens": {"input": 5}}))

    def test_amp_plugin_events(self):
        ev = adapt("amp", {"hook_event_name": "PostToolUseFailure", "session_id": "T-1", "cwd": "/w/y",
                           "tool_name": "Bash", "is_interrupt": True})
        self.assertEqual((ev["hook_event_name"], ev["session_id"], ev.get("interrupt")),
                         ("PostToolUseFailure", "amp-T-1", True))


class TokenTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.state = os.path.join(self.dir, "food.json")

    def write(self, name, lines, mode="w"):
        path = os.path.join(self.dir, name)
        with open(path, mode) as f:
            for obj in lines:
                f.write(json.dumps(obj) + "\n")
        return path

    def test_claude_counts_each_message_once_and_only_new_ones(self):
        usage = {"input_tokens": 10, "output_tokens": 20, "cache_creation_input_tokens": 30,
                 "cache_read_input_tokens": 1000}
        msg = {"type": "assistant", "message": {"id": "m1", "usage": usage}}
        path = self.write("t.jsonl", [{"type": "user"}, msg, msg])     # same message twice
        first = client.new_tokens("claude", [path], self.state)
        self.assertEqual(first, {"input": 10, "output": 20, "cache_write": 30, "cache_read": 1000})
        self.assertEqual(client.new_tokens("claude", [path], self.state),
                         dict.fromkeys(client.TOKEN_KINDS, 0))
        self.write("t.jsonl", [{"message": {"id": "m2", "usage": {"output_tokens": 5}}}], "a")
        self.assertEqual(client.new_tokens("claude", [path], self.state)["output"], 5)

    def test_claude_waits_for_a_line_still_being_written(self):
        path = os.path.join(self.dir, "t.jsonl")
        with open(path, "w") as f:
            f.write('{"message": {"id": "m1", "usage": {"output_tokens": 7}}}')   # no newline yet
        self.assertEqual(client.new_tokens("claude", [path], self.state)["output"], 0)
        with open(path, "a") as f:
            f.write("\n")
        self.assertEqual(client.new_tokens("claude", [path], self.state)["output"], 7)

    def test_codex_running_total_with_cached_input(self):
        def tc(inp, cached, out):
            return {"type": "event_msg", "payload": {"type": "token_count", "info": {
                "total_token_usage": {"input_tokens": inp, "cached_input_tokens": cached,
                                      "output_tokens": out}}}}
        path = self.write("rollout.jsonl", [tc(100, 40, 10), tc(300, 200, 30)])
        self.assertEqual(client.new_tokens("codex", [path], self.state),
                         {"input": 100, "output": 30, "cache_write": 0, "cache_read": 200})
        self.write("rollout.jsonl", [tc(400, 250, 50)], "a")
        self.assertEqual(client.new_tokens("codex", [path], self.state),
                         {"input": 50, "output": 20, "cache_write": 0, "cache_read": 50})

    def test_gemini_session_file(self):
        path = os.path.join(self.dir, "session.json")
        doc = {"messages": [{"id": "1", "type": "user"},
                            {"id": "2", "type": "gemini", "tokens": {
                                "input": 500, "output": 40, "cached": 300, "thoughts": 10, "tool": 5}}]}
        with open(path, "w") as f:
            json.dump(doc, f)
        self.assertEqual(client.new_tokens("gemini", [path], self.state),
                         {"input": 205, "output": 50, "cache_write": 0, "cache_read": 300})

    def test_missing_log_is_ignored(self):
        self.assertEqual(client.new_tokens("claude", [os.path.join(self.dir, "nope")], self.state),
                         dict.fromkeys(client.TOKEN_KINDS, 0))



class InstallerTest(unittest.TestCase):
    """install.py writes and removes the hooks of every harness without touching others'."""
    def setUp(self):
        self.home = tempfile.mkdtemp()
        self.old_home = os.environ.get("HOME")
        os.environ["HOME"] = self.home
        self.addCleanup(self.restore)
        spec = importlib.util.spec_from_file_location(
            "install", os.path.join(HERE, "..", "..", "client", "install.py"))
        self.inst = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.inst)
        self.cmd = 'sh "{}"'.format(self.inst.LAUNCHER)

    def restore(self):
        if self.old_home is None:
            os.environ.pop("HOME", None)
        else:
            os.environ["HOME"] = self.old_home

    def path(self, rel):
        return os.path.join(self.home, rel)

    def test_kiro_hook_file(self):
        path = self.inst.install_harness("kiro", self.cmd)
        with open(path) as f:
            data = json.load(f)
        self.assertEqual(data["version"], "v1")
        triggers = {h["trigger"]: h for h in data["hooks"]}
        self.assertIn("Stop", triggers)
        self.assertEqual(triggers["PreToolUse"]["matcher"], "*")
        self.assertIn("--harness kiro --event Stop", triggers["Stop"]["action"]["command"])
        self.assertTrue(self.inst.uninstall_harness("kiro"))
        self.assertFalse(os.path.exists(path))

    def test_cline_scripts_leave_foreign_hooks_alone(self):
        hooks = self.path("Documents/Cline/Hooks")
        os.makedirs(hooks)
        with open(os.path.join(hooks, "TaskStart"), "w") as f:
            f.write("#!/bin/sh\necho mine\n")
        self.inst.install_harness("cline", self.cmd)
        with open(os.path.join(hooks, "TaskComplete")) as f:
            self.assertIn("--harness cline --event TaskComplete", f.read())
        self.assertTrue(os.access(os.path.join(hooks, "TaskComplete"), os.X_OK))
        self.assertTrue(self.inst.uninstall_harness("cline"))
        self.assertEqual(os.listdir(hooks), ["TaskStart"])           # the user's own hook stays

    def test_plugins(self):
        for name, rel in (("opencode", ".config/opencode/plugins/tokibot.ts"),
                          ("amp", ".config/amp/plugins/tokibot.ts")):
            path = self.inst.install_harness(name, self.cmd)
            self.assertEqual(path, self.path(rel))
            with open(path) as f:
                text = f.read()
            self.assertIn(json.dumps(self.inst.LAUNCHER.replace(os.sep, "/")), text)
            self.assertIn(f'"--harness", "{name}"', text)
            self.assertNotIn("__LAUNCHER__", text)
            self.assertTrue(self.inst.uninstall_harness(name))
            self.assertFalse(os.path.exists(path))

    def test_auto_finds_the_new_harnesses(self):
        os.makedirs(self.path(".kiro"))
        os.makedirs(self.path(".config/amp"))
        self.assertEqual(self.inst.resolve_harnesses("auto"), ["claude", "kiro", "amp"])


if __name__ == "__main__":
    unittest.main()
