from __future__ import annotations

import ast
import hashlib
import json
import re
import unittest
from collections import Counter
from pathlib import Path

from tools.generate_milestone3_artifacts import (
    doi_hash_fixture_rows,
    generated_documents,
)


ROOT = Path(__file__).resolve().parents[1]
DOI_PACKAGE = ROOT / "src" / "synthetic_sales_assist" / "doi"
DOMAIN_PATTERN = re.compile(
    r"^doi-[a-z][a-z0-9]*(?:[._/-][a-z0-9]+)*/v[1-9][0-9]*$",
    re.ASCII,
)
DIGEST_PATTERN = re.compile(r"^[0-9a-f]{64}$", re.ASCII)
EXPECTED_PROVIDER_COUNTS = {
    "case_attention": 7,
    "extraction": 2,
    "interventions": 17,
    "knowledge": 4,
    "lifecycle": 6,
    "models": 37,
    "retention": 5,
    "source": 16,
}
EXPECTED_KATS = (
    (
        "source",
        "DOIStagedOrder",
        "doi-staged-order/v1",
        "508baca143970fa4c74093eae562c92fcb3e0d010392dbdc256f352eed0c132f",
    ),
    (
        "source",
        "DOIRejectedSourceRecord",
        "doi-rejected-source-record/v1",
        "7617bf31344d188c54eb3eebdc2d76306f8bbb27a4ff72452de812b227d1e310",
    ),
    (
        "source",
        "DOISourceBatch",
        "doi-source-batch/v1",
        "c3a19c767d20b47fbd069ed4e833c1a061d49f4b86e8cbcab0b0203f768a9c38",
    ),
    (
        "source",
        "SourceImportResult",
        "doi-source-import-result/v1",
        "9e5a11e5a0d30f1ccb0592785f1754dff5625cda0d572fda755b8090cac26222",
    ),
    (
        "source",
        "DOIRunWorkItem",
        "doi-run-work-item/v1",
        "41c4961d61c07b07977e00b4ed60b3f6f561aa36e33d2442986a59e69660b891",
    ),
    (
        "source",
        "DOIRunWorkDisposition",
        "doi-run-work-disposition/v1",
        "7cb1c9d13c55b640b971f7ea87d172a138deac5215212411251ec3d4ba40338e",
    ),
    (
        "source",
        "DOIRun",
        "doi-run/v1",
        "7dc903e1e4edf488c1216c3c76226608426605824de921d592190875c31f0cf5",
    ),
    (
        "source",
        "DOIRunEvent",
        "doi-run-event/v1",
        "b7879a0e3602374fb7e70309bad9f85ace295b4a80b60660e956370c5290bab1",
    ),
    (
        "source",
        "DOISourceImportAttempt",
        "doi-source-import-attempt/v1",
        "2e1c309feaa93179a57dbc4724282f9927a2944845a26d35ab4c05baee9a342e",
    ),
    (
        "source",
        "DOISourceImportAttemptEvent",
        "doi-source-import-attempt-event/v1",
        "5c2a3fe3062533d06f4b155364267b81162ae37228ab7c9ee280fc5e6440dca6",
    ),
    (
        "source",
        "FinalizeFailedSourceImportNoRetryCommand",
        "doi-finalize-failed-source-no-retry-command/v1",
        "75b55630987b19e186c1f89306834844848e73d664378841bbc87f2c862713d5",
    ),
    (
        "source",
        "NoRetryCommandReceipt",
        "doi-no-retry-command-receipt/v1",
        "9bb37daf5b6fdf3d295fa5efdb41673843ecfa6cae5feda3820016a0453bf1a7",
    ),
    (
        "source",
        "ExtractionReservationReceipt",
        "doi-extraction-reservation-receipt/v1",
        "794b53de9cf2151c8996ca046636269331dc8aac33a4455991c03d152288758a",
    ),
    (
        "source",
        "PreExtractionRulesUnavailableReceipt",
        "doi-pre-extraction-rules-unavailable-receipt/v1",
        "0aea40c2352b3fdbdc3ee7d9557c6de2ff14b1dfbd7fa2f5e8b2dfc1672964da",
    ),
    (
        "source",
        "SyntheticQueueImageContent",
        "doi-source-image-content/v1",
        "87dafd1cf0e1dcba8a76e345f57742ede3e8ce8e8155e36c86cb8ba986cefdd9",
    ),
    (
        "source",
        "DOISourceBatchIdentity",
        "doi-source-batch-identity/v1",
        "7a5efd40848bfb8ad1aa69a81b265d1d12722c80485340d374e321353c3cd97b",
    ),
    (
        "extraction",
        "CompositeLineContinuityIdentity",
        "doi-line-continuity-composite/v1",
        "fe6c25ba3e1e497ff90c5f52682554fb4fb7a9486c7275f708d866443cd8cba1",
    ),
    (
        "extraction",
        "DOIExtractionAttempt",
        "doi-extraction-attempt/v1",
        "d3b0e825fc98d6f9161f625f51e183ad5ae5896ec959e65dcbe305a91f1dd066",
    ),
    (
        "case_attention",
        "AttentionCauseKey",
        "doi-attention-cause-key/v2",
        "d037fbc8c92c8dc92d39d56bd4d4e1feda6dd5a04bf8cb9a77f250b4ebfe0bbf",
    ),
    (
        "case_attention",
        "AttentionOwnerDecision",
        "doi-attention-owner-decision/v1",
        "22788b547268c78f6f78c1a813cbaadaaf6a2bc6c1a3636d6a6c6b91155be17e",
    ),
    (
        "case_attention",
        "AttentionOwnerEvent",
        "doi-attention-event/v2",
        "e169e7c7ce9036a5f6a4caf59963bc121f12803d8d07530c0f3eebc8d8a01ef1",
    ),
    (
        "case_attention",
        "CaseOwnerDecision",
        "doi-case-owner-decision/v1",
        "9bd38c869cd73dfd94635b4834a7c7dcea043f43dfeaac04334bc4674f54561d",
    ),
    (
        "case_attention",
        "CaseOwnerEvent",
        "doi-case-owner-event/v1",
        "d713de619d4da23ca66451257048698edcc19786e3bd30fe6da89ddb516556f0",
    ),
    (
        "case_attention",
        "DOICaseSourceAdmissionProofV1",
        "doi-case-source-admission-proof/v1",
        "ba1335e38e50eb855af22a9e888ec0b10a0aa6776e5d8e698f620c4da8fd4618",
    ),
    (
        "case_attention",
        "OwnedCaseSourceBinding",
        "doi-case-source-binding/v2",
        "ebce54f8dc3704c79035f81be28cb158655a3b598804da0d5f5d01824547d54f",
    ),
    (
        "models",
        "ActionContextCompletionSource",
        "doi-action-context-completion-source/v1",
        "e4ff679c100b8d6bdbaec34a2c6a612b615ba7dec933557eec9d90439779dbb5",
    ),
    (
        "models",
        "ActionContextOpeningAuthorization",
        "doi-action-context-opening-authorization/v1",
        "62a0deb8ee134194f57c81cde4b3a9d2098d5205a7666a25fbc63d249734d761",
    ),
    (
        "models",
        "ActionContextOpeningRequest",
        "doi-action-context-request/v1",
        "b075c1e84d9b4ce7996619358803597b60e0af66902adf77ba4af6bca261b49a",
    ),
    (
        "models",
        "AlternateCandidate",
        "doi-alternate-candidate/v1",
        "17d4be0c71f06f427fb447293176c739b89ebb24c888ee984441e52078f97e22",
    ),
    (
        "models",
        "ContactWorkflowEvent",
        "doi-contact-state-event/v1",
        "91d429894567c8df204c03629163c4de7c03c358f42aab87e1183e2eef95fedf",
    ),
    (
        "models",
        "ContactWorkflowProjection",
        "doi-contact-state-projection/v1",
        "493f45c6e9acedf76e268d1746c6123404f4c383e3980251c208e8ac8c5fe013",
    ),
    (
        "models",
        "DOIActionContext",
        "doi-action-context/v1",
        "8ca679e9716d0d784a3c6bcc96b5c443b4e165882042a456ab46d3a46bfe3dec",
    ),
    (
        "models",
        "DOIActionContextEvent",
        "doi-action-context-event/v1",
        "ad9ba4069a2f2440c1c927108049a1be656462f38dba6a229cc2c7d0f5a45aba",
    ),
    (
        "models",
        "DOIActionContextObservationLink",
        "doi-action-context-observation-link/v1",
        "08d3e57753682cb57d92bff4d68303ba8c074a1e17e147d233a7c8a587be96b1",
    ),
    (
        "models",
        "DOICaseAdmissionProof",
        "doi-case-admission-proof/v1",
        "be045f07316461213568cb752ea5ade2069ea6583613d9e6a620735e36c4fa5d",
    ),
    (
        "models",
        "DOICaseSourceBinding",
        "doi-case-source-binding/v1",
        "7d7e9168b8f1d47a1523e211a590c360546778e393adec9705b5da184b28d850",
    ),
    (
        "models",
        "DOIContactEvent",
        "doi-contact-event/v1",
        "5c0be67b8f1d089bb8aa3d5928ad4f2c295f5a733717d8da68de16dcd80df16d",
    ),
    (
        "models",
        "DOIContactProjection",
        "doi-contact-projection/v1",
        "5104d89e6ab333723c2359e40412f0262e3e43439c780210f7d5541758db57a5",
    ),
    (
        "models",
        "DOIDedupeEvent",
        "doi-dedupe-event/v1",
        "61e9ff1f9347a1cae25d8c30b55c4f2c688a5ff968663d64af7ba9b2d1af674f",
    ),
    (
        "models",
        "DOIDedupeProjection",
        "doi-dedupe-projection/v1",
        "73aee0f0086d7c2e7c8d0588315f73a8ce49bc7c9a1fc01c0019075af1f406ba",
    ),
    (
        "models",
        "DOIEvaluation",
        "doi-evaluation-record/v1",
        "05c5542cb58512a94e4d96bf6b5014e55533194905d992c73e06f89cdb3b5554",
    ),
    (
        "models",
        "DOIEvaluationInput",
        "doi-evaluation-input/v1",
        "2f796bc1c0a7212669132282ab8069707f7373c7d4e8755bddc40bd1ac48bfa2",
    ),
    (
        "models",
        "DOIEvaluationOutput",
        "doi-evaluation-output/v1",
        "6cd0b137d927b36680be5efad08ab4fddadc9a7e119b9ed13fcff2c3a5ca2e14",
    ),
    (
        "models",
        "DOIExplanation",
        "doi-evaluation-explanation/v1",
        "01db09fc41e21f82342aa7735632f2bea443781e9fe95181f41bfd624d66cb60",
    ),
    (
        "models",
        "DOIHumanFactEvent",
        "doi-human-fact-event/v1",
        "257d9d8f370175ba43df3c0c411e9d5657d831a42156cfd450eece1ee937d2ec",
    ),
    (
        "models",
        "DOIHumanFactProjection",
        "doi-human-fact-projection/v1",
        "c39c19b889d078c184bd9c7c10fe567022ad5dfeca984c489fa4ca87395da69b",
    ),
    (
        "models",
        "DOILineItemSnapshot",
        "doi-line-item-snapshot/v1",
        "7cedaa9c72c6f44566a5c66ff648bb26be97670ad3bb8173a76c11a40d0d628e",
    ),
    (
        "models",
        "DOIMutualExclusionEvidence",
        "doi-mutual-exclusion-evidence/v1",
        "b0ef1f7e8f18acb4a997e5332dec3374add29dd235fb7545abba98e8f8207041",
    ),
    (
        "models",
        "DOIOccurrenceGuard",
        "doi-occurrence-guard/v1",
        "b3cc9a02d5a4975c92d032f5a404559a9bfa69ef50dcb78220f8e0f3dacd176e",
    ),
    (
        "models",
        "DOIOpportunity",
        "doi-opportunity/v1",
        "b1136eb47598439e2e9216c1a7f8f532cfa1713d46402dfb9c31f23cbdad3ce7",
    ),
    (
        "models",
        "DOIOpportunityIdentity",
        "doi-opportunity-id/v1",
        "d35358a7d4a37af5492a097ef576b418a7146af40bc9547478f8f48411c3f67d",
    ),
    (
        "models",
        "DOIOpportunityScope",
        "doi-opportunity-scope/v1",
        "7bdd6d29317aeedaa2d87f018871f6f31431b3adc4f7906edc5614fe8a977ca6",
    ),
    (
        "models",
        "DOIOrderSnapshot",
        "doi-order-snapshot/v1",
        "4484170a2128a43d96cdf133cedad81b4d03453429e07a3cb55da0f0c49acf1a",
    ),
    (
        "models",
        "DOIRulePackBinding",
        "doi-rule-pack-binding/v1",
        "aaa63f608d57bf49a8b5eda4294ef7f32b84aee6fae956b64a4327cc7da13789",
    ),
    (
        "models",
        "DOIWWCEvent",
        "doi-wwc-event/v1",
        "ccdda993af80573ef74b43ef69734ffc49763c2fa96e06557047ae12dbbb739e",
    ),
    (
        "models",
        "DOIWWCProjection",
        "doi-wwc-projection/v1",
        "9916db509224bc6241dc51e60fa2d899c82544824fe8b9499db7edf9136a85ae",
    ),
    (
        "models",
        "DedupeFinding",
        "doi-dedupe-finding/v1",
        "0b23e9bd5349394b2877faef415bc8c50a7500143964625798597cf79098c89c",
    ),
    (
        "models",
        "DedupeVerificationFact",
        "doi-dedupe-verification-fact/v1",
        "be8df7dea1a4a0cc3e8e800286877a889ab9db52e14c0388470a422403fb742f",
    ),
    (
        "models",
        "HumanAuthorityGrant",
        "doi-human-authority-grant/v1",
        "12ec90eb11853e762332b6f943b8aae738b1d8af26f819a5f331d78c10488caf",
    ),
    (
        "models",
        "LineContinuityProof",
        "doi-line-continuity-proof/v1",
        "fb63c07d70bd29fe2b081f3d42d6d0c445a7e17835e1acc01ef1a8feb8f0ad8b",
    ),
    (
        "models",
        "StructuredHumanFact",
        "doi-structured-human-fact/v1",
        "414e1efaba447153fcca47d5bd2be527f0a1d0a48f5efbb5c91a69083730acc1",
    ),
    (
        "models",
        "WWCFinding",
        "doi-wwc-finding/v1",
        "205155bfa56ccc89f854f5a7ac7d33cc17fa7bc40cf284a35770443b4f6672e7",
    ),
    (
        "knowledge",
        "DOIAlternateObservation",
        "doi-alternate-observation/v1",
        "7364495156fdf2e0bdd0703eaf2760c39ca7190707091e70f0f49e68bf4d8d3b",
    ),
    (
        "knowledge",
        "DOIAlternateRelationship",
        "doi-alternate-relationship/v1",
        "48735f8b5e72c24e9b44aa9a162d6ef02671428aa9d9cdf82b280d28e5523f93",
    ),
    (
        "knowledge",
        "DOIAlternateRelationshipRevision",
        "doi-alternate-relationship-revision/v1",
        "ecaa862cf7ff89ef1f42ab36c66a3b59a5b25e16826c9c709f99fa418f496bdb",
    ),
    (
        "knowledge",
        "DOIExactSKUObservation",
        "doi-exact-sku-observation/v1",
        "ad3c5c6985f6231815e1e5d1284332e710f6bd9c2fd42a50da6c8d4dd1a72f8d",
    ),
    (
        "lifecycle",
        "TransitionGuardAuthorityEvidence",
        "doi-transition-guard-authority/v1",
        "1e1408766286dec56779ae789456a87a89fc10a72befb2f37c3c891b39916ae7",
    ),
    (
        "lifecycle",
        "TransitionGuardFacts",
        "doi-transition-guard-facts/v1",
        "1777316431e6df212b063b28072de3d32d7a1a9580daed4d4752d4c1d019ea4f",
    ),
    (
        "lifecycle",
        "TransitionGuardProof",
        "doi-transition-guard-proof/v1",
        "0a6193d2e62407d923ba7a65b8f6cece8a3e54219825e1c97438694f8e745948",
    ),
    (
        "lifecycle",
        "TransitionCommand",
        "doi-transition-command/v1",
        "333df15aa867ffaedc5a83b3fa1b485d0a16f7b98d90d462d25e823663bd90a8",
    ),
    (
        "lifecycle",
        "TransitionEvent",
        "doi-lifecycle-event/v1",
        "9c72f75e6c8b5b59fd761f14710e7c70ad085cf179ec73baa8c98421d33f4a18",
    ),
    (
        "lifecycle",
        "AttentionEvent",
        "doi-attention-event/v1",
        "eb01670d81993ed949101e266ce7ff7c76396fc891447d8014ec2c7b42f5c03f",
    ),
    (
        "interventions",
        "ActionVerificationEvent",
        "doi-action-verification-event/v1",
        "acc8473252ca010d492d79441854ce6b6364d2d660387478d4b3cd82e170cfc5",
    ),
    (
        "interventions",
        "ActionVerificationMaterial",
        "doi-action-verification-material/v1",
        "b017fe0c6083e0157d02f27657c9bb751c6bd34a2bce090e3e187f48040875ff",
    ),
    (
        "interventions",
        "AuthorizedHumanExactValueRecord",
        "doi-authorized-human-exact-value-record/v1",
        "16149709eeedd581d7adcb351b812b6ed6bdbaab9df338f85c847e9a594ab400",
    ),
    (
        "interventions",
        "AuthorizedHumanResultingLinkEvidence",
        "doi-authorized-human-resulting-link-evidence/v1",
        "2b649297c8b0dc2604d5d7291a24b32ac82767e1c98279733b686366a1550fc0",
    ),
    (
        "interventions",
        "DOIIntervention",
        "doi-intervention/v1",
        "2b612f69ade3da3131fb42bb46dbbf3bce5b9877b8946fd23e37f64b42f7764e",
    ),
    (
        "interventions",
        "DOIResultingOrderLink",
        "doi-resulting-order-link/v1",
        "b78f69800927dd7a30b9809147a863fb4bc907303fd644f93b134b22aa1131f8",
    ),
    (
        "interventions",
        "DOIResultingOrderLinkSearch",
        "doi-resulting-order-link-search/v1",
        "217d71dce5288d81d27b61afe470ac12250dbdeace587f764280640602cb9500",
    ),
    (
        "interventions",
        "LogicalEvidenceKey",
        "doi-logical-evidence-key/v1",
        "5731825247b8b7b96b19e4b5ea601758bbf0e8c858341ba36ad925b31c2d66e0",
    ),
    (
        "interventions",
        "ResultingLinkSearchEvent",
        "doi-resulting-link-search-event/v1",
        "0493447868bf2a839bd8f683c08df13bf264b90eba0b60839adee14c4c8ec8bc",
    ),
    (
        "interventions",
        "ResultingLinkSearchEvidence",
        "doi-resulting-link-search-evidence/v1",
        "0e6e1c8ee88dd8c9f4940e42474fbe9265c91cae6bec1464c9367cf28ac7c9cf",
    ),
    (
        "interventions",
        "ResultingOrderLinkRevision",
        "doi-resulting-order-link-revision/v1",
        "d3fea5803855fa73794f90988e6152fc39b0b5e4a3ea9c2fd67df7f164f2e45d",
    ),
    (
        "interventions",
        "SystemExactValueRecord",
        "doi-system-exact-value-record/v1",
        "dd3a9b2602334397f3602b074bd96975dbe41cb6cdf292d136ce3f37c6c1756a",
    ),
    (
        "interventions",
        "SystemResultingLinkEvidence",
        "doi-system-resulting-link-evidence/v1",
        "041a77cde24768af55739e918e0ad307e7e17f05927ded839d9f0945cbcb3dc3",
    ),
    (
        "interventions",
        "TargetRepObservation",
        "doi-target-rep-observation/v1",
        "e866d7aabeaef21336428f5c405ef38a6b23969759ad2624af42d279a873c303",
    ),
    (
        "interventions",
        "TargetRepVerificationProof",
        "doi-target-rep-verification-proof/v1",
        "d9ec0e137fe883455a4d67dc236b0c2e578e7ba06aae4161b749b0f7fa4df559",
    ),
    (
        "interventions",
        "ValueEvent",
        "doi-value-event/v1",
        "8a5b9a46f910160655c3d67d0bc3240d6f407dc44dd854e8b4e9e3d7edab8e66",
    ),
    (
        "interventions",
        "VerificationEvidence",
        "doi-verification-evidence/v1",
        "635906a600e061798d1b8804f7b479c3248c2e61cbcbd8b7d97ac7141b9ad992",
    ),
    (
        "retention",
        "KPIContributionEvent",
        "doi-kpi-contribution-event/v1",
        "cbdecc9843c29639bac1d135edae6ad810aab15778e55027dab91e896571e003",
    ),
    (
        "retention",
        "NonidentifyingKPIBucket",
        "doi-nonidentifying-kpi-bucket/v1",
        "abdfd0a7738ea80af8d8181d19f4657a20b93c9a3140404fc869e4370ec329a6",
    ),
    (
        "retention",
        "PriorClosureRetentionBindingV1",
        "doi-prior-closure-retention-binding/v1",
        "811001092428f0db2b2069457b5197b780a1326afe1414674afab653ad07bf8e",
    ),
    (
        "retention",
        "RetainedKPIContribution",
        "doi-retained-kpi-contribution/v1",
        "d8bd285659a6d531d6e4568a6119b0a3704bf0caec4a72037f3aaa4c7a63e592",
    ),
    (
        "retention",
        "VerifiedCurrencyEnvelope",
        "doi-verified-currency-envelope/v1",
        "177a78b1d98ab7f38f049b3d438a9f60fa1b56010c8ef2da92c91617833f34f5",
    ),
)


