# Milestone 3 DOI hash preimages

Generated from the complete DOI hash-fixture provider inventory. Each preimage is
the ASCII domain, exactly one `0A` byte, and the UTF-8 canonical JSON shown below.
There is no trailing line feed in the hashed preimage. Executable tests pin every
fixture name, domain, digest, canonical encoding, and published byte.

- Hash domains: 94
- Fixture names: 94
- Distinct fixed digests: 94

| Provider | Binding fixture | Domain | Expected SHA-256 |
|---|---|---|---|
| `source` | `DOIStagedOrder` | `doi-staged-order/v1` | `508baca143970fa4c74093eae562c92fcb3e0d010392dbdc256f352eed0c132f` |
| `source` | `DOIRejectedSourceRecord` | `doi-rejected-source-record/v1` | `7617bf31344d188c54eb3eebdc2d76306f8bbb27a4ff72452de812b227d1e310` |
| `source` | `DOISourceBatch` | `doi-source-batch/v1` | `c3a19c767d20b47fbd069ed4e833c1a061d49f4b86e8cbcab0b0203f768a9c38` |
| `source` | `SourceImportResult` | `doi-source-import-result/v1` | `9e5a11e5a0d30f1ccb0592785f1754dff5625cda0d572fda755b8090cac26222` |
| `source` | `DOIRunWorkItem` | `doi-run-work-item/v1` | `41c4961d61c07b07977e00b4ed60b3f6f561aa36e33d2442986a59e69660b891` |
| `source` | `DOIRunWorkDisposition` | `doi-run-work-disposition/v1` | `7cb1c9d13c55b640b971f7ea87d172a138deac5215212411251ec3d4ba40338e` |
| `source` | `DOIRun` | `doi-run/v1` | `7dc903e1e4edf488c1216c3c76226608426605824de921d592190875c31f0cf5` |
| `source` | `DOIRunEvent` | `doi-run-event/v1` | `b7879a0e3602374fb7e70309bad9f85ace295b4a80b60660e956370c5290bab1` |
| `source` | `DOISourceImportAttempt` | `doi-source-import-attempt/v1` | `2e1c309feaa93179a57dbc4724282f9927a2944845a26d35ab4c05baee9a342e` |
| `source` | `DOISourceImportAttemptEvent` | `doi-source-import-attempt-event/v1` | `5c2a3fe3062533d06f4b155364267b81162ae37228ab7c9ee280fc5e6440dca6` |
| `source` | `FinalizeFailedSourceImportNoRetryCommand` | `doi-finalize-failed-source-no-retry-command/v1` | `75b55630987b19e186c1f89306834844848e73d664378841bbc87f2c862713d5` |
| `source` | `NoRetryCommandReceipt` | `doi-no-retry-command-receipt/v1` | `9bb37daf5b6fdf3d295fa5efdb41673843ecfa6cae5feda3820016a0453bf1a7` |
| `source` | `ExtractionReservationReceipt` | `doi-extraction-reservation-receipt/v1` | `794b53de9cf2151c8996ca046636269331dc8aac33a4455991c03d152288758a` |
| `source` | `PreExtractionRulesUnavailableReceipt` | `doi-pre-extraction-rules-unavailable-receipt/v1` | `0aea40c2352b3fdbdc3ee7d9557c6de2ff14b1dfbd7fa2f5e8b2dfc1672964da` |
| `source` | `SyntheticQueueImageContent` | `doi-source-image-content/v1` | `87dafd1cf0e1dcba8a76e345f57742ede3e8ce8e8155e36c86cb8ba986cefdd9` |
| `source` | `DOISourceBatchIdentity` | `doi-source-batch-identity/v1` | `7a5efd40848bfb8ad1aa69a81b265d1d12722c80485340d374e321353c3cd97b` |
| `extraction` | `CompositeLineContinuityIdentity` | `doi-line-continuity-composite/v1` | `fe6c25ba3e1e497ff90c5f52682554fb4fb7a9486c7275f708d866443cd8cba1` |
| `extraction` | `DOIExtractionAttempt` | `doi-extraction-attempt/v1` | `d3b0e825fc98d6f9161f625f51e183ad5ae5896ec959e65dcbe305a91f1dd066` |
| `case_attention` | `AttentionCauseKey` | `doi-attention-cause-key/v2` | `d037fbc8c92c8dc92d39d56bd4d4e1feda6dd5a04bf8cb9a77f250b4ebfe0bbf` |
| `case_attention` | `AttentionOwnerDecision` | `doi-attention-owner-decision/v1` | `22788b547268c78f6f78c1a813cbaadaaf6a2bc6c1a3636d6a6c6b91155be17e` |
| `case_attention` | `AttentionOwnerEvent` | `doi-attention-event/v2` | `e169e7c7ce9036a5f6a4caf59963bc121f12803d8d07530c0f3eebc8d8a01ef1` |
| `case_attention` | `CaseOwnerDecision` | `doi-case-owner-decision/v1` | `9bd38c869cd73dfd94635b4834a7c7dcea043f43dfeaac04334bc4674f54561d` |
| `case_attention` | `CaseOwnerEvent` | `doi-case-owner-event/v1` | `d713de619d4da23ca66451257048698edcc19786e3bd30fe6da89ddb516556f0` |
| `case_attention` | `DOICaseSourceAdmissionProofV1` | `doi-case-source-admission-proof/v1` | `ba1335e38e50eb855af22a9e888ec0b10a0aa6776e5d8e698f620c4da8fd4618` |
| `case_attention` | `OwnedCaseSourceBinding` | `doi-case-source-binding/v2` | `ebce54f8dc3704c79035f81be28cb158655a3b598804da0d5f5d01824547d54f` |
| `models` | `ActionContextCompletionSource` | `doi-action-context-completion-source/v1` | `e4ff679c100b8d6bdbaec34a2c6a612b615ba7dec933557eec9d90439779dbb5` |
| `models` | `ActionContextOpeningAuthorization` | `doi-action-context-opening-authorization/v1` | `62a0deb8ee134194f57c81cde4b3a9d2098d5205a7666a25fbc63d249734d761` |
| `models` | `ActionContextOpeningRequest` | `doi-action-context-request/v1` | `b075c1e84d9b4ce7996619358803597b60e0af66902adf77ba4af6bca261b49a` |
| `models` | `AlternateCandidate` | `doi-alternate-candidate/v1` | `17d4be0c71f06f427fb447293176c739b89ebb24c888ee984441e52078f97e22` |
| `models` | `ContactWorkflowEvent` | `doi-contact-state-event/v1` | `91d429894567c8df204c03629163c4de7c03c358f42aab87e1183e2eef95fedf` |
| `models` | `ContactWorkflowProjection` | `doi-contact-state-projection/v1` | `493f45c6e9acedf76e268d1746c6123404f4c383e3980251c208e8ac8c5fe013` |
| `models` | `DOIActionContext` | `doi-action-context/v1` | `8ca679e9716d0d784a3c6bcc96b5c443b4e165882042a456ab46d3a46bfe3dec` |
| `models` | `DOIActionContextEvent` | `doi-action-context-event/v1` | `ad9ba4069a2f2440c1c927108049a1be656462f38dba6a229cc2c7d0f5a45aba` |
| `models` | `DOIActionContextObservationLink` | `doi-action-context-observation-link/v1` | `08d3e57753682cb57d92bff4d68303ba8c074a1e17e147d233a7c8a587be96b1` |
| `models` | `DOICaseAdmissionProof` | `doi-case-admission-proof/v1` | `be045f07316461213568cb752ea5ade2069ea6583613d9e6a620735e36c4fa5d` |
| `models` | `DOICaseSourceBinding` | `doi-case-source-binding/v1` | `7d7e9168b8f1d47a1523e211a590c360546778e393adec9705b5da184b28d850` |
| `models` | `DOIContactEvent` | `doi-contact-event/v1` | `5c0be67b8f1d089bb8aa3d5928ad4f2c295f5a733717d8da68de16dcd80df16d` |
| `models` | `DOIContactProjection` | `doi-contact-projection/v1` | `5104d89e6ab333723c2359e40412f0262e3e43439c780210f7d5541758db57a5` |
| `models` | `DOIDedupeEvent` | `doi-dedupe-event/v1` | `61e9ff1f9347a1cae25d8c30b55c4f2c688a5ff968663d64af7ba9b2d1af674f` |
| `models` | `DOIDedupeProjection` | `doi-dedupe-projection/v1` | `73aee0f0086d7c2e7c8d0588315f73a8ce49bc7c9a1fc01c0019075af1f406ba` |
| `models` | `DOIEvaluation` | `doi-evaluation-record/v1` | `05c5542cb58512a94e4d96bf6b5014e55533194905d992c73e06f89cdb3b5554` |
| `models` | `DOIEvaluationInput` | `doi-evaluation-input/v1` | `2f796bc1c0a7212669132282ab8069707f7373c7d4e8755bddc40bd1ac48bfa2` |
| `models` | `DOIEvaluationOutput` | `doi-evaluation-output/v1` | `6cd0b137d927b36680be5efad08ab4fddadc9a7e119b9ed13fcff2c3a5ca2e14` |
| `models` | `DOIExplanation` | `doi-evaluation-explanation/v1` | `01db09fc41e21f82342aa7735632f2bea443781e9fe95181f41bfd624d66cb60` |
| `models` | `DOIHumanFactEvent` | `doi-human-fact-event/v1` | `257d9d8f370175ba43df3c0c411e9d5657d831a42156cfd450eece1ee937d2ec` |
| `models` | `DOIHumanFactProjection` | `doi-human-fact-projection/v1` | `c39c19b889d078c184bd9c7c10fe567022ad5dfeca984c489fa4ca87395da69b` |
| `models` | `DOILineItemSnapshot` | `doi-line-item-snapshot/v1` | `7cedaa9c72c6f44566a5c66ff648bb26be97670ad3bb8173a76c11a40d0d628e` |
| `models` | `DOIMutualExclusionEvidence` | `doi-mutual-exclusion-evidence/v1` | `b0ef1f7e8f18acb4a997e5332dec3374add29dd235fb7545abba98e8f8207041` |
| `models` | `DOIOccurrenceGuard` | `doi-occurrence-guard/v1` | `b3cc9a02d5a4975c92d032f5a404559a9bfa69ef50dcb78220f8e0f3dacd176e` |
| `models` | `DOIOpportunity` | `doi-opportunity/v1` | `b1136eb47598439e2e9216c1a7f8f532cfa1713d46402dfb9c31f23cbdad3ce7` |
| `models` | `DOIOpportunityIdentity` | `doi-opportunity-id/v1` | `d35358a7d4a37af5492a097ef576b418a7146af40bc9547478f8f48411c3f67d` |
| `models` | `DOIOpportunityScope` | `doi-opportunity-scope/v1` | `7bdd6d29317aeedaa2d87f018871f6f31431b3adc4f7906edc5614fe8a977ca6` |
| `models` | `DOIOrderSnapshot` | `doi-order-snapshot/v1` | `4484170a2128a43d96cdf133cedad81b4d03453429e07a3cb55da0f0c49acf1a` |
| `models` | `DOIRulePackBinding` | `doi-rule-pack-binding/v1` | `aaa63f608d57bf49a8b5eda4294ef7f32b84aee6fae956b64a4327cc7da13789` |
| `models` | `DOIWWCEvent` | `doi-wwc-event/v1` | `ccdda993af80573ef74b43ef69734ffc49763c2fa96e06557047ae12dbbb739e` |
| `models` | `DOIWWCProjection` | `doi-wwc-projection/v1` | `9916db509224bc6241dc51e60fa2d899c82544824fe8b9499db7edf9136a85ae` |
| `models` | `DedupeFinding` | `doi-dedupe-finding/v1` | `0b23e9bd5349394b2877faef415bc8c50a7500143964625798597cf79098c89c` |
| `models` | `DedupeVerificationFact` | `doi-dedupe-verification-fact/v1` | `be8df7dea1a4a0cc3e8e800286877a889ab9db52e14c0388470a422403fb742f` |
| `models` | `HumanAuthorityGrant` | `doi-human-authority-grant/v1` | `12ec90eb11853e762332b6f943b8aae738b1d8af26f819a5f331d78c10488caf` |
| `models` | `LineContinuityProof` | `doi-line-continuity-proof/v1` | `fb63c07d70bd29fe2b081f3d42d6d0c445a7e17835e1acc01ef1a8feb8f0ad8b` |
| `models` | `StructuredHumanFact` | `doi-structured-human-fact/v1` | `414e1efaba447153fcca47d5bd2be527f0a1d0a48f5efbb5c91a69083730acc1` |
| `models` | `WWCFinding` | `doi-wwc-finding/v1` | `205155bfa56ccc89f854f5a7ac7d33cc17fa7bc40cf284a35770443b4f6672e7` |
| `knowledge` | `DOIAlternateObservation` | `doi-alternate-observation/v1` | `7364495156fdf2e0bdd0703eaf2760c39ca7190707091e70f0f49e68bf4d8d3b` |
| `knowledge` | `DOIAlternateRelationship` | `doi-alternate-relationship/v1` | `48735f8b5e72c24e9b44aa9a162d6ef02671428aa9d9cdf82b280d28e5523f93` |
| `knowledge` | `DOIAlternateRelationshipRevision` | `doi-alternate-relationship-revision/v1` | `ecaa862cf7ff89ef1f42ab36c66a3b59a5b25e16826c9c709f99fa418f496bdb` |
| `knowledge` | `DOIExactSKUObservation` | `doi-exact-sku-observation/v1` | `ad3c5c6985f6231815e1e5d1284332e710f6bd9c2fd42a50da6c8d4dd1a72f8d` |
| `lifecycle` | `TransitionGuardAuthorityEvidence` | `doi-transition-guard-authority/v1` | `1e1408766286dec56779ae789456a87a89fc10a72befb2f37c3c891b39916ae7` |
| `lifecycle` | `TransitionGuardFacts` | `doi-transition-guard-facts/v1` | `1777316431e6df212b063b28072de3d32d7a1a9580daed4d4752d4c1d019ea4f` |
| `lifecycle` | `TransitionGuardProof` | `doi-transition-guard-proof/v1` | `0a6193d2e62407d923ba7a65b8f6cece8a3e54219825e1c97438694f8e745948` |
| `lifecycle` | `TransitionCommand` | `doi-transition-command/v1` | `333df15aa867ffaedc5a83b3fa1b485d0a16f7b98d90d462d25e823663bd90a8` |
| `lifecycle` | `TransitionEvent` | `doi-lifecycle-event/v1` | `9c72f75e6c8b5b59fd761f14710e7c70ad085cf179ec73baa8c98421d33f4a18` |
| `lifecycle` | `AttentionEvent` | `doi-attention-event/v1` | `eb01670d81993ed949101e266ce7ff7c76396fc891447d8014ec2c7b42f5c03f` |
| `interventions` | `ActionVerificationEvent` | `doi-action-verification-event/v1` | `acc8473252ca010d492d79441854ce6b6364d2d660387478d4b3cd82e170cfc5` |
| `interventions` | `ActionVerificationMaterial` | `doi-action-verification-material/v1` | `b017fe0c6083e0157d02f27657c9bb751c6bd34a2bce090e3e187f48040875ff` |
| `interventions` | `AuthorizedHumanExactValueRecord` | `doi-authorized-human-exact-value-record/v1` | `16149709eeedd581d7adcb351b812b6ed6bdbaab9df338f85c847e9a594ab400` |
| `interventions` | `AuthorizedHumanResultingLinkEvidence` | `doi-authorized-human-resulting-link-evidence/v1` | `2b649297c8b0dc2604d5d7291a24b32ac82767e1c98279733b686366a1550fc0` |
| `interventions` | `DOIIntervention` | `doi-intervention/v1` | `2b612f69ade3da3131fb42bb46dbbf3bce5b9877b8946fd23e37f64b42f7764e` |
| `interventions` | `DOIResultingOrderLink` | `doi-resulting-order-link/v1` | `b78f69800927dd7a30b9809147a863fb4bc907303fd644f93b134b22aa1131f8` |
| `interventions` | `DOIResultingOrderLinkSearch` | `doi-resulting-order-link-search/v1` | `217d71dce5288d81d27b61afe470ac12250dbdeace587f764280640602cb9500` |
| `interventions` | `LogicalEvidenceKey` | `doi-logical-evidence-key/v1` | `5731825247b8b7b96b19e4b5ea601758bbf0e8c858341ba36ad925b31c2d66e0` |
| `interventions` | `ResultingLinkSearchEvent` | `doi-resulting-link-search-event/v1` | `0493447868bf2a839bd8f683c08df13bf264b90eba0b60839adee14c4c8ec8bc` |
| `interventions` | `ResultingLinkSearchEvidence` | `doi-resulting-link-search-evidence/v1` | `0e6e1c8ee88dd8c9f4940e42474fbe9265c91cae6bec1464c9367cf28ac7c9cf` |
| `interventions` | `ResultingOrderLinkRevision` | `doi-resulting-order-link-revision/v1` | `d3fea5803855fa73794f90988e6152fc39b0b5e4a3ea9c2fd67df7f164f2e45d` |
| `interventions` | `SystemExactValueRecord` | `doi-system-exact-value-record/v1` | `dd3a9b2602334397f3602b074bd96975dbe41cb6cdf292d136ce3f37c6c1756a` |
| `interventions` | `SystemResultingLinkEvidence` | `doi-system-resulting-link-evidence/v1` | `041a77cde24768af55739e918e0ad307e7e17f05927ded839d9f0945cbcb3dc3` |
| `interventions` | `TargetRepObservation` | `doi-target-rep-observation/v1` | `e866d7aabeaef21336428f5c405ef38a6b23969759ad2624af42d279a873c303` |
| `interventions` | `TargetRepVerificationProof` | `doi-target-rep-verification-proof/v1` | `d9ec0e137fe883455a4d67dc236b0c2e578e7ba06aae4161b749b0f7fa4df559` |
| `interventions` | `ValueEvent` | `doi-value-event/v1` | `8a5b9a46f910160655c3d67d0bc3240d6f407dc44dd854e8b4e9e3d7edab8e66` |
| `interventions` | `VerificationEvidence` | `doi-verification-evidence/v1` | `635906a600e061798d1b8804f7b479c3248c2e61cbcbd8b7d97ac7141b9ad992` |
| `retention` | `KPIContributionEvent` | `doi-kpi-contribution-event/v1` | `cbdecc9843c29639bac1d135edae6ad810aab15778e55027dab91e896571e003` |
| `retention` | `NonidentifyingKPIBucket` | `doi-nonidentifying-kpi-bucket/v1` | `abdfd0a7738ea80af8d8181d19f4657a20b93c9a3140404fc869e4370ec329a6` |
| `retention` | `PriorClosureRetentionBindingV1` | `doi-prior-closure-retention-binding/v1` | `811001092428f0db2b2069457b5197b780a1326afe1414674afab653ad07bf8e` |
| `retention` | `RetainedKPIContribution` | `doi-retained-kpi-contribution/v1` | `d8bd285659a6d531d6e4568a6119b0a3704bf0caec4a72037f3aaa4c7a63e592` |
| `retention` | `VerifiedCurrencyEnvelope` | `doi-verified-currency-envelope/v1` | `177a78b1d98ab7f38f049b3d438a9f60fa1b56010c8ef2da92c91617833f34f5` |

