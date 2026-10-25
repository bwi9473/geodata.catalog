from pathlib import Path
import base64
import json

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


def test_layer_config_from_dict_migrates_legacy_column_lists():
    config = LayerConfig.from_dict({
        "datasource_id": "ds1",
        "layer_name": "LAYER_A",
        "searchable_columns": [{"name": "STATUS", "use_distinct": True}],
        "view_columns": [{"name": "ID", "type": "numeric"}, {"name": "STATUS"}],
    })

    columns = {column["name"]: column for column in config.field_columns}

    assert columns["STATUS"]["search"] is True
    assert columns["STATUS"]["export"] is True
    assert columns["STATUS"]["use_distinct"] is True
    assert columns["ID"]["export"] is True


def test_layer_config_repository_persists_enable_fl_filter(tmp_path: Path):
    repo_file = tmp_path / "layer_config.json"
    repository = LayerConfigRepository(repo_file)
    svg_path = tmp_path / "radar.svg"
    svg_content = b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"><circle cx="5" cy="5" r="4"/></svg>'
    svg_path.write_bytes(svg_content)

    config = LayerConfig(
        datasource_id="ds1",
        layer_name="LAYER_A",
        layername="Layer A",
        category_label="Airspace",
        label_column="STATUS",
        svg_marker_path=str(svg_path),
        enable_fl_filter=False,
        field_columns=[
            {"name": "STATUS", "label": "Status", "type": "varchar", "input_type": "dropdown", "search": True},
            {"name": "ID", "label": "ID", "type": "numeric", "export": True, "key": True},
        ],
        key_column="ID",
    )

    repository.save(config)
    loaded = repository.get("ds1", "LAYER_A")

    assert loaded is not None
    assert loaded.category_label == "Airspace"
    assert loaded.svg_marker_path is not None
    assert loaded.svg_marker_path.startswith("base64:")
    assert base64.b64decode(loaded.svg_marker_path[7:]) == svg_content
    assert loaded.enable_fl_filter is False
    assert loaded.field_columns[0]["search"] is True
    assert loaded.searchable_columns[0]["input_type"] == "dropdown"
    assert loaded.field_columns[1]["export"] is True
    assert loaded.key_column == "ID"
    payload = json.loads(repo_file.read_text(encoding="utf-8"))
    assert "searchable_columns" not in payload[0]
    assert "view_columns" not in payload[0]
