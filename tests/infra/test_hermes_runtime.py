#!/usr/bin/env python3
import json
import re
import subprocess
import tempfile
import unittest
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[2]
HERMES = ROOT / "infra/hermes"
SCRIPTS = ROOT / "scripts/hermes"


class HermesRuntimeArtifactsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = json.loads((HERMES / "config/profile-config.json.tmpl").read_text())
        cls.install = (SCRIPTS / "install-runtime.sh").read_text()
        cls.runner = (SCRIPTS / "runtime-run.sh").read_text()
        cls.verify = (SCRIPTS / "verify-runtime.sh").read_text()
        cls.units = {p.name: p.read_text() for p in (HERMES / "systemd").iterdir()}

    def test_model_provider_and_profile_home_are_locked(self):
        self.assertEqual(self.config["model"], {"default": "gpt-5.6-sol", "provider": "openai-codex"})
        self.assertEqual(self.config["terminal"]["backend"], "local")
        self.assertEqual(self.config["terminal"]["home_mode"], "profile")
        self.assertEqual(self.config["terminal"]["cwd"], "__WORKSPACE__")
        self.assertTrue(self.config["security"]["redact_secrets"])
        all_runtime = "\n".join([self.install, self.runner, json.dumps(self.config)])
        self.assertNotIn("anthropic", all_runtime.lower())
        self.assertNotIn("fallback", all_runtime.lower())

    def test_config_upgrade_preserves_bot_dashboard_and_channel_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg=Path(tmp)/"config.yaml"
            cfg.write_text(yaml.safe_dump({"model":{"default":"old","custom":"keep"},"dashboard":{"basic_auth":{"password_hash":"opaque","secret":"opaque"}},"gateway":{"platforms":{"telegram":{"extra":{"require_mention":True}}}},"bot_mode":{"title":"Keep Me"}}))
            subprocess.run([str(SCRIPTS/"merge-profile-config.py"),"--config",str(cfg),"--template",str(HERMES/"config/profile-config.json.tmpl"),"--workspace","/workspaces/chief"],check=True)
            merged=yaml.safe_load(cfg.read_text())
            self.assertEqual(merged["model"]["default"],"gpt-5.6-sol"); self.assertEqual(merged["model"]["custom"],"keep")
            self.assertIn("dashboard",merged); self.assertIn("telegram",merged["gateway"]["platforms"]); self.assertEqual(merged["bot_mode"]["title"],"Keep Me")

    def test_manifest_requires_immutable_digest_and_exact_topology(self):
        schema = json.loads((HERMES / "runtime-manifest.schema.json").read_text())
        manifest = json.loads((HERMES / "runtime-manifest.json").read_text())
        self.assertEqual(schema["properties"]["model"]["const"], "gpt-5.6-sol")
        self.assertEqual(schema["properties"]["provider"]["const"], "openai-codex")
        self.assertIn("@sha256:", schema["properties"]["runtime_image"]["pattern"])
        for text in (self.install, self.runner):
            self.assertNotRegex(text, r"(?i)(?:image|container).*(?:latest|:[A-Za-z0-9_.-]+)(?:['\" ]|$)")
        self.assertIn("('bot-chief',8701,'/workspaces/chief')", self.install)
        self.assertIn("('bot-test-worker',8702,'/workspaces/test-worker')", self.install)
        self.assertEqual(manifest["hermes_version"], "0.21.0")
        self.assertEqual(manifest["runtime_image_digest"], "sha256:62b451ba2e2cfcfc834ed35eb4f28a174325b03e8800c97e7ea2e6402b5ef2c9")
        self.assertEqual(manifest["runtime_image_revision"], "f98f5e74e00e54c36088fa2e78171e2a408ba7c9")
        self.assertTrue(manifest["runtime_image"].endswith("@" + manifest["runtime_image_digest"]))

    def test_exact_official_process_commands(self):
        self.assertIn('hermes -p "$bot" gateway run', self.runner)
        self.assertIn('--entrypoint /opt/hermes/.venv/bin/hermes', self.runner)
        self.assertIn('"${common[@]}" -p "$bot" serve --isolated --host 0.0.0.0 --port "$HERMES_SERVE_PORT" --skip-build', self.runner)
        self.assertNotIn("hermes cron daemon", self.runner)
        self.assertIn('scheduler:{owner:"gateway",standalone_cron_service_count:$standalone_cron_count}', self.verify)

    def test_official_image_runs_rootless_with_bot_scoped_mounts(self):
        for token in (
            "--userns=keep-id:uid=1000,gid=1000", "PUID=1000", "PGID=1000",
            "--cap-drop=all", "no-new-privileges", "--pids-limit=512", "--memory=3g",
            '"/var/lib/hermes-bots/$bot/hermes-install:/opt/data:rw,Z"',
            '"/var/lib/hermes-bots/$bot/workspace:$HERMES_WORKSPACE:rw,Z"',
        ):
            self.assertIn(token, self.runner)
        for prohibited in ("docker.sock", "podman.sock", "--privileged", "--network=host", "-v /:/", "--user 0"):
            self.assertNotIn(prohibited, self.runner)

    def test_serve_publication_is_loopback_only(self):
        self.assertIn('127.0.0.1:$HERMES_SERVE_PORT:$HERMES_SERVE_PORT', self.runner)
        self.assertNotIn('0.0.0.0:$HERMES_SERVE_PORT:$HERMES_SERVE_PORT', self.runner)
        self.assertIn("no_api_listener", self.verify)
        schema = json.loads((ROOT / "schemas/evidence/hermes-runtime-evidence.schema.json").read_text())
        self.assertEqual(schema["properties"]["network"]["properties"]["api_8642_listener_count"]["const"], 0)

    def test_systemd_has_distinct_persistent_supervision_and_ordering(self):
        expected = {
            "hermes-gateway@.service", "hermes-serve@.service", "hermes-runtime@.target",
            "hermes-health@.service", "hermes-health@.timer",
        }
        self.assertEqual(set(self.units), expected)
        gateway = self.units["hermes-gateway@.service"]
        serve = self.units["hermes-serve@.service"]
        self.assertIn("Upholds=hermes-serve@%i.service", gateway)
        for unit in (gateway, serve):
            self.assertIn("User=bot-%i", unit)
            self.assertIn("Restart=on-failure", unit)
            self.assertIn("RestartSec=5", unit)
            self.assertIn("newuidmap/newgidmap", unit)
            self.assertIn("MemoryMax=3G", unit)
            self.assertNotIn("ExecStopPost", unit)
        self.assertIn("Wants=hermes-gateway@%i.service", serve)
        self.assertIn("BindsTo=hermes-gateway@%i.service", serve)
        self.assertIn("After=hermes-gateway@%i.service", serve)
        self.assertIn("hermes-fleet-wait-health %i gateway 180", serve)
        timer = self.units["hermes-health@.timer"]
        self.assertIn("Persistent=true", timer)
        self.assertIn("OnBootSec=90s", timer)

    def test_install_never_accepts_or_prints_secret_values(self):
        self.assertNotRegex(self.install, r"--(?:token|secret|password|api-key)")
        self.assertNotIn("cat \"$profile/auth.json\"", self.install)
        self.assertIn("refusing activation: provision supported Bot-scoped credentials", self.install)
        self.assertIn("stat -c %a", self.install)
        collector = (SCRIPTS / "collect-runtime-evidence.sh").read_text()
        for forbidden in ("journalctl", "printenv", "env |", "auth.json", ".env"):
            self.assertNotIn(forbidden, collector)

    def test_crash_and_reboot_tests_have_safety_gates_and_objectives(self):
        crash = (SCRIPTS / "test-crash-recovery.sh").read_text()
        reboot = (SCRIPTS / "test-vm-reboot.sh").read_text()
        self.assertIn("--disposable-fixture", crash)
        self.assertIn("120", crash)
        self.assertIn("--pre-activation-approved", reboot)
        self.assertIn("PRODUCTION_ACTIVATION", reboot)
        self.assertIn("600", reboot)
        self.assertIn("az vm restart", reboot)

    def test_evidence_schema_is_sanitized_and_closed(self):
        schema = json.loads((ROOT / "schemas/evidence/hermes-runtime-evidence.schema.json").read_text())
        self.assertFalse(schema["additionalProperties"])
        bot = schema["$defs"]["bot"]
        self.assertFalse(bot["additionalProperties"])
        serialized = json.dumps(schema).lower()
        for unsafe_field in ("stdout", "stderr", "environment", "token", "cookie", "authorization", "prompt", "message_body"):
            self.assertNotIn(f'"{unsafe_field}"', serialized)
        self.assertEqual(bot["properties"]["gateway_pid_count"]["const"], 1)
        self.assertEqual(bot["properties"]["isolated_serve_pid_count"]["const"], 1)

    def test_all_shell_scripts_parse(self):
        scripts = sorted(SCRIPTS.glob("*.sh"))
        self.assertGreaterEqual(len(scripts), 8)
        for script in scripts:
            result = subprocess.run(["bash", "-n", str(script)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, f"{script}: {result.stderr}")

    def test_runbook_is_honest_about_scope_and_live_facts(self):
        runbook = (ROOT / "docs/runbooks/hermes-runtime.md").read_text()
        self.assertIn("does not deploy browser/noVNC", runbook)
        self.assertIn("not deploy", runbook)
        self.assertIn('"hermes_version": "0.21.0"', runbook)
        self.assertIn("TCP 443 may be `not-configured`", runbook)
        self.assertIn("gateway is the sole ticker", runbook)


if __name__ == "__main__":
    unittest.main(verbosity=2)