## Exact preimages

The visible newline after each domain is the single required separator.
Every canonical JSON value occupies exactly one line.

### DOIStagedOrder

```text
doi-staged-order/v1
{"order_id":"SYN-ORDER-1","raw_source_policy_version":"doi-synthetic-order-number/v1","reasons":[],"source_ref_ids":["SYN-EVIDENCE-DOI-ROW-0001"],"status":"READY"}
```

### DOIRejectedSourceRecord

```text
doi-rejected-source-record/v1
{"order_id":"SYN-ORDER-2","outcome":"ASSIGNEE_CONFLICT","reasons":[{"code":"RC-008","label":"SOURCE_ASSIGNEE_CONFLICT","registry_version":"synthetic-doi-reason-registry/v1.0.1"}],"target_source_ref_ids":["SYN-EVIDENCE-DOI-ROW-0002"]}
```

### DOISourceBatch

```text
doi-source-batch/v1
{"aggregate_reasons":[],"batch_id":"SYN-EVIDENCE-DOI-BATCH-0001","change_state":"UNCHANGED","coherence_state":"COHERENT","counts":{"accepted_row_count":1,"conflict_row_count":2,"duplicate_row_count":0,"invalid_row_count":0,"out_of_scope_row_count":0,"rejected_order_count":1,"source_row_count":3,"staged_order_count":1,"unrecognized_assignee_row_count":0},"finite_extent":3,"identity":{"domain":"doi-source-batch-identity/v1","sha256":"7a5efd40848bfb8ad1aa69a81b265d1d12722c80485340d374e321353c3cd97b"},"mapping_version":"synthetic-doi-queue-mapping/v1","ordered_source_row_sha256":"87dafd1cf0e1dcba8a76e345f57742ede3e8ce8e8155e36c86cb8ba986cefdd9","rejected_records":[{"order_id":"SYN-ORDER-2","outcome":"ASSIGNEE_CONFLICT","reasons":[{"code":"RC-008","label":"SOURCE_ASSIGNEE_CONFLICT","registry_version":"synthetic-doi-reason-registry/v1.0.1"}],"target_source_ref_ids":["SYN-EVIDENCE-DOI-ROW-0002"]}],"source_identity_id":"SYN-EVIDENCE-DOI-SOURCE-0001","staged_orders":[{"order_id":"SYN-ORDER-1","raw_source_policy_version":"doi-synthetic-order-number/v1","reasons":[],"source_ref_ids":["SYN-EVIDENCE-DOI-ROW-0001"],"status":"READY"}],"status":"READY","structural_anchors":["ORDER_NUMBER","ASSIGNED_REP"]}
```

### SourceImportResult

```text
doi-source-import-result/v1
{"batch":{"aggregate_reasons":[],"batch_id":"SYN-EVIDENCE-DOI-BATCH-0001","change_state":"UNCHANGED","coherence_state":"COHERENT","counts":{"accepted_row_count":1,"conflict_row_count":2,"duplicate_row_count":0,"invalid_row_count":0,"out_of_scope_row_count":0,"rejected_order_count":1,"source_row_count":3,"staged_order_count":1,"unrecognized_assignee_row_count":0},"finite_extent":3,"identity":{"domain":"doi-source-batch-identity/v1","sha256":"7a5efd40848bfb8ad1aa69a81b265d1d12722c80485340d374e321353c3cd97b"},"mapping_version":"synthetic-doi-queue-mapping/v1","ordered_source_row_sha256":"87dafd1cf0e1dcba8a76e345f57742ede3e8ce8e8155e36c86cb8ba986cefdd9","rejected_records":[{"order_id":"SYN-ORDER-2","outcome":"ASSIGNEE_CONFLICT","reasons":[{"code":"RC-008","label":"SOURCE_ASSIGNEE_CONFLICT","registry_version":"synthetic-doi-reason-registry/v1.0.1"}],"target_source_ref_ids":["SYN-EVIDENCE-DOI-ROW-0002"]}],"source_identity_id":"SYN-EVIDENCE-DOI-SOURCE-0001","staged_orders":[{"order_id":"SYN-ORDER-1","raw_source_policy_version":"doi-synthetic-order-number/v1","reasons":[],"source_ref_ids":["SYN-EVIDENCE-DOI-ROW-0001"],"status":"READY"}],"status":"READY","structural_anchors":["ORDER_NUMBER","ASSIGNED_REP"]},"counts":{"accepted_row_count":1,"conflict_row_count":2,"duplicate_row_count":0,"invalid_row_count":0,"out_of_scope_row_count":0,"rejected_order_count":1,"source_row_count":3,"staged_order_count":1,"unrecognized_assignee_row_count":0},"kind":"SUCCEEDED","reasons":[]}
```

### DOIRunWorkItem

```text
doi-run-work-item/v1
{"order_id":"SYN-ORDER-1","origin":"SOURCE_IMPORT","run_id":"SYN-RUN-DOI-SOURCE-0001","source_batch_id":"SYN-EVIDENCE-DOI-BATCH-0001","work_item_id":"SYN-INTERACTION-DOI-WORK-000001"}
```

### DOIRunWorkDisposition

```text
doi-run-work-disposition/v1
{"evidence":{"canonical_json":{"command":{"domain":"doi-transition-command/v1","sha256":"333df15aa867ffaedc5a83b3fa1b485d0a16f7b98d90d462d25e823663bd90a8"},"event_id":"SYN-EVIDENCE-EVENT-TR-044","from_state":"NONEXISTENT","occurred_at":"2026-08-20T12:00:00Z","predecessor_sha256":null,"reasons":[],"schema_version":"doi-lifecycle/v1","sequence":1,"stream_id":"SYN-EVIDENCE-STREAM-TR-044","to_state":"VERIFIED","transition_id":"TR-044","transition_registry_version":"synthetic-doi-transition-registry/v1.0.1"},"domain":"doi-lifecycle-event/v1","sha256":"9c72f75e6c8b5b59fd761f14710e7c70ad085cf179ec73baa8c98421d33f4a18"},"kind":"BLOCKED_ORDER","occurred_at":"2026-08-10T12:00:45Z","portal_read_performed":false,"reasons":[{"code":"RC-011","label":"EXTRACTION_REQUIRED_IDENTITY_MISSING","registry_version":"synthetic-doi-reason-registry/v1.0.1"}],"run_id":"SYN-RUN-DOI-SOURCE-0001","work_item_id":"SYN-INTERACTION-DOI-WORK-000001","work_item_sha256":"41c4961d61c07b07977e00b4ed60b3f6f561aa36e33d2442986a59e69660b891"}
```

### DOIRun

```text
doi-run/v1
{"completed_at":null,"counts":{"blocked_order_count":0,"disposition_subject_count":0,"order_exception_count":0,"portal_read_count":0,"source_attempt_count":1,"source_rows":{"accepted_row_count":0,"conflict_row_count":0,"duplicate_row_count":0,"invalid_row_count":0,"out_of_scope_row_count":0,"rejected_order_count":0,"source_row_count":0,"staged_order_count":0,"unrecognized_assignee_row_count":0},"successful_evaluation_count":0,"work_item_count":0},"invocation_id":"SYN-INTERACTION-DOI-RUN-SOURCE-0001","purge_eligible_at":null,"recheck_order_id":null,"run_id":"SYN-RUN-DOI-SOURCE-0001","run_type":"RUN_DOI_REVIEW","schema_version":"doi-run/v1","source_batch_id":null,"started_at":"2026-08-10T12:00:00Z","status":"IN_PROGRESS","terminal_reasons":[]}
```

### DOIRunEvent

```text
doi-run-event/v1
{"event_kind":"RUN_STARTED","occurred_at":"2026-08-10T12:00:00Z","reasons":[],"run_id":"SYN-RUN-DOI-SOURCE-0001","sequence":1,"status":"IN_PROGRESS"}
```

### DOISourceImportAttempt

```text
doi-source-import-attempt/v1
{"attempt_id":"SYN-INTERACTION-DOI-ATTEMPT-000001","completed_at":null,"ordinal":1,"portal_read_count":0,"reasons":[],"run_id":"SYN-RUN-DOI-SOURCE-0001","schema_version":"doi-source-import-attempt/v1","source_batch_id":null,"source_identity_id":"SYN-EVIDENCE-DOI-SOURCE-0001","started_at":"2026-08-10T12:00:00Z","state":"STARTED"}
```

### DOISourceImportAttemptEvent

```text
doi-source-import-attempt-event/v1
{"attempt_id":"SYN-INTERACTION-DOI-ATTEMPT-000001","event_kind":"SOURCE_IMPORT_STARTED","occurred_at":"2026-08-10T12:00:00Z","reasons":[],"sequence":1,"source_batch_id":null}
```

### FinalizeFailedSourceImportNoRetryCommand

```text
doi-finalize-failed-source-no-retry-command/v1
{"accepted_actor_id":"SYN-REP-AUTHORIZED-0001","accepted_at":"2026-08-10T12:01:00Z","command_id":"SYN-INTERACTION-DOI-COMMAND-NORETRY-0001","greatest_failed_attempt_id":"SYN-INTERACTION-DOI-ATTEMPT-000001","kind":"FINALIZE_FAILED_SOURCE_IMPORT_NO_RETRY","run_id":"SYN-RUN-DOI-SOURCE-0001","schema_version":"doi-finalize-failed-source-no-retry-command/v1"}
```

### NoRetryCommandReceipt

```text
doi-no-retry-command-receipt/v1
{"accepted_at":"2026-08-10T12:01:00Z","command":{"domain":"doi-finalize-failed-source-no-retry-command/v1","sha256":"75b55630987b19e186c1f89306834844848e73d664378841bbc87f2c862713d5"},"receipt_id":"SYN-EVIDENCE-DOI-RECEIPT-000001","run":{"domain":"doi-run/v1","sha256":"d38a0dd61f9c438a1ae1660c82a28b29087ee79abd5eac1aaaaf9d138525adf8"},"run_event":{"domain":"doi-run-event/v1","sha256":"d2f54d3b002adb77840ba3399c321cb2a55e2ecfce7e9b968952e65c3e8f8564"}}
```

