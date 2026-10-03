"""The summary report and the `python -m jachai.world` entry point."""

import re

from jachai.world.config import DEFAULT_CONFIG_DIR, REPO_ROOT, load_patterns_config
from jachai.world.generate import write_world
from jachai.world.summary import main as summary_main


def test_summary_lists_every_pattern_and_category(pattern_world, tmp_path):
    world_dir = tmp_path / "world"
    write_world(pattern_world, world_dir)
    out = tmp_path / "summary.md"
    summary_main([str(world_dir), "--out", str(out)])
    text = out.read_text(encoding="utf-8")
    for spec in load_patterns_config().patterns:
        assert f"| {spec.name} |" in text, spec.name
    for category in pattern_world.config.categories:
        assert f"| {category} |" in text, category
    assert "Synthetic data only" in text
    # p2p_disguise has no QR rows but must still show its shops and transfers.
    line = next(row for row in text.splitlines() if row.startswith("| p2p_disguise |"))
    cells = [c.strip() for c in line.strip("|").split("|")]
    assert cells[1] == "1"  # label
    assert cells[5] != "0" and cells[7] != "0"  # shops, p2p_transfers


def test_assumptions_doc_covers_every_config_section_and_pattern():
    """data/ASSUMPTIONS.md must mention every world.yaml section and every pattern,
    so the doc cannot silently fall behind the configs."""
    doc = (REPO_ROOT / "data" / "ASSUMPTIONS.md").read_text(encoding="utf-8")
    world_yaml = (DEFAULT_CONFIG_DIR / "world.yaml").read_text(encoding="utf-8")
    sections = re.findall(r"^([a-z_]+):", world_yaml, flags=re.M)
    assert sections, "no top-level keys found in world.yaml"
    missing = [s for s in sections if f"`{s}`" not in doc]
    missing += [p.name for p in load_patterns_config().patterns if f"`{p.name}`" not in doc]
    assert not missing, f"not documented in data/ASSUMPTIONS.md: {missing}"
