#!/usr/bin/env python3
"""Static validator for the canonical production acceptance catalog.

This validates the standard itself. It deliberately does not execute or claim live
production acceptance requirements.
"""

import json
import re
import unittest
from collections import Counter, defaultdict, deque
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
CATALOG_PATH = ROOT / "acceptance" / "production-requirements.json"
DOC_PATH = ROOT / "docs" / "acceptance" / "production-standard.md"

REQUIRED_TOP = {
    "schema_version", "title", "canonical", "semantics", "defaults",
    "target_environments", "execution_order", "requirements",
}
REQUIRED_REQUIREMENT = {
    "id", "category", "requirement", "prerequisites", "target",
    "command_test_hook", "evidence_artifacts", "pass_criteria",
    "failure_rollback_behavior", "destructive", "secret_risk", "mandatory",
}
REQUIRED_CATEGORIES = {
    "repository", "azure", "network", "services", "gateway-scheduler",
    "telegram", "bot-isolation", "desktop-rooms", "routines", "browser",
    "laptop", "backup-restore", "monitoring", "failure-injection", "runbook",
    "unsupported-gaps", "final-health",
}
EXPECTED_DEFAULTS = {
    "process_recovery_seconds_max": 120,
    "vm_reboot_fleet_health_seconds_max": 600,
    "scheduled_config_backup_age_hours_max": 24,
    "scheduled_config_rpo_hours": 24,
    "browser_consistent_snapshot_age_hours_max": 24,
    "alert_delivery_seconds_max": 300,
    "laptop_unavailable_seconds_max": 60,
    "reconnect_reconciliation_seconds_max": 300,
    "takeover_transition_seconds_max": 60,
    "isolated_restore_rto_seconds_max": 14400,
    "evidence_retention_days": 400,
    "evidence_encrypted": True,
    "evidence_contains_secrets": False,
}
EXPECTED_TARGETS = {"clean-environment", "live-production", "disposable-fixture"}
REQUIRED_IDS = {
    "AZR-001", "AZR-003", "AZR-004", "NET-001", "NET-003", "SVC-001",
    "SVC-002", "SVC-005", "GAT-001", "GAT-002", "GAT-004", "TEL-001",
    "TEL-002", "TEL-003", "BOT-001", "BOT-002", "BOT-003", "BOT-004",
    "BOT-005", "BOT-006", "BOT-007", "DSK-001", "DSK-002", "DSK-003",
    "DSK-004", "RTN-001", "RTN-002", "BRW-001", "BRW-002", "BRW-003",
    "BRW-004", "BRW-005", "BRW-006", "BRW-007", "BRW-008", "BRW-009",
    "BRW-010", "LAP-001", "LAP-002", "LAP-003", "LAP-004", "LAP-005",
    "LAP-006", "LAP-007", "LAP-008", "LAP-009", "BKP-001", "BKP-002",
    "BKP-003", "BKP-004", "BKP-005", "MON-001", "MON-002", "MON-003",
    "RUN-001", "GAP-001", "GAP-002", "GAP-003", "HLT-001", "HLT-002",
}
FAILURE_CASES = {
    "gateway kill": {"gateway", "kill"},
    "serve kill": {"serve", "kill"},
    "browser crash": {"browser", "crash"},
    "lease supervisor": {"lease supervisor", "kill"},
    "reverse proxy": {"reverse proxy", "kill"},
    "provider outage": {"provider", "outage"},
    "backup failure": {"backup", "failure"},
    "audit or disk full": {"audit", "disk full"},
    "broker or policy gate": {"broker", "policy gate"},
    "telegram outage": {"telegram", "outage"},
    "mac offline/reconnect": {"mac", "reconnect"},
    "vm reboot": {"vm reboot"},
    "tailscale loss": {"tailscale loss"},
    "takeover race/abandon/reboot": {"takeover", "race", "reboot"},
    "database contention": {"db/wal", "contention"},
    "corrupt restore point": {"restore-point corruption"},
}
SECRET_PATTERNS = {
    "private key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "AWS access key": re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),
    "GitHub token": re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b"),
    "Slack token": re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{20,}\b"),
    "JWT": re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"),
    "Telegram bot token": re.compile(r"\b\d{8,10}:[A-Za-z0-9_-]{30,}\b"),
    "credential URL": re.compile(r"https?://[^\s/:]+:[^\s/@]+@", re.IGNORECASE),
}


