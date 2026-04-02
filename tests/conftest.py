from __future__ import annotations

import pytest
import respx


@pytest.fixture
def mock_api():
    with respx.mock(base_url='https://api.rendershot.io', assert_all_called=False) as mock:
        yield mock
