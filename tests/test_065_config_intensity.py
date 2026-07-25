"""Tests for item 065's ``intensity:`` config-mode section
(``src/segfacet/config.py``): a top-level mode section mirroring item 049's
``reference:`` section -- an ``intensity_param(key, default)`` accessor,
excluded from ``config_hash``'s canonical field list, and a guarantee that
no new active ``rules.intensity`` / ``rules.intensity_reference_delta``
YAML section is introduced (the item spec's pivotal, explicitly-justified
Assumption: adding those sections would change ``config.rules`` and hence
``config_hash``, staling the committed ``reference_default.json`` and
breaking item 035's exact-seven-rule-id test).

Covers Acceptance Criteria AC11, AC12:

- AC11: ``config.intensity_param("enabled", False)`` returns the parsed
  config value and defaults to ``False`` when the ``intensity:`` section is
  absent.
- AC12: ``set(load_config(default_config_path()).rules.keys())`` still
  equals exactly the seven active rule ids; ``config_hash(
  bundled_default_config())`` equals the value already committed in
  ``reference_default.json``'s provenance
  (``87c73ab35da9707054b300e15664c391ce50851c5d11490c89125381c1c96ac8``).

Adversarial / edge-case scenarios included:
- ``intensity:`` section present but only partially populated -- unset keys
  still fall back to *default*.
- Adding an ``intensity:`` section does not change ``config_hash``, mirroring
  item 049's own ``reference:`` section guarantee (AC8 there).

Note: ``load_config(default_config_path()) == default_config()`` is *not*
asserted here -- it is a pre-existing, long-standing false equality unrelated
to item 065 (``default_config()``'s ``rules``/``verdict`` are ``{}`` by design,
meaning "all rules enabled with built-in code defaults" -- items 026/034,
while ``load_config()`` on the bundled YAML materialises the full rule set --
item 035). AC12's real intent (a stable ``config_hash`` for the bundled
config) is covered by
``test_ac12_config_hash_matches_committed_reference_default_provenance``
above, mirroring the fix applied to item 048's AC7
(``test_heuristics_bounds_source.py``).
"""

from __future__ import annotations

from segfacet.config import (
    SUPPORTED_SCHEMA_VERSION,
    bundled_default_config,
    default_config,
    default_config_path,
    load_config,
)

_SEVEN_RULE_IDS = frozenset(
    {"bounds", "fragmentation", "coverage", "sequence", "border", "overlap", "mislabel"}
)

_COMMITTED_REFERENCE_DEFAULT_CONFIG_HASH = (
    "87c73ab35da9707054b300e15664c391ce50851c5d11490c89125381c1c96ac8"
)


def _write_yaml(tmp_path, content, name="config.yaml"):
    p = tmp_path / name
    p.write_text(content, encoding="utf-8")
    return p


# =========================================================================== #
# AC11: intensity_param accessor
# =========================================================================== #


def test_ac11_intensity_param_defaults_to_false_when_section_absent():
    cfg = default_config()
    assert cfg.intensity_param("enabled", False) is False


def test_ac11_intensity_param_reads_yaml_intensity_section(tmp_path):
    cfg = load_config(
        _write_yaml(
            tmp_path,
            f"schema_version: '{SUPPORTED_SCHEMA_VERSION}'\n"
            "intensity:\n"
            "  enabled: true\n"
            "  radiomics: false\n",
        )
    )
    assert cfg.intensity_param("enabled", False) is True
    assert cfg.intensity_param("radiomics", True) is False


def test_ac11_intensity_param_returns_default_for_unset_key(tmp_path):
    cfg = load_config(
        _write_yaml(
            tmp_path,
            f"schema_version: '{SUPPORTED_SCHEMA_VERSION}'\n"
            "intensity:\n"
            "  enabled: true\n",
        )
    )
    # 'radiomics' is not set in this file -- falls back to the caller-given
    # default, exactly like reference_param's contract.
    assert cfg.intensity_param("radiomics", True) is True
    assert cfg.intensity_param("some_unknown_key", "sentinel") == "sentinel"


def test_ac11_bundled_default_config_intensity_param_is_false():
    cfg = bundled_default_config()
    assert cfg.intensity_param("enabled", False) is False


# =========================================================================== #
# AC12: no config-hash / rule-id-count regression
# =========================================================================== #


def test_ac12_bundled_default_config_rule_ids_are_exactly_the_seven():
    cfg = load_config(default_config_path())
    assert set(cfg.rules.keys()) == set(_SEVEN_RULE_IDS)


def test_ac12_config_hash_matches_committed_reference_default_provenance():
    from segfacet.reference.artifact import config_hash

    cfg = bundled_default_config()
    assert config_hash(cfg) == _COMMITTED_REFERENCE_DEFAULT_CONFIG_HASH


# =========================================================================== #
# Adversarial / edge cases
# =========================================================================== #


def test_adv_intensity_section_does_not_change_config_hash(tmp_path):
    from segfacet.reference.artifact import config_hash

    cfg_without = default_config()
    cfg_with = load_config(
        _write_yaml(
            tmp_path,
            f"schema_version: '{SUPPORTED_SCHEMA_VERSION}'\n"
            "intensity:\n"
            "  enabled: true\n"
            "  radiomics: false\n",
        )
    )
    assert config_hash(cfg_without) == config_hash(cfg_with)


def test_adv_intensity_and_reference_sections_coexist_independently(tmp_path):
    cfg = load_config(
        _write_yaml(
            tmp_path,
            f"schema_version: '{SUPPORTED_SCHEMA_VERSION}'\n"
            "reference:\n"
            "  enabled: true\n"
            "intensity:\n"
            "  enabled: true\n",
        )
    )
    assert cfg.reference_param("enabled", False) is True
    assert cfg.intensity_param("enabled", False) is True


def test_adv_no_rules_intensity_or_intensity_reference_delta_section_in_bundled_default():
    """The pivotal Assumption, asserted directly: the bundled default config
    does not carry active ``rules.intensity`` / ``rules.intensity_reference_
    delta`` sections -- the two rules stay section-less (code defaults),
    exactly like ``reference_delta``'s own precedent."""
    cfg = load_config(default_config_path())
    assert "intensity" not in cfg.rules
    assert "intensity_reference_delta" not in cfg.rules
    assert "reference_delta" not in cfg.rules