### ExtractionReservationReceipt

```text
doi-extraction-reservation-receipt/v1
{"occurrence_id":"SYN-INTERACTION-DOI-OCCURRENCE-0001","operation":"EXTRACTION_RESERVED","receipt_id":"SYN-EVIDENCE-DOI-RECEIPT-000002","reserved_at":"2026-08-10T12:00:30Z","run_id":"SYN-RUN-DOI-SOURCE-0001"}
```

### PreExtractionRulesUnavailableReceipt

```text
doi-pre-extraction-rules-unavailable-receipt/v1
{"event":{"domain":"doi-run-event/v1","sha256":"34b74370e3e192a3a3c42963e0efc5dc9463bc3aebb8cf9f774dff34a11ce44e"},"operation":"PRE_EXTRACTION_RULES_UNAVAILABLE","receipt_id":"SYN-EVIDENCE-DOI-RECEIPT-000003","run":{"domain":"doi-run/v1","sha256":"dc46226af6cba14f28cb3b67aea296e36a67c4624ab9665d8bb0aaeb1bd79a93"}}
```

### SyntheticQueueImageContent

```text
doi-source-image-content/v1
{"finite_extent":3,"mapping_version":"synthetic-doi-queue-mapping/v1","rows":[{"assignee_class":"TARGET_REP","order_number_class":"SYN-ORDER-1","source_ref_id":"SYN-EVIDENCE-DOI-ROW-0001"},{"assignee_class":"TARGET_REP","order_number_class":"SYN-ORDER-2","source_ref_id":"SYN-EVIDENCE-DOI-ROW-0002"},{"assignee_class":"OTHER_ASSIGNEE","order_number_class":"SYN-ORDER-2","source_ref_id":"SYN-EVIDENCE-DOI-ROW-0003"}],"source_identity_id":"SYN-EVIDENCE-DOI-SOURCE-0001","structural_anchors":["ORDER_NUMBER","ASSIGNED_REP"]}
```

### DOISourceBatchIdentity

```text
doi-source-batch-identity/v1
{"counts":{"accepted_row_count":1,"conflict_row_count":2,"duplicate_row_count":0,"invalid_row_count":0,"out_of_scope_row_count":0,"rejected_order_count":1,"source_row_count":3,"staged_order_count":1,"unrecognized_assignee_row_count":0},"finite_extent":3,"mapping_version":"synthetic-doi-queue-mapping/v1","order_number_policy_version":"doi-synthetic-order-number/v1","ordered_source_row_sha256":"87dafd1cf0e1dcba8a76e345f57742ede3e8ce8e8155e36c86cb8ba986cefdd9","rejected_records":[{"domain":"doi-rejected-source-record/v1","sha256":"7617bf31344d188c54eb3eebdc2d76306f8bbb27a4ff72452de812b227d1e310"}],"source_identity_id":"SYN-EVIDENCE-DOI-SOURCE-0001","staged_orders":[{"domain":"doi-staged-order/v1","sha256":"508baca143970fa4c74093eae562c92fcb3e0d010392dbdc256f352eed0c132f"}],"structural_anchors":["ORDER_NUMBER","ASSIGNED_REP"]}
```

### CompositeLineContinuityIdentity

```text
doi-line-continuity-composite/v1
{"es_number":"SYN-SKU-ES-1","mfg_number":"SYN-SKU-MFG-1","order_id":"SYN-ORDER-1","ordered_quantity":"2","schema_version":"doi-line-continuity-composite/v1","source_ordinal":1,"source_section":"LINE_ITEMS"}
```

### DOIExtractionAttempt

```text
doi-extraction-attempt/v1
{"attempt_id":"SYN-INTERACTION-DOI-EXTRACT-0001","completed_at":"2026-08-10T12:00:01Z","order_id":"SYN-ORDER-1","portal_read_count":1,"reasons":[{"code":"RC-011","label":"EXTRACTION_REQUIRED_IDENTITY_MISSING","registry_version":"synthetic-doi-reason-registry/v1.0.1"},{"code":"RC-014","label":"EXTRACTION_FAILED","registry_version":"synthetic-doi-reason-registry/v1.0.1"},{"code":"RC-015","label":"RECHECK_REQUIRED","registry_version":"synthetic-doi-reason-registry/v1.0.1"}],"run_id":"SYN-RUN-DOI-EXTRACT-0001","schema_version":"doi-extraction-attempt/v1","snapshot_id":null,"started_at":"2026-08-10T12:00:00Z","status":"FAILED"}
```

### AttentionCauseKey

```text
doi-attention-cause-key/v2
{"case_id":"SYN-EVIDENCE-DOI-CASE-ATTENTION-KAT-CASE","cause_evidence":{"domain":"doi-extraction-attempt/v1","sha256":"5d03d269a1d2139761276cc826c0e955d9770111cdbede933bf58de578e1ac8d"},"cause_subject":["FAILED_EXTRACTION","SYN-INTERACTION-DOI-CASE-ATTENTION-KAT-EXTRACTION","SYN-RUN-DOI-CASE-ATTENTION-KAT-EXTRACTION","SYN-ORDER-1"],"condition":"RECHECK_REQUIRED","order_id":"SYN-ORDER-1","schema_version":"doi-attention-cause-key/v2"}
```

### AttentionOwnerDecision

```text
doi-attention-owner-decision/v1
{"occurred_at":"2026-08-20T12:01:00Z","occurrence_id":"SYN-EVIDENCE-DOI-CASE-ATTENTION-KAT-SET","owner_binding":{"domain":"doi-attention-event/v2","sha256":"e169e7c7ce9036a5f6a4caf59963bc121f12803d8d07530c0f3eebc8d8a01ef1"},"prior_head":null,"result_head":{"domain":"doi-attention-event/v2","sha256":"e169e7c7ce9036a5f6a4caf59963bc121f12803d8d07530c0f3eebc8d8a01ef1"},"schema_version":"doi-attention-owner-decision/v1","stream_id":"SYN-EVIDENCE-DOI-CASE-ATTENTION-KAT-CASE","transition_id":"TR-020","validator_tag":"FAILED_EXTRACTION_SET"}
```

### AttentionOwnerEvent

```text
doi-attention-event/v2
{"action":"SET","active_set_event_binding":null,"active_set_event_id":null,"case_id":"SYN-EVIDENCE-DOI-CASE-ATTENTION-KAT-CASE","cause_evidence_binding":{"domain":"doi-extraction-attempt/v1","sha256":"5d03d269a1d2139761276cc826c0e955d9770111cdbede933bf58de578e1ac8d"},"cause_key":{"domain":"doi-attention-cause-key/v2","sha256":"d037fbc8c92c8dc92d39d56bd4d4e1feda6dd5a04bf8cb9a77f250b4ebfe0bbf"},"cause_subject":["FAILED_EXTRACTION","SYN-INTERACTION-DOI-CASE-ATTENTION-KAT-EXTRACTION","SYN-RUN-DOI-CASE-ATTENTION-KAT-EXTRACTION","SYN-ORDER-1"],"condition":"RECHECK_REQUIRED","event_id":"SYN-EVIDENCE-DOI-CASE-ATTENTION-KAT-SET","occurred_at":"2026-08-20T12:01:00Z","order_id":"SYN-ORDER-1","predecessor_binding":null,"replacement_cause_key":null,"replacement_condition":null,"replacement_evidence_binding":null,"replacement_subject":null,"resolver_binding":null,"resulting_projection_binding":null,"schema_version":"doi-attention-event/v2","sequence":1,"transition_id":"TR-020"}
```

### CaseOwnerDecision

```text
doi-case-owner-decision/v1
{"occurred_at":"2026-08-20T12:00:00Z","occurrence_id":"SYN-EVIDENCE-DOI-CASE-ATTENTION-KAT-CREATE","owner_binding":{"domain":"doi-case-owner-event/v1","sha256":"d713de619d4da23ca66451257048698edcc19786e3bd30fe6da89ddb516556f0"},"prior_head":null,"result_head":{"domain":"doi-case-owner-event/v1","sha256":"d713de619d4da23ca66451257048698edcc19786e3bd30fe6da89ddb516556f0"},"schema_version":"doi-case-owner-decision/v1","stream_id":"SYN-EVIDENCE-DOI-CASE-ATTENTION-KAT-CASE","transition_id":"TR-007"}
```

### CaseOwnerEvent

```text
doi-case-owner-event/v1
{"case_id":"SYN-EVIDENCE-DOI-CASE-ATTENTION-KAT-CASE","case_projection":{"case_id":"SYN-EVIDENCE-DOI-CASE-ATTENTION-KAT-CASE","current_evaluation_id":null,"current_snapshot_id":null,"lifecycle_state":"ACTIVE","order_id":"SYN-ORDER-1","terminal_closure_reason":null},"evaluation_binding":null,"event_id":"SYN-EVIDENCE-DOI-CASE-ATTENTION-KAT-CREATE","event_kind":"CASE_CREATED","occurred_at":"2026-08-20T12:00:00Z","order_id":"SYN-ORDER-1","predecessor_binding":null,"schema_version":"doi-case-owner-event/v1","sequence":1,"snapshot_binding":null,"source_binding":{"domain":"doi-case-source-binding/v2","sha256":"ebce54f8dc3704c79035f81be28cb158655a3b598804da0d5f5d01824547d54f"},"transition_id":"TR-007"}
```

### DOICaseSourceAdmissionProofV1

```text
doi-case-source-admission-proof/v1
{"admitted_at":"2026-08-20T12:00:00Z","case_id":"SYN-EVIDENCE-DOI-CASE-ATTENTION-KAT-CASE","case_source_binding_id":"SYN-EVIDENCE-DOI-CASE-ATTENTION-KAT-SOURCE-BINDING","content_binding":{"domain":"doi-source-batch-identity/v1","sha256":"39f845835c9244a9963e106ca552c3a488e14b73550f754137a4d76985fc056c"},"order_id":"SYN-ORDER-1","proof_id":"SYN-EVIDENCE-DOI-CASE-ATTENTION-KAT-ADMISSION","schema_version":"doi-case-source-admission-proof/v1","source_batch_id":"SYN-EVIDENCE-DOI-CASE-ATTENTION-KAT-BATCH","target_assignee":"TARGET_REP"}
```

### OwnedCaseSourceBinding

```text
doi-case-source-binding/v2
{"admission_proof":{"domain":"doi-case-source-admission-proof/v1","sha256":"ba1335e38e50eb855af22a9e888ec0b10a0aa6776e5d8e698f620c4da8fd4618"},"batch_identity":{"domain":"doi-source-batch-identity/v1","sha256":"39f845835c9244a9963e106ca552c3a488e14b73550f754137a4d76985fc056c"},"binding_id":"SYN-EVIDENCE-DOI-CASE-ATTENTION-KAT-SOURCE-BINDING","case_id":"SYN-EVIDENCE-DOI-CASE-ATTENTION-KAT-CASE","order_id":"SYN-ORDER-1","schema_version":"doi-case-source-binding/v2","source_batch_id":"SYN-EVIDENCE-DOI-CASE-ATTENTION-KAT-BATCH"}
```

### ActionContextCompletionSource

```text
doi-action-context-completion-source/v1
{"action_context_binding":{"domain":"doi-action-context/v1","sha256":"8ca679e9716d0d784a3c6bcc96b5c443b4e165882042a456ab46d3a46bfe3dec"},"action_context_id":"SYN-EVIDENCE-DOI-MODEL-KAT-ACTION-CONTEXT","completion_trigger":"SYSTEM_VERIFIED","occurred_at":"2026-08-20T14:15:17Z","source":{"domain":"shared-source-ref/v1","sha256":"1fad637b6386bedaf4a33b35e0623c2c3713beff2b6f494d72c4c82e0c7fe76a"}}
```

### ActionContextOpeningAuthorization

```text
doi-action-context-opening-authorization/v1
{"actor":"SYN-REP-DOI-MODEL-KAT-AUTHORIZED","attempt_intent_id":"SYN-INTERACTION-DOI-MODEL-KAT-ACTION-CONTEXT","authorization_id":"SYN-EVIDENCE-DOI-MODEL-KAT-OPENING-AUTHORITY","case_id":"SYN-EVIDENCE-DOI-MODEL-KAT-CASE","case_source_binding":{"domain":"doi-case-source-binding/v1","sha256":"7d7e9168b8f1d47a1523e211a590c360546778e393adec9705b5da184b28d850"},"context_kind":"FULFILLMENT_SPLIT_REVIEW","evaluation_binding":{"domain":"doi-evaluation-record/v1","sha256":"05c5542cb58512a94e4d96bf6b5014e55533194905d992c73e06f89cdb3b5554"},"evaluation_id":"SYN-EVALUATION-DOI-MODEL-KAT-0001","granted_at":"2026-08-20T14:15:16Z","intervention_type":"FULFILLMENT_SPLIT","line_scope":["SYN-EVIDENCE-DOI-MODEL-KAT-LINE-0001","SYN-EVIDENCE-DOI-MODEL-KAT-LINE-0002"],"opportunity_binding":{"domain":"doi-opportunity/v1","sha256":"b1136eb47598439e2e9216c1a7f8f532cfa1713d46402dfb9c31f23cbdad3ce7"},"opportunity_id":"SYN-EVIDENCE-DOI-OPPORTUNITY-D35358A7D4A37AF5492A097EF576B418A7146AF40BC9547478F8F48411C3F67D","order_id":"SYN-ORDER-DOI-MODEL-KAT-0001","relationship_revision_binding":null,"request_binding":{"domain":"doi-action-context-request/v1","sha256":"b075c1e84d9b4ce7996619358803597b60e0af66902adf77ba4af6bca261b49a"},"request_canonical_bytes":"{\"action_context_request_schema_version\":\"doi-action-context-request/v1\",\"attempt_intent_id\":\"SYN-INTERACTION-DOI-MODEL-KAT-ACTION-CONTEXT\",\"case_id\":\"SYN-EVIDENCE-DOI-MODEL-KAT-CASE\",\"context_kind\":\"FULFILLMENT_SPLIT_REVIEW\",\"created_by_actor_id\":\"SYN-REP-DOI-MODEL-KAT-AUTHORIZED\",\"evaluation_id\":\"SYN-EVALUATION-DOI-MODEL-KAT-0001\",\"opportunity_id\":\"SYN-EVIDENCE-DOI-OPPORTUNITY-D35358A7D4A37AF5492A097EF576B418A7146AF40BC9547478F8F48411C3F67D\"}","schema_version":"synthetic-doi-models/v1","snapshot_id":"SYN-SNAPSHOT-DOI-MODEL-KAT-0001","source":{"domain":"shared-source-ref/v1","sha256":"d9f08d1072ac90910910d9fd8bd9deb6e52f03da23daa95e7843ba11c89479f8"}}
```

