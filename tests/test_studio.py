"""The studio API end to end, without a browser."""
import numpy as np
import pytest

flask = pytest.importorskip("flask")
from studio import server  # noqa: E402


@pytest.fixture
def client():
    server.app.testing = True
    return server.app.test_client()


def test_catalogue_lists_shapes_textures_and_nozzles(client):
    c = client.get("/api/catalogue").get_json()
    assert {s["key"] for s in c["shapes"]} >= {"tray", "cup", "vase"}
    assert any(t["family"] == "fabric" for t in c["textures"])
    assert [n["size"] for n in c["nozzles"]] == [0.2, 0.4, 0.6, 0.8]


def test_build_mesh_and_download(client):
    r = client.post("/api/build", json={"shape": "coaster", "texture": "grid", "params": {"width": 70, "dish": 0}})
    assert r.status_code == 200
    d = r.get_json()
    assert len(d["parts"]) == 2 and d["stats"]["swaps"] > 0
    raw = client.get(d["parts"][0]["url"]).data
    nv, nf = np.frombuffer(raw[:8], dtype=np.uint32)
    assert len(raw) == 8 + nv * 12 + nf * 12 and nf == d["parts"][0]["triangles"]
    dl = client.get(f"/api/job/{d['id']}/download")
    assert dl.status_code == 200 and dl.data[:2] == b"PK"


def test_incompatible_pick_is_a_clear_400(client):
    r = client.post("/api/build", json={"shape": "tile", "texture": "zigzag"})
    assert r.status_code == 400 and "doesn't fit" in r.get_json()["error"]


def test_index_serves_the_picker(client):
    assert b"text2print" in client.get("/").data


def test_draft_builds_and_superseded_requests(client):
    r = client.post("/api/build", json={"shape": "cup", "texture": "zigzag", "params": {"height": 30}, "draft": True})
    assert r.status_code == 200 and r.get_json()["draft"] is True


def test_send_needs_explicit_confirmation(client):
    jid = client.post("/api/build", json={"shape": "coaster", "texture": "grid", "params": {"width": 70, "dish": 0}}).get_json()["id"]
    r = client.post(f"/api/job/{jid}/send", json={})
    assert r.status_code == 400 and "confirm" in r.get_json()["error"]


def test_designs_and_printer_endpoints(client, tmp_path, monkeypatch):
    from text2print import store
    monkeypatch.setattr(store, "HOME", tmp_path)
    d = client.post("/api/designs", json={"name": "A", "link": "?shape=cup&texture=zigzag"}).get_json()
    assert client.get("/api/designs").get_json()[0]["id"] == d["id"]
    assert client.delete(f"/api/designs/{d['id']}").get_json()["ok"]
    r = client.post("/api/printer", json={"ip": "10.0.0.2", "serial": "X", "access_code": "Y", "name": "P2S"}).get_json()
    assert r["configured"] and "access_code" not in client.get("/api/printer").get_json()


def test_catalogue_has_status_plates_and_lan(client):
    c = client.get("/api/catalogue").get_json()
    tw = next(t for t in c["textures"] if t["key"] == "twill")
    assert tw["status"]["0.4"] == "printed" and {p["key"] for p in c["plates"]} == {"woven", "colour", "droop", "fabric", "fit", "band", "courses", "lids", "fur"}
    assert "configured" in c["lan"]


def test_only_the_studios_own_page_may_call_the_api(client):
    """The studio can write files, launch Claude and start a print: another site's script, or a page that has
    rebound its host name to 127.0.0.1, must be refused."""
    assert client.get("/api/designs").status_code == 200
    assert client.get("/api/designs", headers={"Host": "evil.example:7384"}).status_code == 403          # DNS rebinding
    assert client.post("/api/build", data="{}", headers={"Origin": "https://evil.example", "Content-Type": "text/plain"}).status_code == 403
    assert client.post("/api/taste", json={"verdict": "like"}, headers={"Origin": "http://evil.example:7384"}).status_code == 403
    assert client.post("/api/taste", json={"verdict": "nope"}, headers={"Origin": "http://localhost"}).status_code == 400   # own page: reaches the route


def test_a_saved_designs_id_can_never_be_a_path(client, tmp_path, monkeypatch):
    from text2print import store
    monkeypatch.setattr(store, "HOME", tmp_path / "home")
    r = client.post("/api/designs", json={"id": "../../pwn", "name": "x", "thumb": "data:image/png;base64,AAAA"}).get_json()
    assert r["id"] != "../../pwn" and not list(tmp_path.glob("**/pwn.png"))


# ── the studio says what the library does ─────────────────────────────────────────────────────────────────
COASTER = {"shape": "coaster", "texture": "grid", "params": {"width": 70, "dish": 0}}


def test_a_client_made_anywhere_reaches_the_api():
    """No fixture, no flag set by hand: this used to be 403 unless another studio test had run first."""
    assert server.app.test_client().get("/api/ask/nope/file/x.png").status_code == 404
    assert server.app.test_client().get("/api/catalogue").status_code == 200


