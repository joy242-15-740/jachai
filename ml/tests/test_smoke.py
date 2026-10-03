"""Smoke test: the ml package and all its subpackages import."""

import importlib

import jachai

SUBPACKAGES = ["world", "labels", "features", "models", "explain", "simulate", "eval"]


def test_version():
    assert jachai.__version__


def test_subpackages_import():
    for name in SUBPACKAGES:
        importlib.import_module(f"jachai.{name}")