### ActionContextOpeningRequest

```text
doi-action-context-request/v1
{"action_context_request_schema_version":"doi-action-context-request/v1","attempt_intent_id":"SYN-INTERACTION-DOI-MODEL-KAT-ACTION-CONTEXT","case_id":"SYN-EVIDENCE-DOI-MODEL-KAT-CASE","context_kind":"FULFILLMENT_SPLIT_REVIEW","created_by_actor_id":"SYN-REP-DOI-MODEL-KAT-AUTHORIZED","evaluation_id":"SYN-EVALUATION-DOI-MODEL-KAT-0001","opportunity_id":"SYN-EVIDENCE-DOI-OPPORTUNITY-D35358A7D4A37AF5492A097EF576B418A7146AF40BC9547478F8F48411C3F67D"}
```

### AlternateCandidate

```text
doi-alternate-candidate/v1
{"candidate_id":"SYN-EVIDENCE-DOI-MODEL-KAT-CANDIDATE","candidate_sku":"SYN-SKU-DOI-MODEL-KAT-ES-0001","compatibility_decision":"NOT_REQUIRED","current_observation":true,"mutual_exclusion_evidence":null,"mutual_exclusion_group":null,"observation_binding":{"domain":"doi-exact-sku-observation/v1","sha256":"241268f69eed300c6c7df5e9b4d210509f9d26c16343b50c4c1de1b62b7cd626"},"observed_availability":"IN_STOCK","opportunity_type":"EXACT_SKU_RECHECK","ordered_line_id":"SYN-EVIDENCE-DOI-MODEL-KAT-LINE-0001","potential_value":{"amount":"10.00","currency_code":"USD","currency_registry_version":"synthetic-iso-style-currency-registry/v1","currency_scale":2},"quantity":"1","relationship_revision_binding":null,"schema_version":"synthetic-doi-models/v1","unknown_reasons":[],"validity":"VERIFIED"}
```

### ContactWorkflowEvent

```text
doi-contact-state-event/v1
{"action_context":{"domain":"doi-action-context/v1","sha256":"1d8876474417f89cedab723d8cc63fbe7fb067aac39c69a33af2d82edc2b9b69"},"contact_occurred_at":null,"evaluation":{"domain":"doi-evaluation-record/v1","sha256":"cfc80b0b873a43a9bb42b4e65dfd7fb531dcbc7b5252cec93e4022034f283dbd"},"event_id":"SYN-EVIDENCE-DOI-MODEL-KAT-CONTACT-WORKFLOW-EVENT","event_type":"CONTACT_REQUIRED_DERIVED","guard":{"domain":"doi-occurrence-guard/v1","sha256":"e4e3a515608c2232b1a48a1e28c6416817f4d67e02589a873f39be4bbc7e21ef"},"human_authority":null,"predecessor_binding":null,"prior_state":"NOT_CONTACTED","recorded_at":"2026-08-20T14:15:17Z","resulting_state":"CONTACT_REQUIRED","schema_version":"synthetic-doi-models/v1","sequence":1,"stream_id":"SYN-EVIDENCE-DOI-MODEL-KAT-CONTACT-WORKFLOW-STREAM"}
```

### ContactWorkflowProjection

```text
doi-contact-state-projection/v1
{"action_context_binding":{"domain":"doi-action-context/v1","sha256":"1d8876474417f89cedab723d8cc63fbe7fb067aac39c69a33af2d82edc2b9b69"},"action_context_id":"SYN-EVIDENCE-DOI-MODEL-KAT-ALTERNATE-CONTEXT","head_event_binding":{"domain":"doi-contact-state-event/v1","sha256":"91d429894567c8df204c03629163c4de7c03c358f42aab87e1183e2eef95fedf"},"schema_version":"synthetic-doi-models/v1","sequence":1,"state":"CONTACT_REQUIRED","stream_id":"SYN-EVIDENCE-DOI-MODEL-KAT-CONTACT-WORKFLOW-STREAM"}
```

### DOIActionContext

```text
doi-action-context/v1
{"action_context_id":"SYN-EVIDENCE-DOI-MODEL-KAT-ACTION-CONTEXT","close_reason":null,"completion_trigger":null,"created_at":"2026-08-20T14:15:16Z","head_event_binding":{"domain":"doi-action-context-event/v1","sha256":"ad9ba4069a2f2440c1c927108049a1be656462f38dba6a229cc2c7d0f5a45aba"},"observation_links":[],"opening_authorization":{"domain":"doi-action-context-opening-authorization/v1","sha256":"62a0deb8ee134194f57c81cde4b3a9d2098d5205a7666a25fbc63d249734d761"},"schema_version":"synthetic-doi-models/v1","sequence":1,"state":"OPEN","terminal_source_binding":null}
```

### DOIActionContextEvent

```text
doi-action-context-event/v1
{"action_context_id":"SYN-EVIDENCE-DOI-MODEL-KAT-ACTION-CONTEXT","close_reason":null,"completion_trigger":null,"event_id":"SYN-EVIDENCE-DOI-MODEL-KAT-ACTION-CONTEXT-EVENT","event_type":"ACTION_CONTEXT_OPENED","guard":{"domain":"doi-occurrence-guard/v1","sha256":"b3cc9a02d5a4975c92d032f5a404559a9bfa69ef50dcb78220f8e0f3dacd176e"},"human_authority_binding":null,"observation_link":null,"occurred_at":"2026-08-20T14:15:16Z","opening_authorization":{"domain":"doi-action-context-opening-authorization/v1","sha256":"62a0deb8ee134194f57c81cde4b3a9d2098d5205a7666a25fbc63d249734d761"},"predecessor_binding":null,"schema_version":"synthetic-doi-models/v1","sequence":1,"source_entity_binding":{"domain":"doi-action-context-opening-authorization/v1","sha256":"62a0deb8ee134194f57c81cde4b3a9d2098d5205a7666a25fbc63d249734d761"},"superseding_context_binding":null}
```

### DOIActionContextObservationLink

```text
doi-action-context-observation-link/v1
{"action_context_binding":{"domain":"doi-action-context/v1","sha256":"1d8876474417f89cedab723d8cc63fbe7fb067aac39c69a33af2d82edc2b9b69"},"action_context_id":"SYN-EVIDENCE-DOI-MODEL-KAT-ALTERNATE-CONTEXT","alternate_observation_binding":{"domain":"doi-alternate-observation/v1","sha256":"2a87422b8ffcb05e462ba3ba221aebc71c7e800ea78946005b7e1288da55d0e6"},"alternate_observation_id":"SYN-EVIDENCE-DOI-MODEL-KAT-CURRENT-OBSERVATION","case_id":"SYN-EVIDENCE-DOI-MODEL-KAT-CASE","evaluation_id":"SYN-EVALUATION-DOI-MODEL-KAT-ALTERNATE","link_id":"SYN-EVIDENCE-DOI-MODEL-KAT-ACTION-CONTEXT-OBSERVATION-LINK","linked_at":"2026-08-20T14:15:17Z","opportunity_id":"SYN-EVIDENCE-DOI-OPPORTUNITY-D309D71B632C80FB5E6792F3505546436D282F12D3072703E4688B05B6AB1304","relationship_revision_binding":{"domain":"doi-alternate-relationship-revision/v1","sha256":"bb99a1b567af25cfe505ebcdfcbc4e10377f51241d61ecb6592a5ff888a1e261"},"relationship_revision_id":"SYN-EVIDENCE-DOI-MODEL-KAT-RELATIONSHIP-REVISION","schema_version":"synthetic-doi-models/v1"}
```

### DOICaseAdmissionProof

```text
doi-case-admission-proof/v1
{"admitted_at":"2026-08-20T14:15:16Z","case_id":"SYN-EVIDENCE-DOI-MODEL-KAT-CASE","completeness_proof":{"domain":"shared-snapshot-completeness-proof/v1","sha256":"a42c55479a2e8a48c4173d4756c7f4180e2bfc14d32182c2d9d52e82594366a7"},"order_id":"SYN-ORDER-DOI-MODEL-KAT-0001","proof_id":"SYN-EVIDENCE-DOI-MODEL-KAT-ADMISSION","schema_version":"synthetic-doi-models/v1","source":{"domain":"shared-source-ref/v1","sha256":"fb8c93cc6eaf774120a2afa382063ce5f993a02b41d51124cfd02aeaf24b6b03"}}
```

### DOICaseSourceBinding

```text
doi-case-source-binding/v1
{"admission_proof":{"domain":"doi-case-admission-proof/v1","sha256":"be045f07316461213568cb752ea5ade2069ea6583613d9e6a620735e36c4fa5d"},"binding_id":"SYN-EVIDENCE-DOI-MODEL-KAT-CASE-SOURCE","case_id":"SYN-EVIDENCE-DOI-MODEL-KAT-CASE","order_id":"SYN-ORDER-DOI-MODEL-KAT-0001","schema_version":"synthetic-doi-models/v1","source":{"domain":"shared-source-ref/v1","sha256":"fb8c93cc6eaf774120a2afa382063ce5f993a02b41d51124cfd02aeaf24b6b03"}}
```

### DOIContactEvent

```text
doi-contact-event/v1
{"action_context":{"domain":"doi-action-context/v1","sha256":"8ca679e9716d0d784a3c6bcc96b5c443b4e165882042a456ab46d3a46bfe3dec"},"contact_occurred_at":"2026-08-20T14:15:16Z","corrected_direction":null,"corrects_event_id":null,"event_id":"SYN-EVIDENCE-DOI-MODEL-KAT-CONTACT-EVENT","event_type":"INBOUND","guard":{"domain":"doi-occurrence-guard/v1","sha256":"299503688414c78f1ea56e140dc0b8521f5b8046e329f2c0d90f8670667e70d9"},"order_id":"SYN-ORDER-DOI-MODEL-KAT-0001","predecessor_binding":null,"recorded_at":"2026-08-20T14:15:16Z","schema_version":"synthetic-doi-models/v1","sequence":1,"stream_id":"SYN-EVIDENCE-DOI-MODEL-KAT-CONTACT-STREAM","target_rep_participated":true}
```

### DOIContactProjection

```text
doi-contact-projection/v1
{"head_event_binding":{"domain":"doi-contact-event/v1","sha256":"5c0be67b8f1d089bb8aa3d5928ad4f2c295f5a733717d8da68de16dcd80df16d"},"order_id":"SYN-ORDER-DOI-MODEL-KAT-0001","schema_version":"synthetic-doi-models/v1","sequence":1,"state":"INBOUND_OBSERVED","stream_id":"SYN-EVIDENCE-DOI-MODEL-KAT-CONTACT-STREAM"}
```

### DOIDedupeEvent

```text
doi-dedupe-event/v1
{"corrected_human_fact_binding":null,"corrects_event_id":null,"evaluation":null,"event_id":"SYN-EVIDENCE-DOI-MODEL-KAT-DEDUPE-EVENT","event_type":"SOURCE_OBSERVED","finding":{"domain":"doi-dedupe-finding/v1","sha256":"79bead83f437fc5ee09d5420cd9bc750bbc28c745abcbb318163f36a54f37173"},"guard":{"domain":"doi-occurrence-guard/v1","sha256":"70d1c76f7f87612cb4c0d3cbd1c9105eb428891de750963e1806fe7adca5e134"},"human_fact":null,"order_id":"SYN-ORDER-DOI-MODEL-KAT-0001","predecessor_binding":null,"recorded_at":"2026-08-20T14:15:16Z","schema_version":"synthetic-doi-models/v1","sequence":1,"stream_id":"SYN-EVIDENCE-DOI-MODEL-KAT-DEDUPE-STREAM","verification":null}
```

### DOIDedupeProjection

```text
doi-dedupe-projection/v1
{"decision_evaluation_binding":null,"head_event_binding":{"domain":"doi-dedupe-event/v1","sha256":"61e9ff1f9347a1cae25d8c30b55c4f2c688a5ff968663d64af7ba9b2d1af674f"},"human_fact_binding":null,"order_id":"SYN-ORDER-DOI-MODEL-KAT-0001","schema_version":"synthetic-doi-models/v1","sequence":1,"source_finding_binding":{"domain":"doi-dedupe-finding/v1","sha256":"79bead83f437fc5ee09d5420cd9bc750bbc28c745abcbb318163f36a54f37173"},"state":"NOT_CANDIDATE","stream_id":"SYN-EVIDENCE-DOI-MODEL-KAT-DEDUPE-STREAM","verification_binding":null}
```

### DOIEvaluation

```text
doi-evaluation-record/v1
{"append_transition":"TR-027","append_transitions":["TR-027","TR-060"],"evaluation_id":"SYN-EVALUATION-DOI-MODEL-KAT-0001","input_binding":{"domain":"doi-evaluation-input/v1","sha256":"2f796bc1c0a7212669132282ab8069707f7373c7d4e8755bddc40bd1ac48bfa2"},"order_id":"SYN-ORDER-DOI-MODEL-KAT-0001","output":{"aggregate_potential":{"amount":"20.00","currency_code":"USD","currency_registry_version":"synthetic-iso-style-currency-registry/v1","currency_scale":2},"aggregate_potential_state":"AVAILABLE","append_transitions":["TR-027","TR-060"],"closure_proposal":null,"explanation":{"domain":"doi-evaluation-explanation/v1","sha256":"01db09fc41e21f82342aa7735632f2bea443781e9fe95181f41bfd624d66cb60"},"handling_flags":[],"human_review_requirements":["COMMERCIAL_DECISION"],"opportunities":[{"domain":"doi-opportunity/v1","sha256":"b1136eb47598439e2e9216c1a7f8f532cfa1713d46402dfb9c31f23cbdad3ce7"}],"reason_routes":[{"effective_overlay":false,"owning_transition":"TR-034","reason":"RC-031","rule_or_boundary_only":false},{"effective_overlay":false,"owning_transition":"TR-060","reason":"RC-052","rule_or_boundary_only":false}],"reasons":[{"code":"RC-031","label":"FULFILLMENT_SPLIT_CANDIDATE","registry_version":"synthetic-doi-reason-registry/v1.0.1"},{"code":"RC-052","label":"HUMAN_DECISION_REQUIRED","registry_version":"synthetic-doi-reason-registry/v1.0.1"}],"scenario_selection_state":"NOT_REQUIRED","state":"DOI_OPPORTUNITY","transition":"TR-034"},"output_binding":{"domain":"doi-evaluation-output/v1","sha256":"6cd0b137d927b36680be5efad08ab4fddadc9a7e119b9ed13fcff2c3a5ca2e14"},"rule_pack":{"component":"rule_pack","version":"synthetic-doi-rule-pack/v1"},"rule_pack_binding":{"domain":"doi-rule-pack-binding/v1","sha256":"aaa63f608d57bf49a8b5eda4294ef7f32b84aee6fae956b64a4327cc7da13789"},"run_id":"SYN-RUN-DOI-MODEL-KAT-0001","schema_version":"synthetic-doi-models/v1","snapshot_id":"SYN-SNAPSHOT-DOI-MODEL-KAT-0001"}
```