def test_filament_label_is_the_real_preset_per_colour(client):
    from types import SimpleNamespace
    d = client.post("/api/build", json=COASTER).get_json()
    assert [f["preset"] for f in d["filaments"]] == ["Bambu PLA Matte"] * 2 and d["filaments"][0]["colour"].startswith("#")
    b = SimpleNamespace(nozzle=0.4, material=["petg", "pla"], project_colours=lambda: ["#111111", "#EEEEEE"],
                        per_filament={"filament_settings_id": ["Generic PETG @BBL P2S", "Bambu PLA Matte @BBL P2S"]})
    assert server._filaments(b) == [{"colour": "#111111", "preset": "Generic PETG"}, {"colour": "#EEEEEE", "preset": "Bambu PLA Matte"}]
    r = client.post("/api/build", json=dict(COASTER, options={"material": "petg"}))
    if r.status_code == 200:                                    # needs Bambu Studio's PETG preset on this machine
        assert {f["preset"] for f in r.get_json()["filaments"]} == {"Generic PETG"}
    else:
        assert r.status_code == 400 and "preset" in r.get_json()["error"]


def test_badges_follow_the_material(client, tmp_path, monkeypatch):
    import json
    from text2print import verify
    f = tmp_path / "verified.json"
    f.write_text(json.dumps({"twill@0.4": {"result": "ok"}, "twill@0.4@petg": {"result": "fail"}, "grid@0.6@petg-hf": {"result": "ok"}}))
    monkeypatch.setattr(verify, "FILE", f)
    tex = {t["key"]: t for t in client.get("/api/catalogue").get_json()["textures"]}
    tw = tex["twill"]["status_by_material"]
    assert tw["pla"]["0.4"] == "printed" and tw["petg"]["0.4"] == "failed" and tw["petg"]["0.6"] == "untested"
    assert tex["twill"]["status"] == tw["pla"]
    assert tex["grid"]["status_by_material"]["petg-hf"]["0.6"] == "printed" and tex["grid"]["status"]["0.6"] != "printed"


def _wait_for_slice(client, jid):
    import time
    for _ in range(200):
        s = client.get(f"/api/job/{jid}/slice").get_json()
        if s["state"] != "running":
            return s
        time.sleep(0.05)
    raise AssertionError("the slice never finished")


def test_slice_keeps_the_slicers_own_changes_grams_and_warnings(client, tmp_path, monkeypatch):
    from text2print import bambu, store
    monkeypatch.setattr(store, "HOME", tmp_path)
    seen = {}

    def fake_slice(p3mf, workdir):
        seen["project"] = p3mf
        return {"time": "1h 2m", "minutes": 62.0, "grams": 12.5, "layers": 30, "grams_by_filament": [8.0, 4.5], "changes": 7,
                "warnings": ["It seems object has floating regions."], "sliced": str(tmp_path / "sliced.3mf")}
    monkeypatch.setattr(bambu, "slice_project", fake_slice)
    monkeypatch.setattr(bambu, "gcode_preview", lambda *a, **k: None)
    jid = client.post("/api/build", json=dict(COASTER, params={"width": 71, "dish": 0})).get_json()["id"]
    assert client.post(f"/api/job/{jid}/slice").status_code == 200
    s = _wait_for_slice(client, jid)
    assert s["state"] == "done" and s["changes"] == 7 and s["grams_by_filament"] == [8.0, 4.5]
    assert s["warnings"] == ["It seems object has floating regions."] and str(seen["project"]).endswith(".3mf")


def test_check_a_sliced_file_reports_what_the_gcode_does(client, tmp_path, monkeypatch):
    from text2print import bambu, store
    monkeypatch.setattr(store, "HOME", tmp_path)
    jid = client.post("/api/build", json=dict(COASTER, params={"width": 72, "dish": 0})).get_json()["id"]
    r = client.get(f"/api/job/{jid}/report")
    assert r.status_code == 409 and "Slice" in r.get_json()["error"]
    j = server.JOBS[jid]
    j["slice"] = {"state": "done", "minutes": 10, "grams": 3}
    r = client.get(f"/api/job/{jid}/report")                    # remembered numbers, no file: slice again
    assert r.status_code == 409 and "again" in r.get_json()["error"] and j["slice"] is None
    j["slice"] = {"state": "done", "minutes": 10, "grams": 3}
    (j["dir"] / "slice").mkdir(parents=True, exist_ok=True); (j["dir"] / "slice" / "sliced.3mf").write_bytes(b"PK")
    calls = []
    report = {"first_layer": {"Outer wall": {"mm": 400, "speed": 20, "fastest": 20}}, "rest": {}, "fastest_travel": {"first_layer": 300, "rest": 500},
              "accelerations": [300, 4000], "first_layer_order": ["T1"], "changes": 7, "time": "1h 2m", "grams_by_filament": [8.0, 4.5]}
    monkeypatch.setattr(bambu, "print_report", lambda f: calls.append(f) or report)
    assert client.get(f"/api/job/{jid}/report").get_json() == report
    assert client.get(f"/api/job/{jid}/report").get_json() == report and len(calls) == 1      # read once, kept with the slice
    assert store.get_slice(j["key"])["report"]["changes"] == 7


