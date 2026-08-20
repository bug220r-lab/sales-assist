from __future__ import annotations

import copy
import json
import unittest
from collections.abc import Mapping
from dataclasses import FrozenInstanceError
from pathlib import Path
from typing import cast

import synthetic_sales_assist.domain as domain_package
import synthetic_sales_assist.domain.registries as registry_module
from synthetic_sales_assist.domain.registries import (
    DoiRegistries,
    EXPECTED_OWNERSHIP_COUNT,
    EXPECTED_REASON_COUNT,
    EXPECTED_TRANSITION_COUNT,
    OWNERSHIP_REGISTRY_VERSION,
    REASON_REGISTRY_BASE_VERSION,
    REASON_REGISTRY_VERSION,
    TRANSITION_REGISTRY_VERSION,
    ReasonOwnershipView,
    ReasonRef,
    RegistryLookupError,
    RegistryValidationError,
    TransitionRef,
    load_doi_registries,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def load_supplied_document(name: str) -> dict[str, object]:
    raw = (PROJECT_ROOT / "specs" / "doi" / name).read_text(encoding="utf-8")
    return cast(dict[str, object], json.loads(raw))


def row_by_identity(
    document: dict[str, object], collection: str, identity_key: str, identity: str
) -> dict[str, object]:
    rows = cast(list[dict[str, object]], document[collection])
    return next(row for row in rows if row[identity_key] == identity)


class DoiRegistryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.registries = load_doi_registries()

    def test_closed_inventory_counts_and_versions(self) -> None:
        registries = self.registries
        self.assertEqual(registries.reason_count, EXPECTED_REASON_COUNT)
        self.assertEqual(registries.ownership_count, EXPECTED_OWNERSHIP_COUNT)
        self.assertEqual(registries.transition_count, EXPECTED_TRANSITION_COUNT)
        self.assertEqual(registries.reason_registry_version, REASON_REGISTRY_VERSION)
        self.assertEqual(registries.ownership_registry_version, OWNERSHIP_REGISTRY_VERSION)
        self.assertEqual(registries.transition_registry_version, TRANSITION_REGISTRY_VERSION)
        self.assertEqual((registries.reason_count, registries.ownership_count), (138, 138))
        self.assertEqual(registries.transition_count, 115)

    def test_registry_and_ownership_have_exact_ordered_parity(self) -> None:
        for reason in self.registries.reason_refs:
            ownership = self.registries.ownership_record(reason)
            self.assertEqual(ownership.reason_code, reason.code)
            self.assertEqual(ownership.canonical_label, reason.label)
            transitions = self.registries.ownership_transition_refs(reason)
            self.assertEqual(transitions, ownership.owning_transitions)
            self.assertTrue(
                transitions or self.registries.is_rule_or_boundary_only(reason),
                reason.code,
            )
            for transition in transitions:
                self.assertIs(self.registries.transition_ref(transition.transition_id), transition)

    def test_reason_and_transition_access_is_deterministic_and_immutable(self) -> None:
        first = load_doi_registries()
        second = load_doi_registries()
        self.assertIs(first, second)
        self.assertEqual(first.reason_refs[0].code, "RC-001")
        self.assertEqual(first.reason_refs[-1].code, "RC-138")
        self.assertEqual(len({ref.code for ref in first.reason_refs}), 138)
        self.assertEqual(len({ref.transition_id for ref in first.transition_refs}), 115)
        self.assertIs(first.reason_ref("RC-001"), first.reason_ref("RC-001"))
        self.assertIs(first.transition_ref("TR-045A"), first.transition_ref("TR-045A"))

        reason = first.reason_ref("RC-001")
        with self.assertRaises(FrozenInstanceError):
            reason.code = "RC-002"  # type: ignore[misc]
        record = first.reason_record(reason)
        with self.assertRaises(TypeError):
            record["label"] = "CHANGED"  # type: ignore[index]

        transition = first.transition_record("TR-004")
        branches = cast(tuple[Mapping[str, object], ...], transition["Legal branches"])
        with self.assertRaises(TypeError):
            branches[0]["actor"] = "CHANGED"  # type: ignore[index]

        self.assertEqual(repr(first), "DoiRegistries(<closed>)")

    def test_public_ownership_views_are_typed_sanitized_and_immutable(self) -> None:
        self.assertIs(domain_package.ReasonOwnershipView, ReasonOwnershipView)
        public_fields = {
            "canonical_label",
            "governing_refs",
            "ownership_mode",
            "owning_rule_service_area",
            "owning_transitions",
            "reason_code",
            "registry_version",
            "rule_or_boundary_only",
        }
        for reason in self.registries.reason_refs:
            view = self.registries.ownership_record(reason)
            with self.subTest(reason=reason.code):
                self.assertIsInstance(view, ReasonOwnershipView)
                self.assertEqual(set(type(view).__slots__), public_fields)
                self.assertFalse(hasattr(view, "owning_deterministic_oracles"))
                self.assertFalse(hasattr(view, "oracle_status"))
                self.assertFalse(hasattr(view, "emission_sites"))
                self.assertIsInstance(view.governing_refs, str)
                self.assertIsInstance(view.owning_transitions, tuple)
                with self.assertRaises(FrozenInstanceError):
                    view.ownership_mode = "CHANGED"  # type: ignore[misc]

    def test_registry_and_ownership_view_construction_are_protected(self) -> None:
        with self.assertRaises(RegistryLookupError):
            DoiRegistries()
        with self.assertRaises(RegistryLookupError):
            DoiRegistries._create(
                reason_registry_version=REASON_REGISTRY_VERSION,
                ownership_registry_version=OWNERSHIP_REGISTRY_VERSION,
                transition_registry_version=TRANSITION_REGISTRY_VERSION,
                reason_refs=(),
                transition_refs=(),
                reason_by_code={},
                reason_by_label={},
                transition_by_id={},
                reason_records={},
                ownership_by_code={},
                transition_records={},
            )
        with self.assertRaises(RegistryLookupError):
            ReasonOwnershipView(
                reason_code="RC-001",
                canonical_label="SOURCE_IMPORT_FAILED",
                registry_version=REASON_REGISTRY_VERSION,
                ownership_mode="EMITTED_AND_ASSERTED",
                owning_rule_service_area="source_import",
                governing_refs="closed",
                owning_transitions=(),
                rule_or_boundary_only=True,
            )

    def test_direct_reference_construction_and_unknown_aliases_are_rejected(self) -> None:
        unknown_reason = "RC-" + "999"
        unknown_transition = "TR-" + "999"
        wrong_label = "RULE_VERSION_" + "MISSING"
        wrong_version = REASON_REGISTRY_VERSION + "-other"
        checks = (
            lambda: ReasonRef(unknown_reason, "UNKNOWN", REASON_REGISTRY_VERSION),
            lambda: TransitionRef(unknown_transition, TRANSITION_REGISTRY_VERSION),
            lambda: self.registries.reason_ref(unknown_reason),
            lambda: self.registries.reason_ref("rc-084"),
            lambda: self.registries.reason_ref("RC-084", expected_label=wrong_label),
            lambda: self.registries.reason_ref(
                "RC-084", expected_registry_version=wrong_version
            ),
            lambda: self.registries.transition_ref(unknown_transition),
            lambda: self.registries.transition_ref(
                "TR-004", expected_registry_version=wrong_version
            ),
        )
        for check in checks:
            with self.subTest(check=checks.index(check)):
                with self.assertRaises(RegistryLookupError) as caught:
                    check()
                rendered = str(caught.exception)
                self.assertEqual(rendered, "DOI registry reference rejected")
                self.assertNotIn(unknown_reason, rendered)
                self.assertNotIn(unknown_transition, rendered)
                self.assertNotIn(wrong_label, rendered)
                self.assertNotIn(wrong_version, rendered)

    def test_canonical_label_and_version_resolution(self) -> None:
        reason = self.registries.reason_ref(
            "RC-084",
            expected_label="RULE_VERSION_UNAVAILABLE",
            expected_registry_version=REASON_REGISTRY_VERSION,
        )
        self.assertIs(
            reason,
            self.registries.reason_ref_by_label(
                "RULE_VERSION_UNAVAILABLE",
                expected_registry_version=REASON_REGISTRY_VERSION,
            ),
        )
        transition = self.registries.transition_ref(
            "TR-004",
            expected_registry_version=TRANSITION_REGISTRY_VERSION,
        )
        self.assertEqual(transition.transition_id, "TR-004")

    def test_ownership_version_bindings_are_exact(self) -> None:
        versions = [
            self.registries.ownership_record(reason).registry_version
            for reason in self.registries.reason_refs
        ]
        self.assertEqual(versions.count(REASON_REGISTRY_BASE_VERSION), 137)
        self.assertEqual(versions.count(REASON_REGISTRY_VERSION), 1)
        self.assertEqual(
            self.registries.ownership_record("RC-084").registry_version,
            REASON_REGISTRY_VERSION,
        )

    def test_rc084_has_one_identity_and_all_three_closed_owners(self) -> None:
        reason = self.registries.reason_ref("RC-084")
        self.assertEqual(reason.label, "RULE_VERSION_UNAVAILABLE")
        self.assertEqual(
            tuple(
                ref.transition_id
                for ref in self.registries.ownership_transition_refs(reason)
            ),
            ("TR-004", "TR-027", "TR-037"),
        )

        reason_record = self.registries.reason_record(reason)
        sites = cast(tuple[object, ...], reason_record["emission_sites"])
        self.assertEqual(len(sites), 2)
        site_records = tuple(cast(Mapping[str, object], site) for site in sites)
        self.assertEqual(
            {site["site"] for site in site_records},
            {
                "DOIEvaluation rules-version gate",
                "DOIRun pre-extraction systemic rules gate",
            },
        )
        run_site = next(
            site
            for site in site_records
            if site["site"] == "DOIRun pre-extraction systemic rules gate"
        )
        self.assertEqual(run_site["transition_branch"], "PRE_EXTRACTION_RULES_UNAVAILABLE")
        self.assertEqual(run_site["transitions"], ("TR-004",))

    def test_tr004_contains_exact_two_closed_reconciled_branches(self) -> None:
        record = self.registries.transition_record("TR-004")
        branches = tuple(
            cast(Mapping[str, object], branch)
            for branch in cast(tuple[object, ...], record["Legal branches"])
        )
        self.assertEqual(
            tuple(branch["branch_id"] for branch in branches),
            (
                "SOURCE_IMPORT_FAILED_EXPLICIT_NO_RETRY",
                "PRE_EXTRACTION_RULES_UNAVAILABLE",
            ),
        )
        explicit = branches[0]
        systemic = branches[1]
        self.assertEqual(
            explicit["terminal_trigger"],
            "FINALIZE_FAILED_SOURCE_IMPORT_NO_RETRY",
        )
        self.assertEqual(systemic["reason_set"], ("RC-084",))
        self.assertEqual(systemic["actor"], "SYSTEM_RULES_GATE")
        forbidden = cast(tuple[object, ...], record["Forbidden interpretations"])
        self.assertIn("Absence of a retry command", forbidden)
        self.assertIn("Mere passage of time", forbidden)

    def test_tr100_terminalizes_only_attempt_and_never_on_absence(self) -> None:
        record = self.registries.transition_record("TR-100")
        effects = cast(str, record["Required effects"])
        self.assertIn("terminalizes only the current attempt", effects)
        self.assertIn("parent run remains IN_PROGRESS indefinitely", effects)
        self.assertIn("Absence of either command is not an event", effects)
        self.assertIn("never terminalizes the run", effects)


class DoiRegistryClosedSchemaTests(unittest.TestCase):
    def setUp(self) -> None:
        self.reason_document = load_supplied_document("reason_registry.json")
        self.ownership_document = load_supplied_document("reason_ownership.json")
        self.transition_document = load_supplied_document("state_transitions.json")

    def assertValidationRejected(
        self,
        validator: object,
        document: dict[str, object],
    ) -> None:
        with self.assertRaises(RegistryValidationError):
            cast(object, validator)(document)  # type: ignore[operator]

    def test_every_distinct_row_shape_rejects_extra_and_missing_members(self) -> None:
        cases = (
            (self.reason_document, "reasons", registry_module._validate_reason_rows),
            (self.ownership_document, "rows", registry_module._validate_ownership_rows),
            (
                self.transition_document,
                "transitions",
                registry_module._validate_transition_rows,
            ),
        )
        expected_shape_counts = {"reasons": 2, "rows": 3, "transitions": 4}
        for document, collection, validator in cases:
            rows = cast(list[dict[str, object]], document[collection])
            examples: dict[frozenset[str], int] = {}
            for index, row in enumerate(rows):
                examples.setdefault(frozenset(row), index)
            self.assertEqual(len(examples), expected_shape_counts[collection])
            for index in examples.values():
                with self.subTest(collection=collection, mutation="extra", row=index):
                    mutant = copy.deepcopy(document)
                    mutant_rows = cast(list[dict[str, object]], mutant[collection])
                    mutant_rows[index]["unexpected_member"] = "UNEXPECTED"
                    self.assertValidationRejected(validator, mutant)

                with self.subTest(collection=collection, mutation="missing", row=index):
                    mutant = copy.deepcopy(document)
                    mutant_rows = cast(list[dict[str, object]], mutant[collection])
                    if collection == "transitions":
                        mutant_rows[index].pop("section")
                    elif collection == "reasons":
                        mutant_rows[index].pop("description")
                    else:
                        mutant_rows[index].pop("governing_refs")
                    self.assertValidationRejected(validator, mutant)

    def test_top_level_and_nested_metadata_are_closed(self) -> None:
        cases = (
            (self.reason_document, registry_module._validate_reason_rows),
            (self.ownership_document, registry_module._validate_ownership_rows),
            (self.transition_document, registry_module._validate_transition_rows),
        )
        for document, validator in cases:
            with self.subTest(validator=validator.__name__, mutation="top_extra"):
                mutant = copy.deepcopy(document)
                mutant["unexpected_member"] = "UNEXPECTED"
                self.assertValidationRejected(validator, mutant)

        reason = copy.deepcopy(self.reason_document)
        lineage = cast(dict[str, object], reason["source_lineage"])
        lineage["unexpected_member"] = 1
        self.assertValidationRejected(registry_module._validate_reason_rows, reason)

        transition = copy.deepcopy(self.transition_document)
        reconciliation = cast(dict[str, object], transition["reconciliation"])
        reconciliation["unexpected_member"] = "UNEXPECTED"
        self.assertValidationRejected(registry_module._validate_transition_rows, transition)

    def test_rc084_reason_emission_sites_are_recursively_closed(self) -> None:
        mutations: tuple[tuple[str, object], ...] = (
            ("extra", "UNEXPECTED"),
            ("transitions", "TR-027"),
            ("site", "wrong"),
        )
        for key, value in mutations:
            with self.subTest(key=key):
                mutant = copy.deepcopy(self.reason_document)
                row = row_by_identity(mutant, "reasons", "reason_id", "RC-084")
                sites = cast(list[dict[str, object]], row["emission_sites"])
                sites[0][key] = value
                self.assertValidationRejected(registry_module._validate_reason_rows, mutant)

        mutant = copy.deepcopy(self.reason_document)
        row = row_by_identity(mutant, "reasons", "reason_id", "RC-084")
        sites = cast(list[dict[str, object]], row["emission_sites"])
        sites[1].pop("transition_branch")
        self.assertValidationRejected(registry_module._validate_reason_rows, mutant)

    def test_rc084_ownership_emission_sites_are_recursively_closed(self) -> None:
        mutant = copy.deepcopy(self.ownership_document)
        row = row_by_identity(mutant, "rows", "reason_code", "RC-084")
        sites = cast(list[dict[str, object]], row["emission_sites"])
        sites[0]["unexpected_member"] = "UNEXPECTED"
        self.assertValidationRejected(registry_module._validate_ownership_rows, mutant)

        mutant = copy.deepcopy(self.ownership_document)
        row = row_by_identity(mutant, "rows", "reason_code", "RC-084")
        sites = cast(list[dict[str, object]], row["emission_sites"])
        sites[1]["transitions"] = ["TR-005"]
        self.assertValidationRejected(registry_module._validate_ownership_rows, mutant)

        mutant = copy.deepcopy(self.ownership_document)
        row = row_by_identity(mutant, "rows", "reason_code", "RC-084")
        row.pop("oracle_status")
        self.assertValidationRejected(registry_module._validate_ownership_rows, mutant)

    def test_tr004_nested_branches_and_forbidden_list_are_closed(self) -> None:
        mutant = copy.deepcopy(self.transition_document)
        row = row_by_identity(mutant, "transitions", "Transition", "TR-004")
        row["Legal branches"] = {"unexpected": "shape"}
        self.assertValidationRejected(registry_module._validate_transition_rows, mutant)

        mutant = copy.deepcopy(self.transition_document)
        row = row_by_identity(mutant, "transitions", "Transition", "TR-004")
        branches = cast(list[dict[str, object]], row["Legal branches"])
        branches[0]["unexpected_member"] = "UNEXPECTED"
        self.assertValidationRejected(registry_module._validate_transition_rows, mutant)

        mutant = copy.deepcopy(self.transition_document)
        row = row_by_identity(mutant, "transitions", "Transition", "TR-004")
        branches = cast(list[dict[str, object]], row["Legal branches"])
        branches[1]["reason_set"] = ["RC-083"]
        self.assertValidationRejected(registry_module._validate_transition_rows, mutant)

        mutant = copy.deepcopy(self.transition_document)
        row = row_by_identity(mutant, "transitions", "Transition", "TR-004")
        row["Forbidden interpretations"] = 42
        self.assertValidationRejected(registry_module._validate_transition_rows, mutant)

    def test_tr100_protected_parent_run_semantics_are_validated(self) -> None:
        mutant = copy.deepcopy(self.transition_document)
        row = row_by_identity(mutant, "transitions", "Transition", "TR-100")
        effects = cast(str, row["Required effects"])
        row["Required effects"] = effects.replace(
            "terminalizes only the current attempt", "changes the current attempt"
        )
        self.assertValidationRejected(registry_module._validate_transition_rows, mutant)


if __name__ == "__main__":
    unittest.main()
