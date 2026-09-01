#!/usr/bin/env python3
import importlib.util, json, re, tempfile, unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]

class ControlPlaneArtifactsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest=json.loads((ROOT/"infra/control/fleet-control.json").read_text())
        cls.runtime=json.loads((ROOT/"infra/hermes/runtime-manifest.json").read_text())
        cls.runner=(ROOT/"scripts/hermes/runtime-run.sh").read_text()
        cls.installer=(ROOT/"scripts/hermes/install-runtime.sh").read_text()

    def test_exact_bot_ownership_model_and_runtime_projection(self):
        self.assertEqual(set(self.manifest["bots"]),{"chief","test-worker","laptop-worker"})
        self.assertEqual((self.manifest["provider"],self.manifest["model"]),("openai-codex","gpt-5.6-sol"))
        self.assertNotIn("anthropic",json.dumps(self.manifest).lower())
        for name,bot in self.manifest["bots"].items(): self.assertTrue(bot["credential_handle"].startswith(f"secret://{name}/"))
        self.assertEqual(self.manifest["bots"]["laptop-worker"]["runtime"],"mac-laptop"); self.assertIsNone(self.manifest["bots"]["laptop-worker"]["browser_profile"])

    def test_room_channel_and_routine_contract(self):
        room=self.manifest["room"]; self.assertEqual(room["members"],["chief","test-worker","laptop-worker"]); self.assertEqual(room["max_rounds"],3)
        tg=self.manifest["channels"]["telegram"]; self.assertTrue(tg["polling_only"] and tg["unique_token_per_profile"] and tg["pairing_or_numeric_allowlist_required"]); self.assertFalse(tg["public_listener"])
        self.assertTrue(all(job["deliver"]=="bot-chat" for job in self.manifest["routines"].values()))

    def test_v021_is_pinned_by_digest_and_revision(self):
        self.assertEqual(self.runtime["hermes_version"],"0.21.0"); self.assertRegex(self.runtime["runtime_image"],r"@sha256:[0-9a-f]{64}$"); self.assertRegex(self.runtime["runtime_image_revision"],r"^[0-9a-f]{40}$")
        self.assertEqual(self.manifest["desktop_release_commit"],"29112bef099274229cadff79cdff7bf7b99c4b77")

    def test_upgrade_merge_and_image_verification_are_non_destructive(self):
        self.assertIn("hermes-fleet-merge-config",self.installer); self.assertNotIn("sed \"s|__WORKSPACE__",self.installer)
        self.assertIn("RepoDigests",self.installer); self.assertIn("HERMES_IMAGE_REVISION",(ROOT/"scripts/hermes/runtime-preflight.sh").read_text())

    def test_relay_override_uses_fixed_shape_non_eval_waiter(self):
        relay_path=ROOT/"infra/hermes/overrides/tools/bot_relay.py"; waiter=(ROOT/"infra/hermes/overrides/tools/bot_relay_waiter.py").read_text()
        spec=importlib.util.spec_from_file_location("fleet_bot_relay",relay_path)
        assert spec is not None and spec.loader is not None
        module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        command=module.waiter_command("/opt/data",{"id":"a"*32,"target_handle":"test-worker","target_connection":"fleet-test-worker"})
        self.assertNotIn(" -c ",command); self.assertIn("bot_relay_waiter.py",command); self.assertIn("--reply",command); self.assertIn("reply path denied",waiter)
        self.assertIn("/opt/hermes/tools/bot_relay.py:ro",self.runner); self.assertIn("/opt/hermes/tools/bot_relay_waiter.py:ro",self.runner)

    def test_secret_capture_and_rpc_clients_never_print_auth_material(self):
        capture=(ROOT/"scripts/control/capture-telegram-token.sh").read_text(); rpc=(ROOT/"scripts/control/desktop_rpc.py").read_text()
        self.assertIn("read -r -s token",capture); self.assertIn("chmod 0600",capture); self.assertNotIn("echo $token",capture)
        self.assertIn("secret-shaped RPC response rejected",rpc); self.assertNotIn("print(password",rpc)

if __name__=="__main__": unittest.main(verbosity=2)
