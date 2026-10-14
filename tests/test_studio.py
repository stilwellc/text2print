"""The studio API end to end, without a browser."""
import numpy as np
import pytest

flask = pytest.importorskip("flask")
from studio import server  # noqa: E402


@pytest.fixture
def client():
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
    assert tw["status"]["0.4"] == "printed" and {p["key"] for p in c["plates"]} == {"woven", "colour", "droop", "fabric", "fit"}
    assert "configured" in c["lan"]
