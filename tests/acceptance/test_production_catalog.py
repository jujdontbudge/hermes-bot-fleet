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
    "locked_source_crosswalk",
}
REQUIRED_REQUIREMENT = {
    "id", "category", "requirement", "prerequisites", "target",
    "command_test_hook", "evidence_artifacts", "pass_criteria",
    "authoritative_evidence",
    "failure_rollback_behavior", "destructive", "secret_risk", "mandatory",
}
PSC_EXTRA_FIELD = "source_target_bot"
REQUIRED_CATEGORIES = {
    "repository", "azure", "network", "services", "gateway-scheduler",
    "telegram", "bot-isolation", "desktop-rooms", "routines", "browser",
    "laptop", "backup-restore", "monitoring", "failure-injection", "runbook",
    "unsupported-gaps", "final-health", "policy-security",
}
EXPECTED_DEFAULTS = {
    "process_recovery_seconds_max": 120,
    "vm_reboot_fleet_health_seconds_max": 600,
    "scheduled_config_backup_age_hours_max": 24,
    "scheduled_config_rpo_hours": 24,
    "browser_consistent_snapshot_age_hours_max": 24,
    "backup_daily_restore_points_min": 7,
    "backup_weekly_restore_points_min": 4,
    "backup_monthly_restore_points_min": 3,
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
LOCKED_SOURCE_CASES = {
    *(f"AUTH-{number:02d}" for number in range(1, 9)),
    *(f"MAC-{number:02d}" for number in range(1, 4)),
    *(f"BROW-{number:02d}" for number in range(1, 4)),
    *(f"SEC-{number:02d}" for number in range(1, 5)),
    *(f"AUD-{number:02d}" for number in range(1, 6)),
    *(f"FAIL-{number:02d}" for number in range(1, 3)),
    "BG-01", "ISO-01", "SCAN-01",
}
LAPTOP_SOURCE_CASES = {"AUTH-02", "MAC-01", "MAC-02", "MAC-03", "BG-01"}
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
    "PSC-029", "PSC-030",
}
ASSERTION_FIELDS = {
    "assertion_id", "observed_field", "operator", "expected", "actual",
    "source_artifact", "passed",
}
ALLOWED_OPERATORS = {
    "eq", "ne", "lt", "lte", "gt", "gte", "in", "not_in", "contains",
    "not_contains", "matches", "exists",
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
        self.assertEqual(self.catalog["schema_version"], "1.1")
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

    def test_every_hook_has_a_typed_structured_assertion_contract(self):
        contract = self.catalog["semantics"]["assertion_row_contract"]
        self.assertEqual(set(contract), {"required_fields", "allowed_operators", "rules"})
        self.assertEqual(set(contract["required_fields"]), ASSERTION_FIELDS)
        self.assertEqual(set(contract["allowed_operators"]), ALLOWED_OPERATORS)
        rules = contract["rules"].lower()
        for phrase in ("every hook", "nonempty assertions array", "exactly the required fields", "source_artifact", "passed", "pass impossible"):
            self.assertIn(phrase, rules)

    def test_requirement_shape_types_and_mandatory_fields(self):
        self.assertGreaterEqual(len(self.requirements), 80)
        for item in self.requirements:
            with self.subTest(item=item.get("id")):
                expected_fields = REQUIRED_REQUIREMENT | ({PSC_EXTRA_FIELD} if item["category"] == "policy-security" else set())
                self.assertEqual(set(item), expected_fields)
                self.assertRegex(item["id"], r"^[A-Z]{3}-\d{3}$")
                for field in ("category", "requirement", "command_test_hook"):
                    self.assertIsInstance(item[field], str)
                    self.assertTrue(item[field].strip())
                self.assertEqual(set(item["target"]), {"environment", "component"})
                self.assertIn(item["target"]["environment"], EXPECTED_TARGETS)
                self.assertTrue(item["target"]["component"].strip())
                self.assertIsInstance(item["prerequisites"], list)
                for field in ("evidence_artifacts", "authoritative_evidence", "pass_criteria", "failure_rollback_behavior"):
                    self.assertIsInstance(item[field], list)
                    self.assertTrue(item[field])
                    self.assertTrue(all(isinstance(x, str) and x.strip() for x in item[field]))
                self.assertIs(type(item["destructive"]), bool)
                self.assertIs(type(item["secret_risk"]), bool)
                self.assertIs(item["mandatory"], True)
                expected_hook = f"acceptance/hooks/run-requirement --id {item['id']} --target {item['target']['environment']}"
                if item["category"] == "policy-security":
                    expected_hook += (
                        f" --source-target-bot {item['source_target_bot']}"
                        " --deployment-identity-digest ${SOURCE_DEPLOYMENT_IDENTITY_DIGEST}"
                        " --data-scope disposable-test-owned"
                    )
                self.assertEqual(item["command_test_hook"], expected_hook)
                self.assertTrue(all(path.startswith("evidence/{run_id}/") for path in item["evidence_artifacts"]))
                if item["destructive"] and item["target"]["environment"] == "live-production":
                    self.assertEqual(item["id"], "SVC-005")

    def test_criteria_are_binary_artifact_bound_and_not_vague(self):
        comparator = re.compile(r"(?:\bequals?\b|==|<=|>=|\bis (?:less|greater) than(?: or equal to)?\b|\bless than or equal to\b|\bgreater than or equal to\b|\bat most\b|\bat least\b|\bzero\b|\bexactly\b|\babsent\b|\bdenied\b|\bfails?\b|\bmatches?\b|\boperator\s+(?:eq|ne|lt|lte|gt|gte|in|not_in|contains|not_contains|matches|exists)\b)", re.I)
        artifact = re.compile(r"evidence/\{run_id\}/")
        vague = re.compile(r"^\s*(?:all\s+)?(?:controls?|checks?|gates?)\s+pass(?:ed)?[.!]?\s*$", re.I)
        forbidden_umbrella = (
            "authoritative result fields",
            "every stated value and threshold equals or satisfies this criterion",
            "criterion itself",
            "this criterion is satisfied",
        )
        for item in self.requirements:
            with self.subTest(item=item["id"]):
                for criterion in item["pass_criteria"]:
                    self.assertRegex(criterion, comparator, "criterion lacks an explicit comparator/operator")
                    self.assertRegex(criterion, artifact, "criterion lacks an artifact reference")
                    criterion_paths = set(re.findall(r"evidence/\{run_id\}/[A-Za-z0-9_/{}/-]+\.(?:json|log|xml)", criterion))
                    self.assertTrue(criterion_paths, "criterion has no concrete artifact path")
                    self.assertTrue(
                        criterion_paths.issubset(set(item["evidence_artifacts"])),
                        f"criterion references undeclared artifact(s): {sorted(criterion_paths - set(item['evidence_artifacts']))}",
                    )
                    self.assertIsNone(vague.fullmatch(criterion))
                    self.assertNotIn("controls pass", criterion.lower())
                    for forbidden in forbidden_umbrella:
                        self.assertNotIn(forbidden, criterion.lower())
                for evidence in item["authoritative_evidence"]:
                    self.assertRegex(evidence, artifact)

    def test_exact_locked_source_crosswalk_and_one_or_more_requirements_per_case(self):
        crosswalk = self.catalog["locked_source_crosswalk"]
        self.assertEqual(set(crosswalk), LOCKED_SOURCE_CASES)
        flattened = []
        for case, requirement_ids in crosswalk.items():
            with self.subTest(case=case):
                self.assertIsInstance(requirement_ids, list)
                self.assertGreaterEqual(len(requirement_ids), 1)
                self.assertEqual(len(requirement_ids), len(set(requirement_ids)))
                for rid in requirement_ids:
                    self.assertIn(rid, self.by_id)
                    requirement = self.by_id[rid]
                    self.assertEqual(requirement["category"], "policy-security")
                    self.assertIn(case, requirement["requirement"])
                    self.assertTrue(requirement["authoritative_evidence"])
                    flattened.append(rid)
        self.assertEqual(len(flattened), len(set(flattened)))
        policy_ids = {item["id"] for item in self.requirements if item["category"] == "policy-security"}
        self.assertEqual(policy_ids, set(flattened))

    def test_every_psc_binds_exact_source_bot_deployment_and_disposable_data(self):
        expected_by_id = {}
        for case, requirement_ids in self.catalog["locked_source_crosswalk"].items():
            bot = "laptop-worker" if case in LAPTOP_SOURCE_CASES else "test-worker"
            for rid in requirement_ids:
                expected_by_id[rid] = bot
        policy_items = [item for item in self.requirements if item["category"] == "policy-security"]
        self.assertEqual(set(expected_by_id), {item["id"] for item in policy_items})
        for item in policy_items:
            with self.subTest(item=item["id"]):
                bot = expected_by_id[item["id"]]
                self.assertEqual(item["source_target_bot"], bot)
                self.assertIn(f"--source-target-bot {bot}", item["command_test_hook"])
                self.assertIn("--deployment-identity-digest ${SOURCE_DEPLOYMENT_IDENTITY_DIGEST}", item["command_test_hook"])
                self.assertIn("--data-scope disposable-test-owned", item["command_test_hook"])
                evidence = " ".join(item["authoritative_evidence"])
                criteria = " ".join(item["pass_criteria"])
                for exact in (f"Exact source Bot {bot} deployed policy gate/runtime identity manifest", "deployment identity digest", "disposable test-owned fixture inventory"):
                    self.assertIn(exact, evidence)
                for exact in (f"source_target_bot equals {bot}", "deployed_gate_runtime_identity_digest equals the expected reviewed source deployment identity digest", "gate_runtime_instance_count equals 1", "test_data_scope equals disposable-test-owned", "production_data_read_count equals 0", "production_data_mutation_count equals 0", "production_credential_count equals 0"):
                    self.assertIn(exact, criteria)

    def test_aud04_and_aud05_have_exact_live_and_disposable_composition(self):
        expected = {
            "AUD-04": {"PSC-022": ("live-production", False), "PSC-029": ("disposable-fixture", True)},
            "AUD-05": {"PSC-023": ("live-production", False), "PSC-030": ("disposable-fixture", True)},
        }
        for case, composition in expected.items():
            self.assertEqual(set(self.catalog["locked_source_crosswalk"][case]), set(composition))
            for rid, (environment, destructive) in composition.items():
                self.assertEqual(self.by_id[rid]["target"]["environment"], environment)
                self.assertIs(self.by_id[rid]["destructive"], destructive)

    def test_reviewer_locked_policy_cases_have_all_exact_adversarial_parts(self):
        expected_terms = {
            "PSC-003": ("consumed_retry_without_fresh_exact_manifest_or_grant_decision", "uncertain_commit_retry_without_fresh_exact_manifest_or_grant_decision", "unchanged_idempotent_retry_without_fresh_exact_manifest_or_grant_decision", "authorized_reconciled_path", "fresh_single_use_grant_present"),
            "PSC-021": ("archive-object digest mutation", "broken previous-checkpoint/cross-checkpoint link", "invalid"),
            "PSC-022": ("400", "collector_rights", "retained_daily_verification_receipt_count", "daily_due_run_count", "retained_monthly_verification_receipt_count", "monthly_due_run_count", "skipped_or_failed_run_alert_count", "telegram alert correlation_id"),
            "PSC-029": ("accelerated", "tampered_object", "wrong/malformed tags", "cleanup_remaining_object_count"),
            "PSC-023": ("real live storage control plane", "immutable_retention_days", "400", "retention_lock_state", "distinct-key", "revoked_key", "affected interval", "old/new root cross-certificate", "unknown_root"),
            "PSC-030": ("signing_key_rotation_executed", "signing_key_revocation_executed", "revoked-key affected interval", "unknown_key_signature_result", "old_root_to_new_root_cross_certificate_result", "new_root_to_old_root_cross_certificate_result", "retired_hmac_key", "missing, malformed, forged", "incomplete-key-set", "extra-key-set", "key_destroyed", "post_cleanup_fixture_key_count"),
        }
        for rid, terms in expected_terms.items():
            text = " ".join(all_strings(self.by_id[rid])).lower()
            for term in terms:
                self.assertIn(term.lower(), text, f"{rid} omits {term}")

    def test_only_exact_svc005_live_destructive_pre_activation_exception(self):
        live_destructive = [item for item in self.requirements if item["destructive"] and item["target"]["environment"] == "live-production"]
        self.assertEqual([item["id"] for item in live_destructive], ["SVC-005"])
        item = self.by_id["SVC-005"]
        text = " ".join(all_strings(item)).lower()
        for phrase in ("actual provisioned", "pre-activation", "azure activity log", "resource id", "production activation"):
            self.assertIn(phrase, text)
        self.assertIn("provisioned-vm-binding.json", " ".join(item["evidence_artifacts"]))

    def test_live_exact_profile_concurrency_and_destructive_equivalent_split(self):
        live = self.by_id["GAT-002"]
        self.assertEqual(live["target"]["environment"], "live-production")
        self.assertIs(live["destructive"], False)
        live_text = " ".join(all_strings(live)).lower()
        for phrase in ("chief", "test-worker", "laptop-worker", "telegram", "desktop", "bounded concurrent", "submitted_count", "accepted_count", "reply_count", "cron ticks execute", "session_write", "memory_write", "restart order", "correlation_id", "commit_receipt", "lost_count", "duplicate_reply_count", "cross_interface_attribution_count", "cross_profile_attribution_count", "db", "wal", "integrity_check", "cleanup"):
            self.assertIn(phrase, live_text)
        fixture = self.by_id["GAT-005"]
        self.assertEqual(fixture["target"]["environment"], "disposable-fixture")
        self.assertIs(fixture["destructive"], True)
        fixture_text = " ".join(all_strings(fixture)).lower()
        for phrase in ("equivalent", "contention", "restart", "schema", "wal", "integrity_check"):
            self.assertIn(phrase, fixture_text)

    def test_live_backup_retention_tiers_and_authorities(self):
        item = self.by_id["BKP-007"]
        self.assertEqual(item["target"]["environment"], "live-production")
        self.assertIs(item["destructive"], False)
        text = " ".join(all_strings(item)).lower()
        for phrase in ("7 daily", "4 weekly", "3 monthly", "chief", "test-worker", "laptop-worker", "r5", "mac-local", "actual_backup_configuration_present", "encryption_at_rest", "inventory_object_count", ".env", "auth.json", "profile-home credentials", "r3 paths", "azure r1/r2 paths", "retention-policy.json", "restore-point-inventory.json", "deletion-authority.json", "laptop-worker-r5.json"):
            self.assertIn(phrase, text)

    def test_psc003_has_three_zero_receipt_denials_then_authorized_reconciliation(self):
        item = self.by_id["PSC-003"]
        criteria = " ".join(item["pass_criteria"])
        for retry in ("consumed_retry", "uncertain_commit_retry", "unchanged_idempotent_retry"):
            self.assertIn(f"{retry}_without_fresh_exact_manifest_or_grant_decision equals DENY", criteria)
            self.assertIn(f"{retry}_receipt_count equals 0", criteria)
        for assertion in ("authorized_reconciled_path preserves original idempotency_key", "authoritative_reconciliation_result equals NO_PRIOR_COMMIT", "fresh_exact_manifest_digest_present equals true", "fresh_single_use_grant_present equals true", "authorized_reconciled_receipt_count equals 1"):
            self.assertIn(assertion, criteria)

    def test_psc022_requires_retained_live_due_observed_receipts_and_alert_correlation(self):
        item = self.by_id["PSC-022"]
        self.assertEqual(item["evidence_artifacts"], ["evidence/{run_id}/policy-security/aud-04-live.json"])
        criteria = " ".join(item["pass_criteria"])
        for assertion in ("retained_daily_verification_receipt_count equals daily_due_run_count", "retained_monthly_verification_receipt_count equals monthly_due_run_count", "real completed live-production run", "skipped_or_failed_run_alert_count equals skipped_or_failed_run_count", "every skipped/failed run correlation_id equals exactly one Telegram alert correlation_id"):
            self.assertIn(assertion, criteria)

    def test_psc023_and_psc030_separate_real_retention_inspection_from_key_execution(self):
        live = self.by_id["PSC-023"]
        fixture = self.by_id["PSC-030"]
        live_criteria = " ".join(live["pass_criteria"])
        for assertion in ("storage_configuration_source equals real live storage control plane", "immutable_retention_days is greater than or equal to 400", "retention_lock_state equals immutable"):
            self.assertIn(assertion, live_criteria)
        fixture_criteria = " ".join(fixture["pass_criteria"])
        for assertion in ("signing_key_rotation_executed and signing_key_revocation_executed each equal true", "revoked_key_new_signature_result and unknown_key_signature_result each equal DENY", "every revoked-key affected interval trust_mark equals REVOKED_OR_UNTRUSTED", "old_root_to_new_root_cross_certificate_result and new_root_to_old_root_cross_certificate_result each equal VALID", "retired_hmac_key_new_signature_result equals DENY"):
            self.assertIn(assertion, fixture_criteria)

    def test_gat002_structurally_declares_concurrent_interface_evidence_and_exact_counts(self):
        item = self.by_id["GAT-002"]
        self.assertIn("evidence/{run_id}/gateway/live-concurrent-interface-bursts.json", item["evidence_artifacts"])
        criteria = " ".join(item["pass_criteria"])
        for assertion in ("each exact live chief, test-worker, and laptop-worker", "bounded concurrent Telegram and Desktop bursts while cron ticks execute", "submitted_count equals accepted_count and accepted_count equals reply_count", "every accepted item and cron tick has exactly one unique correlation_id", "lost_count, duplicate_reply_count, duplicate_commit_count, cross_interface_attribution_count, cross_profile_attribution_count, and unbounded_operation_count each equal 0"):
            self.assertIn(assertion, criteria)

    def test_bkp007_requires_actual_encrypted_inventory_and_exact_secret_exclusions(self):
        item = self.by_id["BKP-007"]
        self.assertIn("evidence/{run_id}/backup/laptop-worker-r5.json", item["evidence_artifacts"])
        criteria = " ".join(item["pass_criteria"])
        for assertion in ("actual_backup_configuration_present equals true", "encryption_at_rest equals enabled", "encryption_key_handle_present equals true", "inventory_object_count is greater than or equal to 1", "inventory_checksum_failure_count equals 0", "inclusion counts for .env, auth.json, profile-home credentials, R3 paths, and Azure R1/R2 paths each equal 0"):
            self.assertIn(assertion, criteria)

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
