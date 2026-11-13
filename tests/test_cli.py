"""The command line does what the picker does: designs from files, links and saved names; clear errors; JSON out."""
import json

import pytest

from text2print import __main__ as cli, design as dz, store


def run(capsys, *argv):
    code = cli.main(list(argv)); out = capsys.readouterr().out
    return code, out


@pytest.fixture(autouse=True)
def own_home(tmp_path, monkeypatch):                       # never touch the real ~/.text2print
    monkeypatch.setattr(store, "HOME", tmp_path / "home"); monkeypatch.setattr(store, "IMAGES", tmp_path / "home" / "images")


DESIGN = {"shape": "cup", "texture": "jacquard", "params": {"height": 70}, "colours": ["#151515", "#F4F2EC"],
          "options": {"loops": "shag", "band": 2}}


def test_link_round_trip_keeps_sizes_colours_and_options():
    url, dropped = dz.to_link(DESIGN)
    back = dz.from_link(url)
    assert not dropped and back["shape"] == "cup" and back["params"] == {"height": 70.0}
    assert back["colours"] == DESIGN["colours"] and back["options"] == {"loops": "shag", "band": "2"}


def test_link_carries_mixes_and_charts_as_json_and_toggles_as_booleans():
    d = dz.from_link('?shape=vase&texture=mix&mix=[{"texture":"plain","share":1}]&c=8B3A2F')
    assert d["options"]["bands"] == [{"texture": "plain", "share": 1}]
    d = dz.from_link("?shape=cup&texture=domes&rim_loops=1")
    assert d["options"]["rim_loops"] is True
    url, dropped = dz.to_link(dict(DESIGN, options={"loops": {"loop_w": 4}}))
    assert dropped == ["loops"]                             # a hand-set loop spec does not fit in a link: say so


@pytest.mark.parametrize("bad, says", [
    ({"shape": "cupp", "texture": "domes"}, "unknown shape"),
    ({"shape": "cup", "texture": "nope"}, "unknown texture"),
    ({"shape": "candle", "texture": "twill"}, "does not fit"),
    ({"shape": "cup", "texture": "domes", "params": {"width": 9}}, "has no size"),
    ({"shape": "cup", "texture": "domes", "colours": ["red"]}, "#RRGGBB"),
    ({"shape": "cup", "texture": "domes", "nozzle": 0.5}, "no profile"),
    ({"shape": "cup", "texture": "domes", "size": 3}, "unknown design keys"),
])
def test_a_bad_design_says_what_to_fix(bad, says):
    with pytest.raises(dz.DesignError, match=says):
        dz.normalise(bad)


def test_make_from_a_design_file_writes_the_project_and_reports_json(tmp_path, capsys):
    f = tmp_path / "d.json"; f.write_text(json.dumps(DESIGN))
    code, out = run(capsys, "make", "--design", str(f), "--draft", "--no-stls", "--out", str(tmp_path), "--name", "piece")
    r = json.loads(out)
    assert code == 0 and (tmp_path / "piece.3mf").stat().st_size > 1000 and r["stats"]["strands"] > 100
    assert r["link"].startswith("http://127.0.0.1:7384/?shape=cup") and r["design"]["options"]["loops"] == "shag"


def test_make_takes_json_option_values_and_flags_unknown_choices(tmp_path, capsys):
    code, out = run(capsys, "make", "cup", "jacquard", "--draft", "--no-stls", "--out", str(tmp_path),
                    "--option", 'chart=[{"plain": 0, "mm": 5}, {"stripes": [0, 1], "mm": 6}]', "--option", "stitch_size=huge")
    r = json.loads(out)
    assert code == 0 and any("stitch_size" in w for w in r["warnings"])


def test_a_bad_request_exits_2_with_an_error_object(tmp_path, capsys):
    code, out = run(capsys, "make", "cup", "nosuch", "--out", str(tmp_path))
    assert code == 2 and "unknown texture" in json.loads(out)["error"]
    code, out = run(capsys, "make", "--out", str(tmp_path))
    assert code == 2 and "SHAPE TEXTURE" in json.loads(out)["error"]


def test_saved_designs_can_be_listed_shown_built_and_deleted(tmp_path, capsys):
    f = tmp_path / "d.json"; f.write_text(json.dumps(DESIGN))
    code, out = run(capsys, "designs", "save", str(f), "--name", "Shag cup")
    assert code == 0 and json.loads(out)["name"] == "Shag cup"
    code, out = run(capsys, "designs", "list", "--json")
    assert [d["name"] for d in json.loads(out)] == ["Shag cup"]
    code, out = run(capsys, "designs", "show", "shag cup")
    assert json.loads(out)["design"]["texture"] == "jacquard"
    code, out = run(capsys, "make", "--design", "Shag cup", "--draft", "--no-stls", "--out", str(tmp_path))
    assert code == 0
    code, out = run(capsys, "designs", "delete", "Shag cup")
    assert code == 0 and store.designs() == []


def test_options_lists_what_a_texture_takes(capsys):
    code, out = run(capsys, "options", "jacquard", "--json")
    keys = {o["key"] for o in json.loads(out)["options"]}
    assert code == 0 and {"loops", "loop_colour", "band", "material"} <= keys


def test_send_refuses_without_confirm(capsys):
    code, out = run(capsys, "send", "?shape=cup&texture=domes")
    assert code == 2 and "STARTS A PRINT" in json.loads(out)["error"]
