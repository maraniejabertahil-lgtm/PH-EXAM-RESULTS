"""Run the PRC and shared Python suites in scope for the current acceptance plan."""

from __future__ import annotations

import sys
import unittest


MODULES = (
    "test_broadcaster",
    "test_d1_client",
    "test_gitops_manager",
    "test_greenlight",
    "test_json_builder",
    "test_normalizer",
    "test_official_first_policy",
    "test_official_pdf",
    "test_pdf_parser",
    "test_pipeline",
    "test_prc_orchestrator",
    "test_prc_page_sample",
    "test_prc_public_preview_pipeline",
    "test_public_preview",
    "test_public_preview_shards",
    "test_watcher_event_validation",
)

EXCLUDED_TEST_IDS = {
    "test_json_builder.ArrayJsonBuilderTests.test_shards_are_below_configured_size_and_preserve_every_record",
    "test_json_builder.ArrayJsonBuilderTests.test_fallback_manifest_preserves_both_source_identities",
}


def flatten(suite: unittest.TestSuite):
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from flatten(item)
        else:
            yield item


def main() -> int:
    sys.path.insert(0, "tests")
    loader = unittest.defaultTestLoader
    selected = []
    for module in MODULES:
        loaded = loader.loadTestsFromName(module)
        selected.extend(test for test in flatten(loaded) if test.id() not in EXCLUDED_TEST_IDS)

    result = unittest.TextTestRunner(verbosity=2).run(unittest.TestSuite(selected))
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
