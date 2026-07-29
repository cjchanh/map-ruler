"""Privacy regression gate.

Scans every tracked/untracked public text file for the operator's private
location markers. The marker values themselves are operator-local: they live
in ``tests/.private_markers.json`` (gitignored, never committed) — the whole
point of this gate is that those values must not exist in any tracked file,
and that includes this test's own source. Without the marker file the gate
skips honestly; with it, every detector must first trip on a planted sample
(positive control) before a clean scan counts.

Marker file schema::

    {
      "literal_tokens":      {"<label>": "<forbidden literal>"},
      "coordinate_patterns": {"<label>": "<regex>"},
      "literal_samples":     {"<label>": "<text containing the literal>"},
      "coordinate_samples":  {"<label>": "<text matching the regex>"}
    }
"""
from __future__ import annotations

import json
import re
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MARKERS_PATH = Path(__file__).resolve().parent / ".private_markers.json"
TEXT_SUFFIXES = {
    ".cfg",
    ".ini",
    ".json",
    ".md",
    ".py",
    ".sh",
    ".toml",
    ".txt",
    ".yaml",
    ".yml",
}


def load_private_markers() -> dict[str, dict[str, str]] | None:
    if not MARKERS_PATH.exists():
        return None
    return json.loads(MARKERS_PATH.read_text(encoding="utf-8"))


def public_text_files() -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    paths = []
    for raw_path in result.stdout.split(b"\0"):
        if not raw_path:
            continue
        path = ROOT / raw_path.decode("utf-8")
        if path.is_file() and path.suffix.lower() in TEXT_SUFFIXES:
            paths.append(path)
    return sorted(paths)


class TestPublicTreePrivacy(unittest.TestCase):
    def setUp(self) -> None:
        markers = load_private_markers()
        if markers is None:
            self.skipTest(
                "tests/.private_markers.json absent — the gate runs with the "
                "operator's private marker values, which are never committed"
            )
        self.tokens = {
            label: token.casefold()
            for label, token in markers["literal_tokens"].items()
        }
        self.patterns = {
            label: re.compile(pattern)
            for label, pattern in markers["coordinate_patterns"].items()
        }
        self.literal_samples = markers["literal_samples"]
        self.coordinate_samples = markers["coordinate_samples"]

    def test_private_marker_detectors_are_active(self) -> None:
        # Positive control: an empty or malformed marker file must not let the
        # clean-scan assertion pass vacuously.
        self.assertTrue(self.tokens, "marker file defines no literal tokens")
        self.assertTrue(self.patterns, "marker file defines no coordinate patterns")
        self.assertEqual(sorted(self.tokens), sorted(self.literal_samples))
        self.assertEqual(sorted(self.patterns), sorted(self.coordinate_samples))

        for label, token in self.tokens.items():
            self.assertIn(token, self.literal_samples[label].casefold())
        for label, pattern in self.patterns.items():
            self.assertRegex(self.coordinate_samples[label], pattern)

    def test_private_fixture_markers_are_absent(self) -> None:
        # setUp ran, so the detectors exist and the positive control above
        # guards them; the marker file itself is gitignored and therefore
        # excluded from public_text_files().
        findings: list[str] = []
        for path in public_text_files():
            relative_path = path.relative_to(ROOT)
            text = path.read_text(encoding="utf-8")
            folded = text.casefold()

            for label, token in self.tokens.items():
                if token in folded:
                    findings.append(f"{relative_path}: {label}")

            for label, pattern in self.patterns.items():
                if pattern.search(text):
                    findings.append(f"{relative_path}: {label}")

        self.assertEqual(
            [],
            findings,
            "private fixture markers found in public text files:\n" + "\n".join(findings),
        )


if __name__ == "__main__":
    unittest.main()
