#!/usr/bin/env python3
"""Fail if any test case in a JUnit XML report was skipped.

Used by the CI `verify-environment-gated` job: its whole point is to prove
the pyradiomics/Docker-gated tests actually run with the real optional
dependency present, not just skip cleanly the way they do in the baseline
`test` job. A skip here means the job's environment setup is broken (or a
test's skip condition is wrong), not that the dependency is legitimately
absent -- so it must fail the job outright rather than reading as green.
"""
import sys
import xml.etree.ElementTree as ET


def find_skips(path: str) -> list[str]:
    root = ET.parse(path).getroot()
    suites = [root] if root.tag == "testsuite" else root.findall("testsuite")
    skipped = []
    for suite in suites:
        for case in suite.findall("testcase"):
            skip = case.find("skipped")
            if skip is not None:
                name = f"{case.get('classname')}::{case.get('name')}"
                reason = skip.get("message", "")
                skipped.append(f"{name} -- {reason}")
    return skipped


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print("usage: assert_no_skips.py <junit-xml-path>", file=sys.stderr)
        return 2

    skipped = find_skips(argv[0])
    if skipped:
        print(
            "FAIL: the following environment-gated tests were skipped "
            "(expected to run for real in this job):",
            file=sys.stderr,
        )
        for entry in skipped:
            print(f"  - {entry}", file=sys.stderr)
        return 1

    print("OK: no skips among the environment-gated tests.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