### DOIEvaluationInput

```text
doi-evaluation-input/v1
{"alternate_candidates":[],"alternate_research_state":"NOT_STARTED","available_rule_pack_binding":{"domain":"doi-rule-pack-binding/v1","sha256":"aaa63f608d57bf49a8b5eda4294ef7f32b84aee6fae956b64a4327cc7da13789"},"dedupe_history_projection":null,"dedupe_verification":null,"evaluated_at":"2026-08-20T14:15:16Z","evaluation_id":"SYN-EVALUATION-DOI-MODEL-KAT-0001","human_facts":[],"required_rule_pack":{"component":"rule_pack","version":"synthetic-doi-rule-pack/v1"},"scenario_selection":null,"schema_version":"synthetic-doi-models/v1","snapshot":{"domain":"doi-order-snapshot/v1","sha256":"4484170a2128a43d96cdf133cedad81b4d03453429e07a3cb55da0f0c49acf1a"}}
```

### DOIEvaluationOutput

```text
doi-evaluation-output/v1
{"aggregate_potential":{"amount":"20.00","currency_code":"USD","currency_registry_version":"synthetic-iso-style-currency-registry/v1","currency_scale":2},"aggregate_potential_state":"AVAILABLE","append_transitions":["TR-027","TR-060"],"closure_proposal":null,"explanation":{"domain":"doi-evaluation-explanation/v1","sha256":"01db09fc41e21f82342aa7735632f2bea443781e9fe95181f41bfd624d66cb60"},"handling_flags":[],"human_review_requirements":["COMMERCIAL_DECISION"],"opportunities":[{"domain":"doi-opportunity/v1","sha256":"b1136eb47598439e2e9216c1a7f8f532cfa1713d46402dfb9c31f23cbdad3ce7"}],"reason_routes":[{"effective_overlay":false,"owning_transition":"TR-034","reason":"RC-031","rule_or_boundary_only":false},{"effective_overlay":false,"owning_transition":"TR-060","reason":"RC-052","rule_or_boundary_only":false}],"reasons":[{"code":"RC-031","label":"FULFILLMENT_SPLIT_CANDIDATE","registry_version":"synthetic-doi-reason-registry/v1.0.1"},{"code":"RC-052","label":"HUMAN_DECISION_REQUIRED","registry_version":"synthetic-doi-reason-registry/v1.0.1"}],"scenario_selection_state":"NOT_REQUIRED","state":"DOI_OPPORTUNITY","transition":"TR-034"}
```

### DOIExplanation

```text
doi-evaluation-explanation/v1
{"closure_state":"NONE","handling_flags":[],"human_review_requirements":["COMMERCIAL_DECISION"],"normalized_facts":["ALTERNATE_RESEARCH_STATE=NOT_STARTED","SOURCE_PRESENCE=PRESENT","TOP_LEVEL_STATE=DOI_OPPORTUNITY"],"opportunity_ids":["SYN-EVIDENCE-DOI-OPPORTUNITY-D35358A7D4A37AF5492A097EF576B418A7146AF40BC9547478F8F48411C3F67D"],"opportunity_scopes":["SYN-EVIDENCE-DOI-OPPORTUNITY-D35358A7D4A37AF5492A097EF576B418A7146AF40BC9547478F8F48411C3F67D@7bdd6d29317aeedaa2d87f018871f6f31431b3adc4f7906edc5614fe8a977ca6"],"opportunity_values":["SYN-EVIDENCE-DOI-OPPORTUNITY-D35358A7D4A37AF5492A097EF576B418A7146AF40BC9547478F8F48411C3F67D@{\"state\":\"AVAILABLE\",\"value\":{\"amount\":\"20.00\",\"currency_code\":\"USD\",\"currency_registry_version\":\"synthetic-iso-style-currency-registry/v1\",\"currency_scale\":2}}"],"precedence_decision":"DOI_OPPORTUNITY","reason_codes":["RC-031","RC-052"],"reason_ownership":["RC-031@TR-034","RC-052@TR-060"],"reason_registry_version":"synthetic-doi-reason-registry/v1.0.1","rule_pack_binding":{"domain":"doi-rule-pack-binding/v1","sha256":"aaa63f608d57bf49a8b5eda4294ef7f32b84aee6fae956b64a4327cc7da13789"},"rules_evaluated":["ALTERNATE_HIERARCHY","CLOSURE_PRECEDENCE","DEDUPE","DIRECT_SHIP","FIELD_UNCERTAINTY_CONTAINMENT","FULFILLMENT_SPLIT","GEOGRAPHY_HANDLING","OPPORTUNITY_OVERLAP","ORDER_PROGRESSION","PARTIAL_QUANTITY","PAYMENT_HANDLING","SOURCE_RECHECK","WWC_COORDINATION"],"rules_fired":["FULFILLMENT_SPLIT","GEOGRAPHY_HANDLING"],"schema_version":"synthetic-doi-models/v1","supplied_facts":["ALTERNATE_CANDIDATES","COMPLETE_ORDER_SNAPSHOT","DEDUPE_FINDING","LINE_FACTS","PAYMENT_FACT","WWC_FINDING"],"transition_registry_version":"synthetic-doi-transition-registry/v1.0.1","unavailable_facts":[]}
```

### DOIHumanFactEvent

```text
doi-human-fact-event/v1
{"corrects_event_id":null,"event_id":"SYN-EVIDENCE-DOI-MODEL-KAT-HUMAN-EVENT","event_type":"RECORDED","fact":{"domain":"doi-structured-human-fact/v1","sha256":"414e1efaba447153fcca47d5bd2be527f0a1d0a48f5efbb5c91a69083730acc1"},"guard":{"domain":"doi-occurrence-guard/v1","sha256":"fd5cfb85dcc680671cfd4c542ae2344d604d080857869070bffb7b35485e3794"},"predecessor_binding":null,"recorded_at":"2026-08-20T14:15:16Z","schema_version":"synthetic-doi-models/v1","sequence":1,"stream_id":"SYN-EVIDENCE-DOI-MODEL-KAT-HUMAN-STREAM"}
```

### DOIHumanFactProjection

```text
doi-human-fact-projection/v1
{"current_fact":{"domain":"doi-structured-human-fact/v1","sha256":"414e1efaba447153fcca47d5bd2be527f0a1d0a48f5efbb5c91a69083730acc1"},"head_event_binding":{"domain":"doi-human-fact-event/v1","sha256":"257d9d8f370175ba43df3c0c411e9d5657d831a42156cfd450eece1ee937d2ec"},"schema_version":"synthetic-doi-models/v1","sequence":1,"stream_id":"SYN-EVIDENCE-DOI-MODEL-KAT-HUMAN-STREAM"}
```

### DOILineItemSnapshot

```text
doi-line-item-snapshot/v1
{"active_line_value":{"raw_hint":null,"reason_code":null,"tag":"KNOWN","value":{"amount":"20.00","currency_code":"USD","currency_registry_version":"synthetic-iso-style-currency-registry/v1","currency_scale":2}},"active_quantity":{"raw_hint":null,"reason_code":null,"tag":"KNOWN","value":"2"},"activity":{"raw_hint":null,"reason_code":null,"tag":"KNOWN","value":"ACTIVE"},"availability":{"raw_hint":null,"reason_code":null,"tag":"KNOWN","value":"IN_STOCK"},"canceled_quantity":{"raw_hint":null,"reason_code":null,"tag":"KNOWN","value":"0"},"continuity":{"domain":"doi-line-continuity-proof/v1","sha256":"fb63c07d70bd29fe2b081f3d42d6d0c445a7e17835e1acc01ef1a8feb8f0ad8b"},"drop_ship_state":{"raw_hint":null,"reason_code":null,"tag":"KNOWN","value":"NON_DS"},"es_number":{"raw_hint":null,"reason_code":null,"tag":"KNOWN","value":"SYN-SKU-DOI-MODEL-KAT-ES-0001"},"eta":{"raw_hint":null,"reason_code":null,"tag":"KNOWN","value":"2026-08-20T14:15:16Z"},"explicitly_available_quantity":{"raw_hint":null,"reason_code":null,"tag":"KNOWN","value":"2"},"line_sales_rep":{"raw_hint":null,"reason_code":null,"tag":"KNOWN","value":"SYN-REP-DOI-MODEL-KAT-TARGET"},"line_snapshot_id":"SYN-EVIDENCE-DOI-MODEL-KAT-LINE-0001","mfg_number":{"raw_hint":null,"reason_code":null,"tag":"KNOWN","value":"SYN-SKU-DOI-MODEL-KAT-MFG-0001"},"ordered_quantity":{"raw_hint":null,"reason_code":null,"tag":"KNOWN","value":"2"},"quantity_availability":{"raw_hint":null,"reason_code":null,"tag":"KNOWN","value":"FULL"},"relevant_merchandise":true,"schema_version":"synthetic-doi-models/v1","source":{"domain":"shared-source-ref/v1","sha256":"fb8c93cc6eaf774120a2afa382063ce5f993a02b41d51124cfd02aeaf24b6b03"},"source_ref_id":"SYN-EVIDENCE-DOI-MODEL-KAT-ORDER-SOURCE","stable_source_line_id":{"raw_hint":null,"reason_code":null,"tag":"KNOWN","value":"SYN-EVIDENCE-DOI-MODEL-KAT-STABLE-LINE-0001"},"unit_value":{"raw_hint":null,"reason_code":null,"tag":"KNOWN","value":{"amount":"10.00","currency_code":"USD","currency_registry_version":"synthetic-iso-style-currency-registry/v1","currency_scale":2}}}
```

### DOIMutualExclusionEvidence

```text
doi-mutual-exclusion-evidence/v1
{"candidate_ids":["SYN-EVIDENCE-DOI-MODEL-KAT-CANDIDATE","SYN-EVIDENCE-DOI-MODEL-KAT-CANDIDATE-OTHER"],"evidence_id":"SYN-EVIDENCE-DOI-MODEL-KAT-MUTUAL-EXCLUSION","group_id":"SYN-EVIDENCE-DOI-MODEL-KAT-SCENARIO-GROUP","human_fact":{"domain":"doi-structured-human-fact/v1","sha256":"53d3bf1450fe9177f06186dd02f91b534122731483d3ec993a033aa261599d86"},"schema_version":"synthetic-doi-models/v1"}
```

### DOIOccurrenceGuard

```text
doi-occurrence-guard/v1
{"guard_id":"SYN-EVIDENCE-DOI-MODEL-KAT-ACTION-CONTEXT-EVENT","occurrence_id":"SYN-INTERACTION-DOI-MODEL-KAT-ACTION-CONTEXT","owner_id":"SYN-EVIDENCE-DOI-MODEL-KAT-ACTION-CONTEXT","schema_version":"synthetic-doi-models/v1","source":{"domain":"shared-source-ref/v1","sha256":"d9f08d1072ac90910910d9fd8bd9deb6e52f03da23daa95e7843ba11c89479f8"}}
```

### DOIOpportunity

```text
doi-opportunity/v1
{"alternate_observation_binding":null,"human_fact_binding":null,"mutual_exclusion_group":null,"opportunity_id":"SYN-EVIDENCE-DOI-OPPORTUNITY-D35358A7D4A37AF5492A097EF576B418A7146AF40BC9547478F8F48411C3F67D","opportunity_type":"FULFILLMENT_SPLIT","potential_value":{"amount":"20.00","currency_code":"USD","currency_registry_version":"synthetic-iso-style-currency-registry/v1","currency_scale":2},"potential_value_state":"AVAILABLE","relationship_revision_binding":null,"schema_version":"synthetic-doi-models/v1","scope":{"domain":"doi-opportunity-scope/v1","sha256":"7bdd6d29317aeedaa2d87f018871f6f31431b3adc4f7906edc5614fe8a977ca6"}}
```

### DOIOpportunityIdentity

```text
doi-opportunity-id/v1
{"discriminator":"FULFILLMENT_SPLIT","evaluation_id":"SYN-EVALUATION-DOI-MODEL-KAT-0001","opportunity_type":"FULFILLMENT_SPLIT","scope_sha256":"7bdd6d29317aeedaa2d87f018871f6f31431b3adc4f7906edc5614fe8a977ca6"}
```

### DOIOpportunityScope

```text
doi-opportunity-scope/v1
{"components":[{"line_snapshot_id":"SYN-EVIDENCE-DOI-MODEL-KAT-LINE-0001","quantity":"2","role":"AVAILABLE"},{"line_snapshot_id":"SYN-EVIDENCE-DOI-MODEL-KAT-LINE-0002","quantity":"2","role":"DELAYED"}],"schema_version":"synthetic-doi-models/v1"}
```

### DOIOrderSnapshot

```text
doi-order-snapshot/v1
{"completeness_proof":{"domain":"shared-snapshot-completeness-proof/v1","sha256":"a42c55479a2e8a48c4173d4756c7f4180e2bfc14d32182c2d9d52e82594366a7"},"current_rep_relation":{"raw_hint":null,"reason_code":null,"tag":"KNOWN","value":"TARGET_REP_OWNED"},"current_rep_value":{"raw_hint":null,"reason_code":null,"tag":"KNOWN","value":"SYN-REP-DOI-MODEL-KAT-TARGET"},"dedupe_finding":{"domain":"doi-dedupe-finding/v1","sha256":"79bead83f437fc5ee09d5420cd9bc750bbc28c745abcbb318163f36a54f37173"},"geography_class":{"raw_hint":null,"reason_code":null,"tag":"KNOWN","value":"DOMESTIC_STANDARD"},"lines":[{"domain":"doi-line-item-snapshot/v1","sha256":"7cedaa9c72c6f44566a5c66ff648bb26be97670ad3bb8173a76c11a40d0d628e"},{"domain":"doi-line-item-snapshot/v1","sha256":"45f23e1898cfd92663ea8cdad68a925e685f78a73362de94573cc78a7eb42c33"}],"order_id":"SYN-ORDER-DOI-MODEL-KAT-0001","order_state":{"raw_hint":null,"reason_code":null,"tag":"KNOWN","value":"ACTIVE"},"order_total":{"raw_hint":null,"reason_code":null,"tag":"KNOWN","value":{"amount":"40.00","currency_code":"USD","currency_registry_version":"synthetic-iso-style-currency-registry/v1","currency_scale":2}},"payment_condition":{"raw_hint":null,"reason_code":null,"tag":"KNOWN","value":"NONE_OBSERVED"},"run_id":"SYN-RUN-DOI-MODEL-KAT-0001","schema_version":"synthetic-doi-models/v1","snapshot_id":"SYN-SNAPSHOT-DOI-MODEL-KAT-0001","source_observed_at":"2026-08-20T14:15:16Z","source_presence":"PRESENT","wwc_finding":{"domain":"doi-wwc-finding/v1","sha256":"205155bfa56ccc89f854f5a7ac7d33cc17fa7bc40cf284a35770443b4f6672e7"}}
```

