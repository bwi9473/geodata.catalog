from pathlib import Path

from geodata_catalog.metadata.layer_config_repository import LayerConfig, LayerConfigRepository


def test_layer_config_from_dict_defaults_enable_fl_filter_to_true():
    raw = {
        "datasource_id": "ds1",
        "layer_name": "LAYER_A",
        "searchable_columns": [],
        "view_columns": [],
    }

    config = LayerConfig.from_dict(raw)

    assert config.enable_fl_filter is True


def test_layer_config_repository_persists_enable_fl_filter(tmp_path: Path):
    repo_file = tmp_path / "layer_config.json"
    repository = LayerConfigRepository(repo_file)

    config = LayerConfig(
        datasource_id="ds1",
        layer_name="LAYER_A",
        layername="Layer A",
        label_column="STATUS",
        enable_fl_filter=False,
        searchable_columns=[{"name": "STATUS", "label": "Status", "type": "varchar"}],
        view_columns=[{"name": "STATUS", "label": "Status", "type": "varchar"}],
    )

    repository.save(config)
    loaded = repository.get("ds1", "LAYER_A")

    assert loaded is not None
    assert loaded.enable_fl_filter is False
