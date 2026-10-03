"""Smoke test: the backend package imports."""

import app


def test_version():
    assert app.__version__