### DOIRulePackBinding

```text
doi-rule-pack-binding/v1
{"model_schema_version":"synthetic-doi-models/v1","overlap_policy":"PRESERVE_SEPARATE_OPPORTUNITIES_AND_WITHHOLD_ONLY_AGGREGATE_POTENTIAL","rule_pack_version":"synthetic-doi-rule-pack/v1","tr_037_policy":"USE_ONLY_WHEN_NO_SAFE_OPPORTUNITY_OR_OTHER_HIGHER_PRECEDENCE_RESULT_IS_PROVABLE","uncertainty_containment_policy":"PRESERVE_INDEPENDENTLY_PROVEN_OPPORTUNITIES"}
```

### DOIWWCEvent

```text
doi-wwc-event/v1
{"corrects_event_id":null,"event_id":"SYN-EVIDENCE-DOI-MODEL-KAT-WWC-EVENT","event_type":"OBSERVED","finding":{"domain":"doi-wwc-finding/v1","sha256":"205155bfa56ccc89f854f5a7ac7d33cc17fa7bc40cf284a35770443b4f6672e7"},"guard":{"domain":"doi-occurrence-guard/v1","sha256":"7afe818c5e6e894286628449115035e60af2ff8cb481e4d706d0f6619c997870"},"order_id":"SYN-ORDER-DOI-MODEL-KAT-0001","predecessor_binding":null,"recorded_at":"2026-08-20T14:15:16Z","schema_version":"synthetic-doi-models/v1","sequence":1,"stream_id":"SYN-EVIDENCE-DOI-MODEL-KAT-WWC-STREAM"}
```

### DOIWWCProjection

```text
doi-wwc-projection/v1
{"current_finding":{"domain":"doi-wwc-finding/v1","sha256":"205155bfa56ccc89f854f5a7ac7d33cc17fa7bc40cf284a35770443b4f6672e7"},"head_event_binding":{"domain":"doi-wwc-event/v1","sha256":"ccdda993af80573ef74b43ef69734ffc49763c2fa96e06557047ae12dbbb739e"},"order_id":"SYN-ORDER-DOI-MODEL-KAT-0001","schema_version":"synthetic-doi-models/v1","sequence":1,"state":"NOT_APPLICABLE","stream_id":"SYN-EVIDENCE-DOI-MODEL-KAT-WWC-STREAM"}
```

### DedupeFinding

```text
doi-dedupe-finding/v1
{"finding_id":"SYN-EVIDENCE-DOI-MODEL-KAT-DEDUPE-PRESENT-FINDING","observed_at":"2026-08-20T14:15:16Z","presence":"PRESENT","schema_version":"synthetic-doi-models/v1","source":{"domain":"shared-source-ref/v1","sha256":"fb8c93cc6eaf774120a2afa382063ce5f993a02b41d51124cfd02aeaf24b6b03"},"state":"SOURCE_PRESENT"}
```

### DedupeVerificationFact

```text
doi-dedupe-verification-fact/v1
{"approved_at":"2026-08-20T14:15:16Z","approved_human_fact_binding":{"domain":"doi-structured-human-fact/v1","sha256":"38c5989c0e43ca8f4991b1c41e6e1340fa5741b8b3a6d00519c9291a106949e6"},"order_id":"SYN-ORDER-DOI-MODEL-KAT-0001","prior_finding":{"domain":"doi-dedupe-finding/v1","sha256":"0b23e9bd5349394b2877faef415bc8c50a7500143964625798597cf79098c89c"},"prior_projection_binding":{"domain":"doi-dedupe-projection/v1","sha256":"274c79464cdf7671a59b321edce53a11e4f2a3332b8b8fb314485491b1395301"},"prior_snapshot":{"domain":"doi-order-snapshot/v1","sha256":"1cd752bc844b078a920f2072880b5265e02562a94a48dc29294ef03b7f770c80"},"schema_version":"synthetic-doi-models/v1","verification_id":"SYN-EVIDENCE-DOI-MODEL-KAT-DEDUPE-VERIFY","verified_finding":{"domain":"doi-dedupe-finding/v1","sha256":"c0ec7911d0e3ff489878f79cc327a3d66aa2b946a6a6524a691f011c140fe37e"},"verified_snapshot":{"domain":"doi-order-snapshot/v1","sha256":"65593d421e4757511364035ce0f2547c81759a4cbd546c8d7c65159fc19668ae"},"verified_source_observed_at":"2026-08-20T14:15:17Z"}
```

### HumanAuthorityGrant

```text
doi-human-authority-grant/v1
{"action_context_binding":{"domain":"doi-action-context/v1","sha256":"8ca679e9716d0d784a3c6bcc96b5c443b4e165882042a456ab46d3a46bfe3dec"},"action_context_id":"SYN-EVIDENCE-DOI-MODEL-KAT-ACTION-CONTEXT","actor":"SYN-REP-DOI-MODEL-KAT-AUTHORIZED","grant_id":"SYN-EVIDENCE-DOI-MODEL-KAT-AUTHORITY","granted_at":"2026-08-20T14:15:16Z","schema_version":"synthetic-doi-models/v1","source":{"domain":"shared-source-ref/v1","sha256":"d9f08d1072ac90910910d9fd8bd9deb6e52f03da23daa95e7843ba11c89479f8"}}
```

### LineContinuityProof

```text
doi-line-continuity-proof/v1
{"composite_binding":null,"proof_type":"STABLE_SOURCE_LINE_ID","schema_version":"synthetic-doi-models/v1","stable_source_line_id":"SYN-EVIDENCE-DOI-MODEL-KAT-STABLE-LINE-0001","state":"VERIFIED"}
```

### StructuredHumanFact

```text
doi-structured-human-fact/v1
{"action_context":{"domain":"doi-action-context/v1","sha256":"8ca679e9716d0d784a3c6bcc96b5c443b4e165882042a456ab46d3a46bfe3dec"},"action_context_id":"SYN-EVIDENCE-DOI-MODEL-KAT-ACTION-CONTEXT","actor":"SYN-REP-DOI-MODEL-KAT-AUTHORIZED","authority_grant":{"domain":"doi-human-authority-grant/v1","sha256":"12ec90eb11853e762332b6f943b8aae738b1d8af26f819a5f331d78c10488caf"},"evaluation_id":"SYN-EVALUATION-DOI-MODEL-KAT-0001","fact_id":"SYN-EVIDENCE-DOI-MODEL-KAT-HUMAN-FACT","occurred_at":"2026-08-20T14:15:16Z","order_id":"SYN-ORDER-DOI-MODEL-KAT-0001","result_code":"APPROVED","schema_version":"synthetic-doi-models/v1","source":{"domain":"shared-source-ref/v1","sha256":"d9f08d1072ac90910910d9fd8bd9deb6e52f03da23daa95e7843ba11c89479f8"},"usage_kind":"NO_ACTION_DECISION"}
```

### WWCFinding

```text
doi-wwc-finding/v1
{"author_relation":{"raw_hint":null,"reason_code":null,"tag":"NOT_APPLICABLE","value":null},"finding_id":"SYN-EVIDENCE-DOI-MODEL-KAT-WWC-FINDING","marker":{"raw_hint":null,"reason_code":null,"tag":"NOT_APPLICABLE","value":null},"observed_at":{"raw_hint":null,"reason_code":null,"tag":"NOT_APPLICABLE","value":null},"presence":"NOT_PRESENT","schema_version":"synthetic-doi-models/v1","source":{"domain":"shared-source-ref/v1","sha256":"fb8c93cc6eaf774120a2afa382063ce5f993a02b41d51124cfd02aeaf24b6b03"},"timing_state":{"raw_hint":null,"reason_code":null,"tag":"NOT_APPLICABLE","value":null}}
```

### DOIAlternateObservation

```text
doi-alternate-observation/v1
{"action_context_binding":{"domain":"doi-action-context/v1","sha256":"8ca679e9716d0d784a3c6bcc96b5c443b4e165882042a456ab46d3a46bfe3dec"},"action_context_id":"SYN-EVIDENCE-DOI-MODEL-KAT-ACTION-CONTEXT","candidate_sku":"SYN-SKU-DOI-KNOWLEDGE-KAT-CANDIDATE","observation_id":"SYN-EVIDENCE-DOI-KNOWLEDGE-KAT-OBSERVATION","observed_at":"2026-08-20T14:15:16Z","observed_availability":{"raw_hint":null,"reason_code":null,"tag":"KNOWN","value":"IN_STOCK"},"observed_eta":{"raw_hint":null,"reason_code":null,"tag":"NOT_APPLICABLE","value":null},"observed_price":{"raw_hint":null,"reason_code":null,"tag":"KNOWN","value":{"amount":"10.00","currency_code":"USD","currency_registry_version":"synthetic-iso-style-currency-registry/v1","currency_scale":2}},"relationship_revision_binding":{"domain":"doi-alternate-relationship-revision/v1","sha256":"ecaa862cf7ff89ef1f42ab36c66a3b59a5b25e16826c9c709f99fa418f496bdb"},"schema_version":"synthetic-doi-models/v1","source":{"domain":"shared-source-ref/v1","sha256":"a9a70300ecc64dcd7dbffb4f5affa56a1a9774c1f1e74a95b8199b834a5a3198"},"state":"CURRENT"}
```

### DOIAlternateRelationship

```text
doi-alternate-relationship/v1
{"candidate_sku":"SYN-SKU-DOI-KNOWLEDGE-KAT-CANDIDATE","ordered_sku":"SYN-SKU-DOI-KNOWLEDGE-KAT-ORDERED","relationship_id":"SYN-EVIDENCE-DOI-KNOWLEDGE-KAT-RELATIONSHIP","relationship_type":"EXACT_MFG","revision_bindings":[{"domain":"doi-alternate-relationship-revision/v1","sha256":"ecaa862cf7ff89ef1f42ab36c66a3b59a5b25e16826c9c709f99fa418f496bdb"}],"schema_version":"synthetic-doi-models/v1"}
```

### DOIAlternateRelationshipRevision

```text
doi-alternate-relationship-revision/v1
{"candidate_mfg":"SYN-SKU-DOI-KNOWLEDGE-KAT-MFG","candidate_sku":"SYN-SKU-DOI-KNOWLEDGE-KAT-CANDIDATE","compatibility_review_required":false,"evidence_source":{"domain":"shared-source-ref/v1","sha256":"a9a70300ecc64dcd7dbffb4f5affa56a1a9774c1f1e74a95b8199b834a5a3198"},"ordered_mfg":"SYN-SKU-DOI-KNOWLEDGE-KAT-MFG","ordered_sku":"SYN-SKU-DOI-KNOWLEDGE-KAT-ORDERED","predecessor_binding":null,"relationship_id":"SYN-EVIDENCE-DOI-KNOWLEDGE-KAT-RELATIONSHIP","relationship_type":"EXACT_MFG","revision_id":"SYN-EVIDENCE-DOI-KNOWLEDGE-KAT-REVISION","revision_kind":"CREATED","revision_number":1,"schema_version":"synthetic-doi-models/v1","state":"ACTIVE"}
```

### DOIExactSKUObservation

```text
doi-exact-sku-observation/v1
{"action_context_binding":{"domain":"doi-action-context/v1","sha256":"8ca679e9716d0d784a3c6bcc96b5c443b4e165882042a456ab46d3a46bfe3dec"},"action_context_id":"SYN-EVIDENCE-DOI-MODEL-KAT-ACTION-CONTEXT","observation_id":"SYN-EVIDENCE-DOI-KNOWLEDGE-KAT-EXACT-OBSERVATION","observed_at":"2026-08-20T14:15:16Z","observed_availability":"IN_STOCK","observed_sku":"SYN-SKU-DOI-KNOWLEDGE-KAT-ORDERED","ordered_line_id":"SYN-EVIDENCE-DOI-KNOWLEDGE-KAT-LINE","ordered_sku":"SYN-SKU-DOI-KNOWLEDGE-KAT-ORDERED","potential_unit_value":{"amount":"10.00","currency_code":"USD","currency_registry_version":"synthetic-iso-style-currency-registry/v1","currency_scale":2},"schema_version":"synthetic-doi-models/v1","source":{"domain":"shared-source-ref/v1","sha256":"877d91b9923ef3f320afce10a027d139ec3c8e96323a79cd7d053aec6590337d"},"state":"CURRENT"}
```

### TransitionGuardAuthorityEvidence

```text
doi-transition-guard-authority/v1
{"authority_schema_version":"doi-transition-guard-authority/v1","evidence":{"fixture":"CLOSED_REGISTRY_STRUCTURAL_COVERAGE","transition_id":"TR-044"},"evidence_kind":"SYNTHETIC_REGISTRY_FIXTURE","guard_facts_binding":{"domain":"doi-transition-guard-facts/v1","sha256":"1777316431e6df212b063b28072de3d32d7a1a9580daed4d4752d4c1d019ea4f"},"issuer":"SYNTHETIC_FIXTURE","occurrence_id":"SYN-EVIDENCE-EVENT-TR-044","satisfied_at":"2026-08-20T12:00:00Z","stream_id":"SYN-EVIDENCE-STREAM-TR-044","transition_id":"TR-044"}
```

### TransitionGuardFacts

```text
doi-transition-guard-facts/v1
{"completed_human_action_proved":true,"deterministic_system_action_proof":true,"scope_time_key_fingerprint_exact":true}
```

### TransitionGuardProof

