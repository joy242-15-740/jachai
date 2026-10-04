"""A small trained system on disk and an API client over it (built once per run)."""

import joblib
import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.settings import Settings
from app.store import Configs, Store
from jachai.features import build_features
from jachai.labels.config import load_rules
from jachai.system import train_system
from jachai.testing import small_models, small_thresholds, small_world_config
from jachai.world.config import load_patterns_config
from jachai.world.generate import generate_world, write_world


@pytest.fixture(scope="session")
def artifacts(tmp_path_factory):
    root = tmp_path_factory.mktemp("jachai")
    cfg, thr, models, rules = small_world_config(), small_thresholds(), small_models(), load_rules()
    world = generate_world(cfg, load_patterns_config())
    write_world(world, root / "world")
    shop_day = build_features(world.tables, cfg, thr.features)["shop_day"]
    system, _ = train_system(world.tables, shop_day, cfg, thr, rules, models)
    system.payment.save(root / "models")
    joblib.dump(system.shop, root / "models" / "shop_model.joblib")
    system.fusion.save(root / "models" / "fusion.json")
    return root, Configs(cfg, thr, rules, models), world


@pytest.fixture(scope="session")
def api(artifacts):
    root, configs, world = artifacts
    settings = Settings(
        model_dir=root / "models",
        world_dir=root / "world",
        reports_dir=root / "reports",
        audit_db_path=root / "audit.sqlite3",
        allowed_origins=["http://localhost:3000"],
    )
    store = Store(settings.model_dir, settings.world_dir, configs)
    with TestClient(create_app(settings, store)) as client:
        yield client, store, world
