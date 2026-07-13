"""Regression guard: synthetic-golden meta must not be coupled to config.MODEL.

Binding `model_version` to the live MODEL rewrote every tracked golden on each
test run and misrepresented provenance when MODEL changed without the expected
data being regenerated. These tests fail if that coupling is reintroduced.
"""

import src.config
from tests.fixtures.generators._common import _GOLDEN_MODEL_VERSION, golden_meta


def test_model_version_is_fixed_literal():
    assert golden_meta("grp_x")["model_version"] == _GOLDEN_MODEL_VERSION


def test_model_version_independent_of_config_model(monkeypatch):
    monkeypatch.setattr(src.config, "MODEL", "claude-some-future-model")
    # golden_meta must ignore the live MODEL entirely.
    assert golden_meta("grp_x")["model_version"] == _GOLDEN_MODEL_VERSION
    assert golden_meta("grp_x")["model_version"] != "claude-some-future-model"