```text
doi-transition-guard-proof/v1
{"authority_evidence_binding":{"domain":"doi-transition-guard-authority/v1","sha256":"1e1408766286dec56779ae789456a87a89fc10a72befb2f37c3c891b39916ae7"},"from_state":"NONEXISTENT","guard_fact_schema_version":"doi-transition-guard-fact-schema/v1","guard_facts":{"completed_human_action_proved":true,"deterministic_system_action_proof":true,"scope_time_key_fingerprint_exact":true},"guard_facts_binding":{"domain":"doi-transition-guard-facts/v1","sha256":"1777316431e6df212b063b28072de3d32d7a1a9580daed4d4752d4c1d019ea4f"},"registered_guard":"Deterministic system proof of completed human action; exact scope/time/natural key/fingerprint validates","required_effects":"Append typed action-verification event, invoke TR-106, and project one SYSTEM_VERIFIED intervention; identical evidence no-op","required_guard_facts":["deterministic_system_action_proof","completed_human_action_proved","scope_time_key_fingerprint_exact"],"schema_version":"doi-lifecycle/v1","section":"10. DOIIntervention and value projection","to_state":"VERIFIED","transition_id":"TR-044","transition_registry_version":"synthetic-doi-transition-registry/v1.0.1","verdict":"SATISFIED"}
```

### TransitionCommand

```text
doi-transition-command/v1
{"current_state":"NONEXISTENT","expected_predecessor_sha256":null,"expected_sequence":1,"guard_proof":{"authority_evidence_binding":{"domain":"doi-transition-guard-authority/v1","sha256":"1e1408766286dec56779ae789456a87a89fc10a72befb2f37c3c891b39916ae7"},"from_state":"NONEXISTENT","guard_fact_schema_version":"doi-transition-guard-fact-schema/v1","guard_facts":{"completed_human_action_proved":true,"deterministic_system_action_proof":true,"scope_time_key_fingerprint_exact":true},"guard_facts_binding":{"domain":"doi-transition-guard-facts/v1","sha256":"1777316431e6df212b063b28072de3d32d7a1a9580daed4d4752d4c1d019ea4f"},"registered_guard":"Deterministic system proof of completed human action; exact scope/time/natural key/fingerprint validates","required_effects":"Append typed action-verification event, invoke TR-106, and project one SYSTEM_VERIFIED intervention; identical evidence no-op","required_guard_facts":["deterministic_system_action_proof","completed_human_action_proved","scope_time_key_fingerprint_exact"],"schema_version":"doi-lifecycle/v1","section":"10. DOIIntervention and value projection","to_state":"VERIFIED","transition_id":"TR-044","transition_registry_version":"synthetic-doi-transition-registry/v1.0.1","verdict":"SATISFIED"},"guard_proof_binding":{"domain":"doi-transition-guard-proof/v1","sha256":"0a6193d2e62407d923ba7a65b8f6cece8a3e54219825e1c97438694f8e745948"},"occurrence_id":"SYN-EVIDENCE-EVENT-TR-044","reasons":[],"schema_version":"doi-lifecycle/v1","stream_id":"SYN-EVIDENCE-STREAM-TR-044","transition_id":"TR-044","transition_registry_version":"synthetic-doi-transition-registry/v1.0.1"}
```

### TransitionEvent

```text
doi-lifecycle-event/v1
{"command":{"domain":"doi-transition-command/v1","sha256":"333df15aa867ffaedc5a83b3fa1b485d0a16f7b98d90d462d25e823663bd90a8"},"event_id":"SYN-EVIDENCE-EVENT-TR-044","from_state":"NONEXISTENT","occurred_at":"2026-08-20T12:00:00Z","predecessor_sha256":null,"reasons":[],"schema_version":"doi-lifecycle/v1","sequence":1,"stream_id":"SYN-EVIDENCE-STREAM-TR-044","to_state":"VERIFIED","transition_id":"TR-044","transition_registry_version":"synthetic-doi-transition-registry/v1.0.1"}
```

### AttentionEvent

```text
doi-attention-event/v1
{"action":"SET","active_set_event_id":null,"case_id":"SYN-EVIDENCE-KAT-ATTENTION-CASE","cause_key":"SYN-EVIDENCE-KAT-ATTENTION-CAUSE","condition":"RECHECK_REQUIRED","event_id":"SYN-EVIDENCE-KAT-ATTENTION-EVENT","occurred_at":"2026-08-20T12:00:00Z","resolver_id":null,"schema_version":"doi-attention-event/v1","transition_id":"TR-020"}
```

### ActionVerificationEvent

```text
doi-action-verification-event/v1
{"event_id":"SYN-EVIDENCE-DOI-INTERVENTION-KAT-ACTION-EVENT","evidence":{"domain":"doi-verification-evidence/v1","sha256":"635906a600e061798d1b8804f7b479c3248c2e61cbcbd8b7d97ac7141b9ad992"},"intervention_id":"SYN-EVIDENCE-DOI-INTERVENTION-KAT","intervention_type":"FULFILLMENT_SPLIT","key":{"domain":"doi-logical-evidence-key/v1","sha256":"5731825247b8b7b96b19e4b5ea601758bbf0e8c858341ba36ad925b31c2d66e0"},"opportunity_id":"SYN-EVIDENCE-DOI-OPPORTUNITY-D35358A7D4A37AF5492A097EF576B418A7146AF40BC9547478F8F48411C3F67D","schema_version":"doi-intervention-history/v1"}
```

### ActionVerificationMaterial

```text
doi-action-verification-material/v1
{"action_context_binding":{"domain":"doi-action-context/v1","sha256":"1554efa8e05249d87018388082d4f3292014bc3f2ec042c96cef8bf08e04e253"},"action_context_id":"SYN-EVIDENCE-DOI-MODEL-KAT-ACTION-CONTEXT","authority_binding":null,"evidence_id":"SYN-EVIDENCE-DOI-INTERVENTION-KAT-ACTION-PROOF","intervention_id":"SYN-EVIDENCE-DOI-INTERVENTION-KAT","intervention_type":"FULFILLMENT_SPLIT","occurred_at":"2026-08-20T14:16:00Z","opportunity_id":"SYN-EVIDENCE-DOI-OPPORTUNITY-D35358A7D4A37AF5492A097EF576B418A7146AF40BC9547478F8F48411C3F67D","schema_version":"doi-intervention-history/v1","source":{"domain":"shared-source-ref/v1","sha256":"8473561fedb6b4c5e7486a0531ea3d0d71b0391ef5ea8386da87046435b8afa3"},"verification":"SYSTEM_VERIFIED"}
```

### AuthorizedHumanExactValueRecord

```text
doi-authorized-human-exact-value-record/v1
{"amount":{"amount":"12.34","currency_code":"USD","currency_registry_version":"synthetic-iso-style-currency-registry/v1","currency_scale":2},"correction_kind":"ORIGINAL_VALUE_CORRECTED","event_type":"CORRECTION","human_fact_binding":{"domain":"doi-structured-human-fact/v1","sha256":"af32467cc4ac0e7adeda93749e8972896a14cb9212fc246d24d89c647831105b"},"human_fact_event_binding":{"domain":"doi-human-fact-event/v1","sha256":"fda231756f7bfa4a8eb3434110d2e0d519b1f4d8292d019456f41722c43c550a"},"intervention_action_binding":{"domain":"doi-action-verification-event/v1","sha256":"acc8473252ca010d492d79441854ce6b6364d2d660387478d4b3cd82e170cfc5"},"intervention_id":"SYN-EVIDENCE-DOI-INTERVENTION-KAT","occurred_at":"2026-08-20T14:15:17Z","predecessor_event_binding":{"domain":"doi-value-event/v1","sha256":"8a5b9a46f910160655c3d67d0bc3240d6f407dc44dd854e8b4e9e3d7edab8e66"},"predecessor_event_id":"SYN-EVIDENCE-DOI-INTERVENTION-KAT-VALUE-EVENT","record_id":"SYN-EVIDENCE-DOI-INTERVENTION-KAT-HUMAN-VALUE-RECORD","schema_version":"doi-intervention-history/v1","source":{"domain":"shared-source-ref/v1","sha256":"d9e49ef1121780a891426e160175ed7d51c08f2ee1163cf02808f990908011a7"},"subject_order_id":"SYN-ORDER-DOI-MODEL-KAT-0001"}
```

### AuthorizedHumanResultingLinkEvidence

```text
doi-authorized-human-resulting-link-evidence/v1
{"child_order_id":"SYN-ORDER-DOI-INTERVENTION-KAT-CHILD","evidence_id":"SYN-EVIDENCE-DOI-INTERVENTION-KAT-LINK-HUMAN-EVIDENCE","human_fact_binding":{"domain":"doi-structured-human-fact/v1","sha256":"af32467cc4ac0e7adeda93749e8972896a14cb9212fc246d24d89c647831105b"},"human_fact_event_binding":{"domain":"doi-human-fact-event/v1","sha256":"fda231756f7bfa4a8eb3434110d2e0d519b1f4d8292d019456f41722c43c550a"},"intervention_action_binding":{"domain":"doi-action-verification-event/v1","sha256":"acc8473252ca010d492d79441854ce6b6364d2d660387478d4b3cd82e170cfc5"},"intervention_id":"SYN-EVIDENCE-DOI-INTERVENTION-KAT","intervention_type":"FULFILLMENT_SPLIT","link_id":"SYN-EVIDENCE-DOI-INTERVENTION-KAT-LINK","mappings":[{"child_line_id":"SYN-EVIDENCE-DOI-INTERVENTION-KAT-CHILD-LINE-0001","parent_line_id":"SYN-EVIDENCE-DOI-MODEL-KAT-LINE-0001","quantity":"1","replacement_line_target_rep_proof":null},{"child_line_id":"SYN-EVIDENCE-DOI-INTERVENTION-KAT-CHILD-LINE-0002","parent_line_id":"SYN-EVIDENCE-DOI-MODEL-KAT-LINE-0002","quantity":"1","replacement_line_target_rep_proof":null}],"observed_at":"2026-08-20T14:15:17Z","parent_order_id":"SYN-ORDER-DOI-MODEL-KAT-0001","predecessor_revision_binding":{"domain":"doi-resulting-order-link-revision/v1","sha256":"d3fea5803855fa73794f90988e6152fc39b0b5e4a3ea9c2fd67df7f164f2e45d"},"resolves_conflict_binding":null,"resulting_order_target_rep_proof":{"domain":"doi-target-rep-verification-proof/v1","sha256":"d9ec0e137fe883455a4d67dc236b0c2e578e7ba06aae4161b749b0f7fa4df559"},"schema_version":"doi-intervention-history/v1","source":{"domain":"shared-source-ref/v1","sha256":"d9e49ef1121780a891426e160175ed7d51c08f2ee1163cf02808f990908011a7"}}
```

### DOIIntervention

```text
doi-intervention/v1
{"action_event_hashes":[{"domain":"doi-action-verification-event/v1","sha256":"acc8473252ca010d492d79441854ce6b6364d2d660387478d4b3cd82e170cfc5"}],"action_occurred_at":"2026-08-20T14:16:00Z","action_verification":"SYSTEM_VERIFIED","intervention_id":"SYN-EVIDENCE-DOI-INTERVENTION-KAT","intervention_type":"FULFILLMENT_SPLIT","opportunity_id":"SYN-EVIDENCE-DOI-OPPORTUNITY-D35358A7D4A37AF5492A097EF576B418A7146AF40BC9547478F8F48411C3F67D","schema_version":"doi-intervention-history/v1","status":"VERIFIED_ACTIVE","value":{"authoritative_event_id":"SYN-EVIDENCE-DOI-INTERVENTION-KAT-VALUE-EVENT","authoritative_original":{"amount":"12.34","currency_code":"USD","currency_registry_version":"synthetic-iso-style-currency-registry/v1","currency_scale":2},"net_value":{"amount":"12.34","currency_code":"USD","currency_registry_version":"synthetic-iso-style-currency-registry/v1","currency_scale":2},"reversed_value":{"amount":"0.00","currency_code":"USD","currency_registry_version":"synthetic-iso-style-currency-registry/v1","currency_scale":2},"verification":"SYSTEM_VERIFIED"},"value_event_hashes":[{"domain":"doi-value-event/v1","sha256":"8a5b9a46f910160655c3d67d0bc3240d6f407dc44dd854e8b4e9e3d7edab8e66"}]}
```

### DOIResultingOrderLink

```text
doi-resulting-order-link/v1
{"child_order_id":"SYN-ORDER-DOI-INTERVENTION-KAT-CHILD","intervention_action_binding":{"domain":"doi-action-verification-event/v1","sha256":"acc8473252ca010d492d79441854ce6b6364d2d660387478d4b3cd82e170cfc5"},"intervention_id":"SYN-EVIDENCE-DOI-INTERVENTION-KAT","intervention_type":"FULFILLMENT_SPLIT","link_id":"SYN-EVIDENCE-DOI-INTERVENTION-KAT-LINK","parent_order_id":"SYN-ORDER-DOI-MODEL-KAT-0001","resulting_order_target_rep_proof":{"domain":"doi-target-rep-verification-proof/v1","sha256":"d9ec0e137fe883455a4d67dc236b0c2e578e7ba06aae4161b749b0f7fa4df559"},"revision_hashes":[{"domain":"doi-resulting-order-link-revision/v1","sha256":"d3fea5803855fa73794f90988e6152fc39b0b5e4a3ea9c2fd67df7f164f2e45d"}],"schema_version":"doi-intervention-history/v1","state":"AUTO_LINKED"}
```

### DOIResultingOrderLinkSearch

```text
doi-resulting-order-link-search/v1
{"candidate_order_ids":[],"head_event_binding":{"domain":"doi-resulting-link-search-event/v1","sha256":"0493447868bf2a839bd8f683c08df13bf264b90eba0b60839adee14c4c8ec8bc"},"intervention_type":"FULFILLMENT_SPLIT","parent_order_id":"SYN-ORDER-DOI-MODEL-KAT-0001","revision":1,"schema_version":"doi-intervention-history/v1","search_id":"SYN-EVIDENCE-DOI-INTERVENTION-KAT-LINK-SEARCH","state":"NOT_FOUND"}
```

### LogicalEvidenceKey

```text
doi-logical-evidence-key/v1
{"key_id":"SYN-EVIDENCE-DOI-INTERVENTION-KAT-ACTION-KEY","kind":"ACTION","occurrence_id":"SYN-EVIDENCE-DOI-INTERVENTION-KAT-ACTION-PROOF","owner_id":"SYN-EVIDENCE-DOI-INTERVENTION-KAT","schema_version":"doi-intervention-history/v1"}
```

### ResultingLinkSearchEvent

