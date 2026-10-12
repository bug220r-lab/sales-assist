"""Reviewed public DOI links and synthetic rejection fixtures, scoped to exact bytes.

ADR 0038: new or changed values still fail the repository scan. No runtime permission.
The independent credential scanner still examines every file.
"""

from synthetic_sales_assist.safety.sales_credit_evidence_literals import (
    REVIEWED_EVIDENCE_LITERALS,
)

REVIEWED_SOURCE_LITERALS = {
    "docs/doi-draft-transfer.md": {
        "non_localhost_url": (
            "17f3e9ee6ed8e553d8159377cfe659ade2eae3118c5f3a2e6e1bade08ee20bb7",
            "26b2cda0431c5d9a581678a4c2e0e16b3a7edc25f625a35382f090eb8b3193d2",
            "884ae034abb93905917cb995a2b1ff4753e6d9cffd7ebdafec6e245acef0b738",
            "d074bbe2ffe1f37b91c37f739d7f7fb017cb0ca6f73fa69424502ebb75e2cb94",
            "ef61cfcc7ef676f766237d5f3fcf76508fdd1a78eaedd3824036a786ebcb1461",
            "f4a26a3ba24711f8d5cb113bd3b2f3d152f06914f1305d63dd9b6e25ca736c4a",
            "fb9dd78ec5095a5fb4c80737956d07f3e60d8ce9449930d79138b127904cea32",

            "606caa20d907d47f0affb9231011d4f1755eb86f2394ab63dc43e76c3ff857c7",
        )
    },
    "src/doi_csv_staging/alternate_drafts.py": {
        "non_localhost_url": ("f4a26a3ba24711f8d5cb113bd3b2f3d152f06914f1305d63dd9b6e25ca736c4a",)
    },
    "src/doi_draft_transfer/contract.py": {
        "non_localhost_url": ("5384dc8562ffb9763f8b46b64a030924a2939a1defd6757f9b02050e7e4f322e",
            "2b2b15ff10dc867ce6229e3a306f12e853395b272075c2a5f51bfcba02c3332f",
        )
    },
    "src/doi_draft_transfer/helpscout.py": {
        "non_localhost_url": ("ea228fe1dd15839b868e429f0538109a7867fcd429e1c024d74bdbb5e0f9c46e",)
    },
    "src/synthetic_sales_assist/portal/alternate_draft_ui.py": {
        "non_localhost_url": ("a09d56acd34b7ddc9ff72671b9e0292aa265012a90a727d04648346a7b299e4c",)
    },
    "tests/test_doi_alternate_drafts.py": {
        "non_localhost_url": (
            "031cb7f8a2e1cc58ecf5c934f7808c0e97c18acef8d709a490d6c7befe75e657",
            "3bed2b909e5886298b49e13fdc49262b0e7231cb326c67c0acea20a47e6d0e04",
            "4facc55cf1fd929e369f05c9a1313cf680de30ebbea9816e3ab0de270b2d3115",
            "53fdde1fc2fac05c10e46fe14e3b0de9e1eb096d8b61ad465c4c94708e1b03ff",
            "7a77c081a31f8182db2ced30b02bda857c840794b0b08a3c154b1b7fab9934ff",
            "9352632fe4f1269766484c004ae60830cc400bb7cb94fe785909b3d9853d51b4",
            "a066e97b143d9babbc58bc9252041a5ab521d5d6e440d25bb88980e04ce64b9e",
            "ad75fcd9761d082db96f40aeea4864c291d34ce9b54f3d2884fdb659f9d1fc0f",
            "c1a6a88debb0ef508f3a3502e5863a3e16636ce4dcfc8fcf40a47ac75ac3f40f",
            "c6247868144418b523e9e4d55823acf2c3e9314c245e4fa02fdd088e3322caf6",
            "e2514182dbb660d4ad50731edbb267d6c114599e0aee21c604005c4f54935be4",
            "fb5927d08096f246d0840019a0f8c02a1063afcd489d8ca1f85108984836b05a",
        ),
        "non_synthetic_email": (
            "e2dd2dd6c9f45ae00c528f9bf084ac4007d404d52b12758c252762855578f0eb",
        ),
    },
    "tests/test_doi_draft_transfer.py": {
        "non_localhost_url": (
            "45b65ece4c66548201ce3609ca0cdf33fd7b0e853507d5c6359a5cc864da4b75",
            "4facc55cf1fd929e369f05c9a1313cf680de30ebbea9816e3ab0de270b2d3115",
            "7e34cb0def5bde93b9071f37b06f27bbd0474448c97b2461c5b9de0f8473e760",
            "98c33feb607b22e52d8ce86ec863c7e20a2d1ead672de74de903bfece616beb5",
            "e1faf374c194cd34e34c222ffe490c06a5c83cdb866195a6692bf12d6e436d51",
            "eddaff8597a0731d7e200fb5e798e5a6d79af49f05e3035456d1e39219ad91f7",
        ),
        "non_synthetic_email": (
            "2f2c673828bc9fb22873912a20341a6413601324f914b40cdb1e7815f304fb19",
            "d1c062af7fabf58e8443e8d80ddeecd9098520c1b8fcc26e982ce34687a4538d",
        ),
    },
    "tests/test_doi_draft_transfer_http.py": {
        "non_localhost_url": ("e1faf374c194cd34e34c222ffe490c06a5c83cdb866195a6692bf12d6e436d51",)
    },
    "tests/test_doi_review_marks.py": {
        "non_localhost_url": ("f1e2c7da767e6e0fc3eac0819fdd3a622967f18748c6f0a875c3a5b0a165031e",)
    },
    "docs/adr/0041-labeled-draft-links-and-rendered-approval.md": {
        "non_localhost_url": (
            "606caa20d907d47f0affb9231011d4f1755eb86f2394ab63dc43e76c3ff857c7",
        ),
    },
    "docs/doi-draft-transfer-auth-proposal.md": {
        "non_localhost_url": (
            "481d14e8caf4fbf2c721a5ab15b8dadb5ff59e0fb2a04d10fa79aed0606c41e4",
            "8da5330f436b9d6fa8126975f936b93f391c79645914671adaa7d0082f9bb46b",
        ),
    },
    "tests/test_doi_draft_launch.py": {
        "non_localhost_url": (
            "e1faf374c194cd34e34c222ffe490c06a5c83cdb866195a6692bf12d6e436d51",
        ),
    },
    "tests/test_doi_draft_transfer_links.py": {
        "non_localhost_url": (
            "2c66a6ed6fa7b8a5f78dbaa057672b20585c5a4b4918d46f777a1c078940091f",
            "8d4c7d2187a07ff6b9dfb726c7b140120203d9b78f4005337f03dbffd5170fd8",
            "d8c0a7de34ba33bbd330fd412f87b2550e3947349c8717827335df10c0557fbd",
        ),
    },
}

# ADR 0044 uses the same exact-literal mechanism for the isolated evidence reader.
# Scanner behavior, whole-file coverage, and runtime host policy remain unchanged.
REVIEWED_SOURCE_LITERALS.update(REVIEWED_EVIDENCE_LITERALS)
