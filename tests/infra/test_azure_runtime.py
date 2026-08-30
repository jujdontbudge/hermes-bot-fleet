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
        self.assertNotIn("access: 'Allow'", self.runtime)
        self.assertIn("name: 'DenyDirectAdminTcp'", self.runtime)
        self.assertIn("destinationPortRanges: ['22', '443']", self.runtime)

    def test_trusted_launch_and_platform_disk_encryption(self):
        for value in ("TrustedLaunch", "encryptionAtHost: true", "secureBootEnabled: true", "vTpmEnabled: true", "StandardSSD_LRS"):
            self.assertIn(value, self.runtime)
        self.assertNotIn("VMGuestStateOnly", self.runtime)
        main = (ROOT / "infra/azure/main.bicep").read_text()
        self.assertIn("param imageVersion string = '24.04.202608270'", main)
        self.assertNotIn("version: 'latest'", self.runtime)
        self.assertIn('IMAGE_VERSION=${IMAGE_VERSION:-24.04.202608270}', self.deploy)

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

    def test_tailnet_policy_is_default_deny_and_narrow(self):
        policy = (ROOT / "infra/tailscale/policy.hujson").read_text()
        self.assertNotIn('"src": ["*"]', policy)
        self.assertIn('"dst": ["fleet-server"]', policy)
        self.assertIn('"src": ["laptop-worker"]', policy)
        self.assertNotIn('"ip": ["*"]', policy)
        self.assertIn('"ip": ["tcp:22", "tcp:443"]', policy)
        self.assertIn('"proto": "tcp"', policy)
        self.assertIn('"deny": ["fleet-server:22", "fleet-server:443"]', policy)

    def test_committed_evidence_if_present(self):
        evidence = ROOT / "evidence/issue-10"
        if not evidence.exists():
            return
        azure = json.loads((evidence / "azure-controls.json").read_text())
        host = json.loads((evidence / "host-controls.json").read_text())
        self.assertEqual(azure["vm"]["public_ips"], "")
        self.assertEqual(azure["network"]["public_ip_association_count"], 0)
        self.assertEqual(azure["network"]["custom_inbound_allow_rule_count"], 0)
        self.assertEqual(azure["network"]["custom_inbound_admin_deny_rule_count"], 1)
        self.assertEqual(azure["vm"]["image"]["exact_version"], "24.04.202608270")
        self.assertTrue(azure["network"]["vnet_id"].endswith("/virtualNetworks/vnet-hermes-fleet-prod"))
        self.assertTrue(azure["network"]["subnet_id"].endswith("/subnets/snet-runtime"))
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