```text
doi-resulting-link-search-event/v1
{"event_id":"SYN-EVIDENCE-DOI-INTERVENTION-KAT-LINK-SEARCH-EVENT","evidence":{"domain":"doi-resulting-link-search-evidence/v1","sha256":"0e6e1c8ee88dd8c9f4940e42474fbe9265c91cae6bec1464c9367cf28ac7c9cf"},"predecessor_binding":null,"schema_version":"doi-intervention-history/v1","search_id":"SYN-EVIDENCE-DOI-INTERVENTION-KAT-LINK-SEARCH","sequence":1}
```

### ResultingLinkSearchEvidence

```text
doi-resulting-link-search-evidence/v1
{"candidate_order_ids":[],"disproved_candidate_order_ids":[],"evidence_id":"SYN-EVIDENCE-DOI-INTERVENTION-KAT-LINK-SEARCH-EVIDENCE","intervention_type":"FULFILLMENT_SPLIT","observed_at":"2026-08-20T14:18:00Z","parent_order_id":"SYN-ORDER-DOI-MODEL-KAT-0001","schema_version":"doi-intervention-history/v1","search_id":"SYN-EVIDENCE-DOI-INTERVENTION-KAT-LINK-SEARCH","source":{"domain":"shared-source-ref/v1","sha256":"8473561fedb6b4c5e7486a0531ea3d0d71b0391ef5ea8386da87046435b8afa3"}}
```

### ResultingOrderLinkRevision

```text
doi-resulting-order-link-revision/v1
{"evidence":{"domain":"doi-system-resulting-link-evidence/v1","sha256":"041a77cde24768af55739e918e0ad307e7e17f05927ded839d9f0945cbcb3dc3"},"intervention_action_binding":{"domain":"doi-action-verification-event/v1","sha256":"acc8473252ca010d492d79441854ce6b6364d2d660387478d4b3cd82e170cfc5"},"intervention_id":"SYN-EVIDENCE-DOI-INTERVENTION-KAT","intervention_type":"FULFILLMENT_SPLIT","link_id":"SYN-EVIDENCE-DOI-INTERVENTION-KAT-LINK","mappings":[{"child_line_id":"SYN-EVIDENCE-DOI-INTERVENTION-KAT-CHILD-LINE-0001","parent_line_id":"SYN-EVIDENCE-DOI-MODEL-KAT-LINE-0001","quantity":"1","replacement_line_target_rep_proof":null},{"child_line_id":"SYN-EVIDENCE-DOI-INTERVENTION-KAT-CHILD-LINE-0002","parent_line_id":"SYN-EVIDENCE-DOI-MODEL-KAT-LINE-0002","quantity":"1","replacement_line_target_rep_proof":null}],"predecessor_sha256":null,"resulting_order_target_rep_proof":{"domain":"doi-target-rep-verification-proof/v1","sha256":"d9ec0e137fe883455a4d67dc236b0c2e578e7ba06aae4161b749b0f7fa4df559"},"revision":1,"revision_id":"SYN-EVIDENCE-DOI-INTERVENTION-KAT-LINK-REVISION","schema_version":"doi-intervention-history/v1","state":"AUTO_LINKED"}
```

### SystemExactValueRecord

```text
doi-system-exact-value-record/v1
{"action_context_binding":{"domain":"doi-action-context/v1","sha256":"1554efa8e05249d87018388082d4f3292014bc3f2ec042c96cef8bf08e04e253"},"amount":{"amount":"12.34","currency_code":"USD","currency_registry_version":"synthetic-iso-style-currency-registry/v1","currency_scale":2},"correction_kind":null,"event_type":"INITIAL_VERIFIED_VALUE","intervention_action_binding":{"domain":"doi-action-verification-event/v1","sha256":"acc8473252ca010d492d79441854ce6b6364d2d660387478d4b3cd82e170cfc5"},"intervention_id":"SYN-EVIDENCE-DOI-INTERVENTION-KAT","observed_at":"2026-08-20T14:16:01Z","predecessor_event_binding":null,"predecessor_event_id":null,"record_id":"SYN-EVIDENCE-DOI-INTERVENTION-KAT-VALUE-RECORD","schema_version":"doi-intervention-history/v1","source":{"domain":"shared-source-ref/v1","sha256":"8473561fedb6b4c5e7486a0531ea3d0d71b0391ef5ea8386da87046435b8afa3"},"subject_order_id":"SYN-ORDER-DOI-MODEL-KAT-0001"}
```

### SystemResultingLinkEvidence

```text
doi-system-resulting-link-evidence/v1
{"child_order_id":"SYN-ORDER-DOI-INTERVENTION-KAT-CHILD","evidence_id":"SYN-EVIDENCE-DOI-INTERVENTION-KAT-LINK-SYSTEM-EVIDENCE","intervention_action_binding":{"domain":"doi-action-verification-event/v1","sha256":"acc8473252ca010d492d79441854ce6b6364d2d660387478d4b3cd82e170cfc5"},"intervention_id":"SYN-EVIDENCE-DOI-INTERVENTION-KAT","intervention_type":"FULFILLMENT_SPLIT","link_id":"SYN-EVIDENCE-DOI-INTERVENTION-KAT-LINK","mappings":[{"child_line_id":"SYN-EVIDENCE-DOI-INTERVENTION-KAT-CHILD-LINE-0001","parent_line_id":"SYN-EVIDENCE-DOI-MODEL-KAT-LINE-0001","quantity":"1","replacement_line_target_rep_proof":null},{"child_line_id":"SYN-EVIDENCE-DOI-INTERVENTION-KAT-CHILD-LINE-0002","parent_line_id":"SYN-EVIDENCE-DOI-MODEL-KAT-LINE-0002","quantity":"1","replacement_line_target_rep_proof":null}],"observed_at":"2026-08-20T14:17:00Z","parent_order_id":"SYN-ORDER-DOI-MODEL-KAT-0001","predecessor_revision_binding":null,"resolves_conflict_binding":null,"resulting_order_target_rep_proof":{"domain":"doi-target-rep-verification-proof/v1","sha256":"d9ec0e137fe883455a4d67dc236b0c2e578e7ba06aae4161b749b0f7fa4df559"},"schema_version":"doi-intervention-history/v1","source":{"domain":"shared-source-ref/v1","sha256":"2fdc3e4bfc7f3fdad6d2a9a907cd2cd5d0347b6edc56a97377317a93d255e0f3"}}
```

### TargetRepObservation

```text
doi-target-rep-observation/v1
{"intervention_action_binding":{"domain":"doi-action-verification-event/v1","sha256":"acc8473252ca010d492d79441854ce6b6364d2d660387478d4b3cd82e170cfc5"},"intervention_id":"SYN-EVIDENCE-DOI-INTERVENTION-KAT","intervention_type":"FULFILLMENT_SPLIT","link_id":"SYN-EVIDENCE-DOI-INTERVENTION-KAT-LINK","observation_id":"SYN-EVIDENCE-DOI-INTERVENTION-KAT-REP-OBSERVATION","observed_at":"2026-08-20T14:17:00Z","observed_relation":"TARGET_REP_OWNED","observed_rep_id":"SYN-REP-TARGET-REP","schema_version":"doi-intervention-history/v1","scope":"RESULTING_ORDER","source":{"domain":"shared-source-ref/v1","sha256":"2fdc3e4bfc7f3fdad6d2a9a907cd2cd5d0347b6edc56a97377317a93d255e0f3"},"subject_line_id":null,"subject_order_id":"SYN-ORDER-DOI-INTERVENTION-KAT-CHILD"}
```

### TargetRepVerificationProof

```text
doi-target-rep-verification-proof/v1
{"intervention_action_binding":{"domain":"doi-action-verification-event/v1","sha256":"acc8473252ca010d492d79441854ce6b6364d2d660387478d4b3cd82e170cfc5"},"intervention_id":"SYN-EVIDENCE-DOI-INTERVENTION-KAT","intervention_type":"FULFILLMENT_SPLIT","link_id":"SYN-EVIDENCE-DOI-INTERVENTION-KAT-LINK","observation":{"domain":"doi-target-rep-observation/v1","sha256":"e866d7aabeaef21336428f5c405ef38a6b23969759ad2624af42d279a873c303"},"observed_relation":"TARGET_REP_OWNED","observed_rep_id":"SYN-REP-TARGET-REP","proof_id":"SYN-EVIDENCE-DOI-INTERVENTION-KAT-REP-PROOF","schema_version":"doi-intervention-history/v1","scope":"RESULTING_ORDER","source":{"domain":"shared-source-ref/v1","sha256":"2fdc3e4bfc7f3fdad6d2a9a907cd2cd5d0347b6edc56a97377317a93d255e0f3"},"subject_line_id":null,"subject_order_id":"SYN-ORDER-DOI-INTERVENTION-KAT-CHILD","verified_at":"2026-08-20T14:17:00Z"}
```

### ValueEvent

```text
doi-value-event/v1
{"amount":{"amount":"12.34","currency_code":"USD","currency_registry_version":"synthetic-iso-style-currency-registry/v1","currency_scale":2},"correction_kind":null,"event_id":"SYN-EVIDENCE-DOI-INTERVENTION-KAT-VALUE-EVENT","event_type":"INITIAL_VERIFIED_VALUE","evidence":{"domain":"doi-system-exact-value-record/v1","sha256":"dd3a9b2602334397f3602b074bd96975dbe41cb6cdf292d136ce3f37c6c1756a"},"exact":true,"intervention_id":"SYN-EVIDENCE-DOI-INTERVENTION-KAT","key":{"domain":"doi-logical-evidence-key/v1","sha256":"d38b84a50d3cf0ce9008ea2a35d455f217fc70d2029245cc9642924acc443c01"},"occurred_at":"2026-08-20T14:16:01Z","predecessor_event_binding":null,"predecessor_event_id":null,"schema_version":"doi-intervention-history/v1","verification":"SYSTEM_VERIFIED"}
```

### VerificationEvidence

```text
doi-verification-evidence/v1
{"material":{"domain":"doi-action-verification-material/v1","sha256":"b017fe0c6083e0157d02f27657c9bb751c6bd34a2bce090e3e187f48040875ff"},"schema_version":"doi-intervention-history/v1"}
```

### KPIContributionEvent

```text
doi-kpi-contribution-event/v1
{"action_date":"2026-08-20","action_occurred_at":"2026-08-20T14:16:00Z","current_value":{"amount":"12.34","currency_code":"USD","currency_registry_version":"synthetic-iso-style-currency-registry/v1","currency_scale":2},"event_id":"SYN-EVIDENCE-KAT-RETENTION-KPI-EVENT","intervention_action_binding":{"domain":"doi-action-verification-event/v1","sha256":"acc8473252ca010d492d79441854ce6b6364d2d660387478d4b3cd82e170cfc5"},"intervention_id":"SYN-EVIDENCE-DOI-INTERVENTION-KAT","kind":"ORIGINAL_VALUE","predecessor_binding":null,"resulting_link_binding":{"domain":"doi-resulting-order-link/v1","sha256":"b78f69800927dd7a30b9809147a863fb4bc907303fd644f93b134b22aa1131f8"},"resulting_link_id":"SYN-EVIDENCE-DOI-INTERVENTION-KAT-LINK","schema_version":"doi-kpi-history/v1","sequence":1,"trigger_binding":{"domain":"doi-value-event/v1","sha256":"8a5b9a46f910160655c3d67d0bc3240d6f407dc44dd854e8b4e9e3d7edab8e66"}}
```

### NonidentifyingKPIBucket

```text
doi-nonidentifying-kpi-bucket/v1
{"action_date":"2026-08-20","current_value":{"amount":"12.34","currency_code":"USD","currency_registry_version":"synthetic-iso-style-currency-registry/v1","currency_scale":2},"intervention_count":1,"intervention_type":"FULFILLMENT_SPLIT","schema_version":"doi-nonidentifying-kpi-bucket/v1","state":"FINALIZED"}
```

### PriorClosureRetentionBindingV1

```text
doi-prior-closure-retention-binding/v1
{"case_id":"SYN-EVIDENCE-KAT-RETENTION-CASE","closed_at":"2026-08-20T12:00:00Z","closure_event_id":"SYN-EVIDENCE-KAT-RETENTION-CLOSURE","closure_reason":"REP_TRANSFERRED","lifecycle_state":"CLOSED_REVERSIBLE","prior_purge_eligible_at":"2026-11-18T13:00:00Z","projection_revision":1,"projection_sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","retention_policy_version":"doi-retention-calendar90-ny/v1","timezone_database_binding":"python-zoneinfo-America-New_York/v1"}
```

### RetainedKPIContribution

```text
doi-retained-kpi-contribution/v1
{"action_date":"2026-08-20","action_occurred_at":"2026-08-20T14:16:00Z","current_value":{"amount":"12.34","currency_code":"USD","currency_registry_version":"synthetic-iso-style-currency-registry/v1","currency_scale":2},"head_event_binding":{"domain":"doi-kpi-contribution-event/v1","sha256":"cbdecc9843c29639bac1d135edae6ad810aab15778e55027dab91e896571e003"},"intervention_action_binding":{"domain":"doi-action-verification-event/v1","sha256":"acc8473252ca010d492d79441854ce6b6364d2d660387478d4b3cd82e170cfc5"},"intervention_count":1,"intervention_id":"SYN-EVIDENCE-DOI-INTERVENTION-KAT","intervention_type":"FULFILLMENT_SPLIT","resulting_link_binding":{"domain":"doi-resulting-order-link/v1","sha256":"b78f69800927dd7a30b9809147a863fb4bc907303fd644f93b134b22aa1131f8"},"resulting_link_id":"SYN-EVIDENCE-DOI-INTERVENTION-KAT-LINK","revision":1,"schema_version":"doi-kpi-history/v1","state":"RETAINED"}
```

### VerifiedCurrencyEnvelope

```text
doi-verified-currency-envelope/v1
{"action_context_binding":{"domain":"doi-action-context/v1","sha256":"1554efa8e05249d87018388082d4f3292014bc3f2ec042c96cef8bf08e04e253"},"currency_code":"USD","evidence_id":"SYN-EVIDENCE-KAT-RETENTION-CURRENCY","intervention_action_binding":{"domain":"doi-action-verification-event/v1","sha256":"acc8473252ca010d492d79441854ce6b6364d2d660387478d4b3cd82e170cfc5"},"intervention_id":"SYN-EVIDENCE-DOI-INTERVENTION-KAT","observed_at":"2026-08-20T14:19:00Z","registry_version":"synthetic-iso-style-currency-registry/v1","scale":2,"schema_version":"doi-kpi-history/v1","source":{"domain":"shared-source-ref/v1","sha256":"8473561fedb6b4c5e7486a0531ea3d0d71b0391ef5ea8386da87046435b8afa3"},"subject_order_id":"SYN-ORDER-DOI-MODEL-KAT-0001"}
```