def load_catalog() -> dict[str, Any]:
    with CATALOG_PATH.open(encoding="utf-8") as handle:
        return json.load(handle)


def all_strings(value: Any):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for key, item in value.items():
            yield str(key)
            yield from all_strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from all_strings(item)


class ProductionCatalogTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = load_catalog()
        cls.requirements = cls.catalog["requirements"]
        cls.by_id = {item["id"]: item for item in cls.requirements}
        cls.doc = DOC_PATH.read_text(encoding="utf-8")

    def test_top_level_schema_and_exact_defaults(self):
        self.assertEqual(set(self.catalog), REQUIRED_TOP)
        self.assertEqual(self.catalog["schema_version"], "1.0")
        self.assertIs(self.catalog["canonical"], True)
        self.assertEqual(self.catalog["defaults"], EXPECTED_DEFAULTS)
        self.assertEqual(set(self.catalog["target_environments"]), EXPECTED_TARGETS)
        self.assertEqual(
            self.catalog["semantics"]["allowed_results"],
            ["PASS", "FAIL", "BLOCKED", "SKIPPED"],
        )
        release_text = json.dumps(self.catalog["semantics"]).lower()
        self.assertIn("blocked", release_text)
        self.assertIn("skipped", release_text)
        self.assertIn("fail", release_text)

    def test_requirement_shape_types_and_mandatory_fields(self):
        self.assertGreaterEqual(len(self.requirements), 80)
        for item in self.requirements:
            with self.subTest(item=item.get("id")):
                self.assertEqual(set(item), REQUIRED_REQUIREMENT)
                self.assertRegex(item["id"], r"^[A-Z]{3}-\d{3}$")
                for field in ("category", "requirement", "command_test_hook"):
                    self.assertIsInstance(item[field], str)
                    self.assertTrue(item[field].strip())
                self.assertEqual(set(item["target"]), {"environment", "component"})
                self.assertIn(item["target"]["environment"], EXPECTED_TARGETS)
                self.assertTrue(item["target"]["component"].strip())
                self.assertIsInstance(item["prerequisites"], list)
                for field in ("evidence_artifacts", "pass_criteria", "failure_rollback_behavior"):
                    self.assertIsInstance(item[field], list)
                    self.assertTrue(item[field])
                    self.assertTrue(all(isinstance(x, str) and x.strip() for x in item[field]))
                self.assertIs(type(item["destructive"]), bool)
                self.assertIs(type(item["secret_risk"]), bool)
                self.assertIs(item["mandatory"], True)
                self.assertEqual(
                    item["command_test_hook"],
                    f"acceptance/hooks/run-requirement --id {item['id']} --target {item['target']['environment']}",
                )
                self.assertTrue(all(path.startswith("evidence/{run_id}/") for path in item["evidence_artifacts"]))
                if item["destructive"]:
                    self.assertIn(item["target"]["environment"], {"disposable-fixture", "clean-environment"})

    def test_unique_stable_ids_and_complete_execution_order(self):
        ids = [item["id"] for item in self.requirements]
        duplicates = [rid for rid, count in Counter(ids).items() if count > 1]
        self.assertEqual(duplicates, [])
        self.assertTrue(REQUIRED_IDS.issubset(ids), sorted(REQUIRED_IDS - set(ids)))
        self.assertEqual(self.catalog["execution_order"], ids)

    def test_prerequisites_exist_are_prior_and_acyclic(self):
        ids = [item["id"] for item in self.requirements]
        position = {rid: index for index, rid in enumerate(ids)}
        indegree = {rid: 0 for rid in ids}
        edges = defaultdict(list)
        for item in self.requirements:
            self.assertEqual(len(item["prerequisites"]), len(set(item["prerequisites"])))
            for prerequisite in item["prerequisites"]:
                self.assertIn(prerequisite, position, f"unknown prerequisite for {item['id']}")
                self.assertLess(position[prerequisite], position[item["id"]], f"out-of-order prerequisite for {item['id']}")
                edges[prerequisite].append(item["id"])
                indegree[item["id"]] += 1
        queue = deque(rid for rid, degree in indegree.items() if degree == 0)
        visited = 0
        while queue:
            rid = queue.popleft()
            visited += 1
            for successor in edges[rid]:
                indegree[successor] -= 1
                if indegree[successor] == 0:
                    queue.append(successor)
        self.assertEqual(visited, len(ids), "prerequisite graph contains a cycle")

    def test_every_required_category_and_failure_case_is_represented(self):
        categories = {item["category"] for item in self.requirements}
        self.assertEqual(categories, REQUIRED_CATEGORIES)
        failure_texts = [
            " ".join(all_strings(item)).lower()
            for item in self.requirements
            if item["category"] == "failure-injection"
        ]
        self.assertGreaterEqual(len(failure_texts), len(FAILURE_CASES))
        for name, terms in FAILURE_CASES.items():
            self.assertTrue(
                any(all(term in text for term in terms) for text in failure_texts),
                f"missing explicit failure injection: {name}",
            )

    def test_doc_has_exact_catalog_index_coverage(self):
        start_marker = "<!-- CATALOG_INDEX_START -->"
        end_marker = "<!-- CATALOG_INDEX_END -->"
        self.assertEqual(self.doc.count(start_marker), 1)
        self.assertEqual(self.doc.count(end_marker), 1)
        index = self.doc.split(start_marker, 1)[1].split(end_marker, 1)[0]
        documented = re.findall(r"^\| `([A-Z]{3}-\d{3})` \|", index, re.MULTILINE)
        expected = self.catalog["execution_order"]
        self.assertEqual(documented, expected)
        self.assertEqual(len(documented), len(set(documented)))
        for category in REQUIRED_CATEGORIES:
            self.assertIn(f"`{category}`", index)
        for required_phrase in (
            "BLOCKED", "SKIPPED", "Clean environment", "Live production",
            "Disposable fixture", "400 days", "24 hours", "4 hours",
            "RECOVERING", "unsupported", "execution_order",
        ):
            self.assertIn(required_phrase, self.doc)

    def test_no_stale_marker_or_skip_waiver(self):
        stale_marker = "T" + "BD"
        skip_waiver = "skip" + "_allowed"
        texts = {
            str(CATALOG_PATH.relative_to(ROOT)): CATALOG_PATH.read_text(encoding="utf-8"),
            str(DOC_PATH.relative_to(ROOT)): self.doc,
        }
        for path, text in texts.items():
            with self.subTest(path=path):
                self.assertNotIn(stale_marker, text.upper())
                self.assertNotIn(skip_waiver, text.lower())
                self.assertNotRegex(text.lower(), r"mandatory\s*(?:[=:]|is)\s*false")
                self.assertNotRegex(text.lower(), r"skip(?:ped|ping)?\s+(?:is\s+)?(?:permitted|allowed|acceptable|passes)")

    def test_no_secret_shaped_values(self):
        paths = (CATALOG_PATH, DOC_PATH)
        for path in paths:
            text = path.read_text(encoding="utf-8")
            for name, pattern in SECRET_PATTERNS.items():
                self.assertIsNone(pattern.search(text), f"{name} shaped value in {path.relative_to(ROOT)}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
