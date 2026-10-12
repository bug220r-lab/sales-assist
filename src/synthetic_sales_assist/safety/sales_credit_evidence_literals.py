"""ADR 0044: reviewed evidence-reader public links and synthetic rejection canaries.

Exact file path, category, and literal SHA256 only. New bytes or another path remain
subject to the normal scanner. This registry grants no runtime network permission and
does not affect the independent credential scanner.
"""

REVIEWED_EVIDENCE_LITERALS: dict[str, dict[str, tuple[str, ...]]] = {
    "docs/helpscout-credit-evidence.md": {
        "non_localhost_url": (
            "05aab66e0ff4eba1b65edc6960d093c6e389fa5589ea013b3108ad525bddce8b",
            "0faac84303f511733d13a10bb7ab509d2b373eca36bc2ca87a74af214a86cfa2",
            "3e8ee86c327215228295811cd374fe62ec330c9de9c93fe8523e8a1d22f98e5c",
            "481d14e8caf4fbf2c721a5ab15b8dadb5ff59e0fb2a04d10fa79aed0606c41e4",
            "53f3e34c330319ba9c7782e85995ed447bdd1c084885b87c89d6846301d9d17a",
            "57aae3d49f11868e0f9db3281fdfcd1dd87682ad8dcb651161ffb7a4d4c8a6d2",
            "63fd535d991b0833de6d76cd6d386c6475d41233cf11b7eea847b210a0a39b8a",
            "646a5f6c934c5637f658bec1eafbd0a2ec40b1ebbe19b64003c885a7953d0fe8",
            "6b86ab0dc6429731de2208a794144d8a98f0389050a825c36e4481d8d824e68f",
            "8da5330f436b9d6fa8126975f936b93f391c79645914671adaa7d0082f9bb46b",
            "d387b32f62f5c01965abe77f85ba2c2774eb9e66bd384d1962edf933a251042c",
            "ee78b658d73d15f6c64bf81b58b2e2cacefda5da140786aa87b7a0c96bf4222a",
        ),
    },
    "src/sales_credit_evidence/demo.py": {
        "non_localhost_url": (
            "03bbd9436f0e2f1cfe8a709a0e4d39f9549669bdcd017a0e34e269d1dbd8cb2d",
        ),
    },
    "src/sales_credit_evidence/transport.py": {
        "non_localhost_url": (
            "646a5f6c934c5637f658bec1eafbd0a2ec40b1ebbe19b64003c885a7953d0fe8",
        ),
    },
    "tests/test_sales_credit_evidence_reader.py": {
        "non_localhost_url": (
            "0389de9a2270926a9d4c27ff49cde58274eef5d35645b1592a06ce9e6b5555e9",
            "0e0d82e9046558ff9f895bbeb346bacdd4ec8cae0f9f9e047eec976f762acca3",
            "11115dbd50d44d05cc1381ad400abf9c8355637f657dc38c65c1688227322bfa",
            "23719b822fd8cb22fc35e835d7ae88f57b9d7facca8f22ebb67e1558dd883931",
            "340076217915ea6bd5cc3cd27690aa92b924fdf830c9f7360f7b79e878c808fe",
            "3cf3bc152595d2645c889db8fc640fbd94f68e0967a893cc8ed0b83773f7f748",
            "44a2eebc612e1d3d12d035b8c9cb5b70962f4adca766ac92c54b15727f8f8df2",
            "7540291448f62b9666744c5ea4330fc3b8b1a1054cae4cf98a6198000a24959e",
            "88426eddff8647085ffd30c74fa549ec7bac8c2a5f3e87552847174568c8bebf",
            "9894c77dcd5d09a33cfeec89f37e8cad846c6cdb0976eeb2ba6103e2b18e737b",
            "a91533f618e8deb34d4ac43cdf8dea009abea6308a31ac059a99efa0c1c75802",
            "aed00db2f175917dc69723e2d33cc09f78e02569fec99227668c9493ae3360c9",
            "af368d0f1e7d3dc9b0b9f3b889a315536bae5f4d02aa8e0d760bb50bf9999857",
            "b3177945710f265811cc07d2278099625674bc12e4ce7270ebcb9d6ef97b0e02",
            "cce75d97183ac05d1094a2979ad8eb1a86d632959134acbb88c2be1237f5f3ab",
            "e147de3259cbc5ecc0940496697d15e628822ace60faa82bdb9d8ca0a5e7f319",
            "eec6d39856f4da11958fc483d3efdc9dbda9c5223e844306b10a1374263aa180",
        ),
    },
    "tests/test_sales_credit_evidence_transport.py": {
        "non_localhost_url": (
            "1c69a780f6e741c8d1b12193d06f5a9ef83d4db70c3bb8411529800627254ac5",
            "2982b39f7d5b7a384f32cf25d325e985c11f17d9bffda99a199549174140a2b1",
            "3439fc0285839640074d006cdb245f3f852e05679b8d0f83c1d58587711f2d2d",
            "34a015d78962832aa30b66170770ccebc9e92e0aa62a34768948b9caff55fc33",
            "408c645a432e9a28faaaf862c6fa3da15570ec52e3bdfe39e87144922d11bcbb",
            "43cba8f04722781c35e8bea7fa209f3528c7026658aee57722c0c22329b9660e",
            "49a76e96eb0c32f031e25d22b7bf10cda21306031daa375883439a5e3eb5c38d",
            "62db95dc09cff6dfd63499eeb602db84022d73388e0a80501dc28b6c658ed7fd",
            "741a1fc1f5893c76a29a7933ce0ed6a6a49efe9a9b5b6ab2cbea0d7dcea0b316",
            "768f648e78ba6e6b11095ac440e0ad86483c5907d46574a575d5c656965a93e2",
            "7b7001e31f8d8cb519ed65027a81c2a38766fa5f421dc61ef350926604611186",
            "818ddedc791317ae9262596c692c94c2d5707bef5cb2521dfb31a22544c9d86e",
            "85df18484a9994908501948c2a9cd909035f15f24cf17b595a5031fdb4820448",
            "8ee85b6dbfa0a0f58a1ec1fcf1f7b73274080f8894d3172ec0f7f35e6eb7333c",
            "a0aed12c6bc90bc9476e04cca872b8a14d7e0e03945201446a5459cfdf548e92",
            "ab6fa713914cd41633a500f7ecae3ffc711d93800a130b29d0e5a697d5114e9b",
            "b60e588ecf6bd42684707dc7fc64c48fa2e92f3c313af8adf3aee220c6629bda",
            "c1b10b79511c460be136024eb62bbe603858f3889b4cae482b9d38515c4aae9c",
            "c512aaf94db665d59f4e018d441bb5cb578a7771314557192bcc46ee8951dde6",
            "cffaed0bd07d707d9b15ac162491297ea4ae0553f9454eb17ce13cfd8b4f6a16",
            "dfb11fac697d14bc29a2fd662af9605473db129e0aa9d98e6cf6b0b9da3e827f",
            "f58bbec12c507015c85ea86788227b70a97f944f5f24412cf1dc37a77291b4e8",
            "f8247cc5a5f6e9269bf38cf8cdf808d7262a9e38b85c4736e023d70383649655",
            "f968efaffdaddcea2149b75f434fa70ddb2d73c039062d126a57d2f78efd299b",
        ),
        "non_synthetic_email": (
            "2565c48989fb1ebf14571d06e39ab5dcc9e8ada9e3fe3775cec590fbaec3303e",
            "f35abc91702dc15acc02089b276e4f4ff0d125af257b1adf91d13ff0a4b450cd",
            "f6ca9285ae31cb16b3cc42cf0febad99ed240c66deda79457ca30cd807214705",
        ),
    },
}