@pytest.mark.parametrize("body,word", [
    (dict(COASTER, colours=["#GGGGGG", "#EDE3D1"]), "#GGGGGG"),
    (dict(COASTER, colours=["red"]), "six-digit hex"),
    (dict(COASTER, colours="#8B3A2F"), "list"),
    (dict(COASTER, shape="teapot"), "Unknown shape"),
    (dict(COASTER, texture="tweed"), "Unknown texture"),
    (dict(COASTER, params={"width": "wide"}), "size 'width' must be a number"),
    (dict(COASTER, params=[70]), "params"),
    (dict(COASTER, nozzle=0.5), "0.2, 0.4, 0.6, 0.8"),
    (dict(COASTER, nozzle="big"), "nozzle must be a number"),
    (dict(COASTER, options="petg"), "options"),
    (dict(COASTER, options={"lid_colours": ["blue"]}), "'blue'"),
])
def test_bad_design_input_is_a_400_that_says_what_to_fix(client, body, word):
    r = client.post("/api/build", json=body)
    assert r.status_code == 400 and r.is_json and word in r.get_json()["error"]


def test_every_api_error_is_json(client):
    for path in ("/api/build", "/api/plates", "/api/designs", "/api/taste", "/api/printer"):
        for raw in ("{not json", "[1, 2]", ""):
            r = client.post(path, data=raw, content_type="application/json")
            assert r.status_code == 400 and "JSON object" in r.get_json()["error"], (path, raw)
    assert "nozzle" in client.post("/api/plates", json={"nozzle": "x"}).get_json()["error"]
    assert client.post("/api/plates", json={"plate": "nope"}).status_code == 400
    for path in ("/api/job/nope/download", "/api/job/nope/stls", "/api/job/nope/mesh/0", "/api/job/nope/slice", "/api/ask/nope",
                 "/api/image/nope", "/api/designs/nope/thumb", "/api/part/nope/download", "/api/nothing-here"):
        r = client.get(path)
        assert r.status_code == 404 and r.get_json()["error"], path
    jid = client.post("/api/build", json=COASTER).get_json()["id"]
    assert client.get(f"/api/job/{jid}/mesh/99").status_code == 404
    r = client.get("/api/designs", headers={"Host": "evil.example:7384"})
    assert r.status_code == 403 and r.get_json()["error"]
    assert client.get("/nothing-here").status_code == 404        # the page itself still answers as a page


def test_the_page_starts_with_no_network(client):
    """three.js is served from the studio's own files: a CDN link gave a blank page offline."""
    import json
    import re
    page = client.get("/").data.decode()
    assert "://" not in page
    imports = json.loads(re.search(r'<script type="importmap">(.*?)</script>', page, re.S).group(1))["imports"]
    three = client.get(imports["three"])
    assert three.status_code == 200 and b"SPDX-License-Identifier: MIT" in three.data[:200] and b"REVISION = '164'" in three.data[:300]
    assert client.get(imports["three/addons/"] + "controls/OrbitControls.js").status_code == 200
    assert b"MIT License" in client.get("/static/vendor/three/LICENSE").data
    for name in ("app.js", "app.css"):                          # nothing else is fetched from outside either
        assert not re.search(r"""(from|import|url\(|fetch\()\s*["'(]*https?://""", (server.STATIC / name).read_text()), name


def test_an_stl_becomes_a_project_with_a_drawing(client, tmp_path, monkeypatch):
    import io
    import trimesh
    monkeypatch.setattr(server, "WORK", tmp_path / "work")
    monkeypatch.setattr(server, "PARTS", type(server.PARTS)())
    stl = trimesh.creation.box(extents=(30, 20, 10)).export(file_type="stl")
    r = client.post("/api/part", data={"stl": (io.BytesIO(stl), "my bracket.stl"), "material": "pla", "colours": "#8B3A2F"},
                    content_type="multipart/form-data")
    assert r.status_code == 200, r.get_json()
    d = r.get_json()
    assert d["size"] == [30.0, 20.0, 10.0] and d["name"] == "my_bracket" and d["filaments"] == [{"colour": "#8B3A2F", "preset": "Bambu PLA Matte"}]
    assert client.get(d["drawing"]).data[:4] == b"\x89PNG" and client.get(d["download"]).data[:2] == b"PK"
    bad = lambda **f: client.post("/api/part", data=f, content_type="multipart/form-data").get_json()["error"]
    assert "Choose an STL" in bad(material="pla")
    assert "not an STL" in bad(stl=(io.BytesIO(stl), "part.obj"))
    assert "Couldn't read" in bad(stl=(io.BytesIO(b"not a mesh"), "junk.stl"))
    assert "Unknown material" in bad(stl=(io.BytesIO(stl), "a.stl"), material="wood")
    assert "not a colour" in bad(stl=(io.BytesIO(stl), "a.stl"), colours="red")
    assert "nozzle" in bad(stl=(io.BytesIO(stl), "a.stl"), nozzle="0.5")
    assert len(server.PARTS) == 1 and len(list((tmp_path / "work").iterdir())) == 1          # failed uploads leave nothing behind