def _assigned_name(node: ast.Assign | ast.AnnAssign) -> str | None:
    if isinstance(node, ast.AnnAssign):
        return node.target.id if isinstance(node.target, ast.Name) else None
    if len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
        return node.targets[0].id
    return None


def _doi_owned_hash_domains() -> frozenset[str]:
    domains: set[str] = set()
    for path in sorted(DOI_PACKAGE.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, (ast.Assign, ast.AnnAssign)):
                name = _assigned_name(node)
                value = node.value
                if (
                    name is not None
                    and "DOMAIN" in name
                    and isinstance(value, ast.Constant)
                    and isinstance(value.value, str)
                    and DOMAIN_PATTERN.fullmatch(value.value) is not None
                ):
                    domains.add(value.value)
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "domain_hash"
                and node.args
                and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)
                and DOMAIN_PATTERN.fullmatch(node.args[0].value) is not None
            ):
                domains.add(node.args[0].value)
    return frozenset(domains)


class DOIHashPreimageTests(unittest.TestCase):
    def test_frozen_94_domain_inventory_and_independent_sha256(self) -> None:
        rows = doi_hash_fixture_rows()
        actual = tuple(
            (row.provider, row.name, row.domain, row.digest)
            for row in rows
        )
        self.assertEqual(actual, EXPECTED_KATS)
        self.assertEqual(len(rows), 94)
        self.assertEqual(
            Counter(row.provider for row in rows),
            Counter(EXPECTED_PROVIDER_COUNTS),
        )
        self.assertEqual(rows, doi_hash_fixture_rows())
        self.assertEqual(len({row.name for row in rows}), len(rows))
        self.assertEqual(len({row.domain for row in rows}), len(rows))
        self.assertEqual(len({row.digest for row in rows}), len(rows))

        for row in rows:
            with self.subTest(provider=row.provider, name=row.name):
                self.assertIsNotNone(DOMAIN_PATTERN.fullmatch(row.domain))
                self.assertIsNotNone(DIGEST_PATTERN.fullmatch(row.digest))
                self.assertTrue(row.canonical_bytes.startswith(b"{"))
                self.assertNotIn(b"\n", row.canonical_bytes)
                independently_encoded = json.dumps(
                    json.loads(row.canonical_bytes.decode("utf-8")),
                    ensure_ascii=False,
                    allow_nan=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
                self.assertEqual(independently_encoded, row.canonical_bytes)
                expected_preimage = (
                    row.domain.encode("ascii")
                    + b"\n"
                    + row.canonical_bytes
                )
                self.assertEqual(row.preimage, expected_preimage)
                self.assertEqual(row.preimage.count(b"\n"), 1)
                self.assertEqual(
                    hashlib.sha256(row.preimage).hexdigest(),
                    row.digest,
                )
                for wrong_preimage in (
                    row.domain.encode("ascii") + row.canonical_bytes,
                    row.domain.encode("ascii") + b"\r\n" + row.canonical_bytes,
                    row.domain.encode("ascii") + b"\n\n" + row.canonical_bytes,
                    row.preimage + b"\n",
                ):
                    self.assertNotEqual(
                        hashlib.sha256(wrong_preimage).hexdigest(),
                        row.digest,
                    )

    def test_ast_domain_inventory_has_no_unowned_hash(self) -> None:
        expected_domains = frozenset(row[2] for row in EXPECTED_KATS)
        self.assertEqual(len(expected_domains), 94)
        self.assertEqual(_doi_owned_hash_domains(), expected_domains)

    def test_published_milestone3_documents_have_no_drift(self) -> None:
        documents = generated_documents()
        self.assertEqual(len(documents), 4)
        for path, expected in documents:
            with self.subTest(document=path.name):
                self.assertTrue(path.is_file())
                self.assertEqual(path.read_bytes(), expected.encode("utf-8"))


if __name__ == "__main__":
    unittest.main()
