#!/usr/bin/env python3
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

class AzureRuntimeIaCTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.runtime = (ROOT / "infra/azure/runtime.bicep").read_text()
        cls.deploy = (ROOT / "scripts/azure/deploy.sh").read_text()
        cls.bootstrap = (ROOT / "scripts/azure/bootstrap-host.sh").read_text()

    def test_no_public_ip_or_inbound_allow(self):
        self.assertNotIn("publicIPAddresses", self.runtime)
        self.assertIn("No publicIPAddress property", self.runtime)
        self.assertIn("securityRules: []", self.runtime)

    def test_trusted_launch_and_platform_disk_encryption(self):
        for value in ("TrustedLaunch", "encryptionAtHost: true", "secureBootEnabled: true", "vTpmEnabled: true", "StandardSSD_LRS"):
            self.assertIn(value, self.runtime)
        self.assertNotIn("VMGuestStateOnly", self.runtime)

    def test_identity_auth_and_patching(self):
        for value in ("type: 'SystemAssigned'", "disablePasswordAuthentication: true", "patchMode: 'AutomaticByPlatform'", "assessmentMode: 'AutomaticByPlatform'"):
            self.assertIn(value, self.runtime)

    def test_live_feasible_region_and_size_are_locked(self):
        main = (ROOT / "infra/azure/main.bicep").read_text()
        self.assertIn("@allowed(['westus'])", main)
        self.assertIn("param location string = 'westus'", main)
        self.assertIn("vmSize: 'Standard_D2s_v3'", self.runtime)
        self.assertNotIn("centralus", self.deploy)

    def test_durable_operator_public_key(self):
        self.assertIn('$HOME/.ssh/id_ed25519.pub', self.deploy)
        self.assertNotIn("ssh-keygen", self.deploy)
        self.assertNotIn("PRIVATE KEY", self.deploy.upper())
        self.assertIn("--network-access-policy DenyAll", self.deploy)
        self.assertIn("--public-network-access Disabled", self.deploy)

    def test_firewall_and_tailscale_enrollment_order(self):
        self.assertIn('policy drop;', self.bootstrap)
        self.assertIn('iifname "tailscale0" tcp dport { 22, 443 }', self.bootstrap)
        self.assertNotIn("tailscale up", self.bootstrap)
        self.assertIn("tailscale down", self.bootstrap)

    def test_committed_evidence_if_present(self):
        evidence = ROOT / "evidence/issue-10"
        if not evidence.exists():
            return
        azure = json.loads((evidence / "azure-controls.json").read_text())
        host = json.loads((evidence / "host-controls.json").read_text())
        self.assertEqual(azure["vm"]["public_ips"], "")
        self.assertEqual(azure["network"]["public_ip_association_count"], 0)
        self.assertEqual(azure["network"]["custom_inbound_allow_rule_count"], 0)
        self.assertTrue(azure["vm"]["encryption_at_host"])
        self.assertEqual(azure["disk"]["encryption_type"], "EncryptionAtRestWithPlatformKey")
        self.assertEqual(azure["disk"]["network_access_policy"], "DenyAll")
        self.assertEqual(azure["disk"]["public_network_access"], "Disabled")
        self.assertTrue(host["passed"], host["failures"])
        self.assertNotIn("bcfb0381", (evidence / "azure-controls.json").read_text())
        pre = json.loads((evidence / "pre-reboot-host-controls.json").read_text())
        self.assertNotEqual(pre["boot_id"], host["boot_id"])
        feasibility = json.loads((evidence / "feasibility.json").read_text())
        self.assertEqual(feasibility["selected"]["region"], "westus")
        self.assertLess(feasibility["retail_cost_usd"]["baseline_monthly"], feasibility["retail_cost_usd"]["student_credit_assumption_monthly"])

if __name__ == "__main__":
    unittest.main(verbosity=2)
