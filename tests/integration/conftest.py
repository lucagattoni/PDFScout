import os

import pytest


@pytest.fixture(autouse=True, scope="session")
def ensure_fixtures_generated():
    """Regenerate stale or missing PDF fixtures at session start."""
    from tests.fixtures.generators.generate_all import hash_check_all

    hash_check_all()


@pytest.fixture(autouse=True)
def require_real_api_key(request):
    """Skip B–H tests when no real ANTHROPIC_API_KEY is available.
    Group A carries @pytest.mark.e2e but makes no API calls — do NOT skip it here.
    """
    api_groups = ["grp_b", "grp_c", "grp_d", "grp_e", "grp_f", "grp_g", "grp_h", "grp_i", "grp_r"]
    if any(request.node.get_closest_marker(g) for g in api_groups):
        key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not key or key == "sk-test-fake":
            pytest.skip("Real ANTHROPIC_API_KEY required for B–H tests")
