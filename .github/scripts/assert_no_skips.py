#!/usr/bin/env python3
"""Fail if any test case in a JUnit XML report was skipped, except for
skips explicitly allow-listed by a substring of their reason message.

Used by the CI `verify-environment-gated` job: its whole point is to prove
the pyradiomics/Docker-gated tests actually run with the real optional
dependency present, not just skip cleanly the way they do in the baseline
`test` job. A skip here usually means the job's environment setup is broken
(or a test's skip condition is wrong), not that the dependency is
legitimately absent -- so it must fail the job outright rather than reading
as green.

The one legitimate exception: a handful of tests are designed to verify the
*absent*-path behaviour and correctly self-skip when the dependency happens
to be present (e.g. "PyRadiomics happens to be installed" -- the inverse
condition of every other gated test here). Pass one or more --allow
substrings to whitelist exactly those, by reason text, so a genuine
unexpected skip elsewhere still fails the job.
"""
import argparse
import sys
import xml.etree.ElementTree as ET


def find_skips(path: str) -> list[tuple[str, str]]:
    root = ET.parse(path).getroot()
    suites = [root] if root.tag == "testsuite" else root.findall("testsuite")
    skipped = []
    for suite in suites:
        for case in suite.findall("testcase"):
            skip = case.find("skipped")
            if skip is not None:
                name = f"{case.get('classname')}::{case.get('name')}"
                reason = skip.get("message", "")
                skipped.append((name, reason))
    return skipped


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("junit_xml_path")
    parser.add_argument(
        "--allow",
        action="append",
        default=[],
        metavar="SUBSTRING",
        help="Skip reason substring to allow-list (repeatable); a skip whose "
        "reason contains any --allow substring does not fail the job.",
    )
    args = parser.parse_args(argv)

    skipped = find_skips(args.junit_xml_path)
    unexpected = [
        (name, reason)
        for name, reason in skipped
        if not any(allowed in reason for allowed in args.allow)
    ]

    if unexpected:
        print(
            "FAIL: the following environment-gated tests were skipped "
            "(expected to run for real in this job):",
            file=sys.stderr,
        )
        for name, reason in unexpected:
            print(f"  - {name} -- {reason}", file=sys.stderr)
        return 1

    if skipped:
        print(
            f"OK: {len(skipped)} skip(s) found, all allow-listed "
            "(inverse-condition tests):"
        )
        for name, reason in skipped:
            print(f"  - {name} -- {reason}")
    else:
        print("OK: no skips among the environment-gated tests.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
