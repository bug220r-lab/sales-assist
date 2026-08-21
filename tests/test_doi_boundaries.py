from __future__ import annotations

import unittest

from synthetic_sales_assist.doi.boundaries import (
    DOIBoundaryError,
    DOICapabilityRequest,
    enforce_milestone3_capability,
)


class DOIMilestone3CapabilityBoundaryTests(unittest.TestCase):
    def test_read_only_is_allowed_and_prohibited_capabilities_emit_exact_reasons(self) -> None:
        self.assertIsNone(
            enforce_milestone3_capability(
                DOICapabilityRequest.READ_ONLY_INSPECTION
            )
        )
        cases = (
            (DOICapabilityRequest.OA_WRITE, "RC-082"),
            (DOICapabilityRequest.UNSAFE_EXTERNAL_ACTION, "RC-083"),
        )
        for request, expected in cases:
            with self.subTest(request=request.value), self.assertRaises(
                DOIBoundaryError
            ) as raised:
                enforce_milestone3_capability(request)
            self.assertEqual(
                tuple(reason.code for reason in raised.exception.reasons.reasons),
                (expected,),
            )


if __name__ == "__main__":
    unittest.main()
