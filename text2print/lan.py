"""Send a sliced project to a Bambu Lab printer on your LAN (Bambu's local protocol: FTPS upload + MQTT command).

Needs the printer's IP, serial and LAN access code (printer screen: Settings > Network), stored only on this machine
in ~/.text2print/printer.json. EXPERIMENTAL: built from Bambu's documented local protocol, not yet run against a
real P2S from this app. The studio always asks before sending, because sending starts a print."""
import ftplib
import hashlib
import json
import pathlib
import ssl
import time


class _ImplicitFTPS(ftplib.FTP_TLS):
    """Bambu printers speak implicit FTPS on port 990 with a self-signed certificate."""

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw); self._sock = None

    @property
    def sock(self):
        return self._sock

    @sock.setter
    def sock(self, value):
        if value is not None and not isinstance(value, ssl.SSLSocket):
            value = self.context.wrap_socket(value)
        self._sock = value

    def ntransfercmd(self, cmd, rest=None):                     # reuse the TLS session on the data channel
        conn, size = ftplib.FTP.ntransfercmd(self, cmd, rest)
        if self._prot_p:
            conn = self.context.wrap_socket(conn, server_hostname=self.host, session=self.sock.session)
        return conn, size


def _ctx():
    c = ssl.create_default_context(); c.check_hostname = False; c.verify_mode = ssl.CERT_NONE
    return c


def project_command(filename, name, ams_mapping, md5, use_ams=True):
    return {"print": {
        "sequence_id": str(int(time.time())), "command": "project_file", "param": "Metadata/plate_1.gcode",
        "project_id": "0", "profile_id": "0", "task_id": "0", "subtask_id": "0", "subtask_name": name,
        "url": f"ftp://{filename}", "md5": md5, "timelapse": False, "bed_type": "auto", "bed_levelling": True,
        "flow_cali": True, "vibration_cali": True, "layer_inspect": False,
        "use_ams": bool(use_ams), "ams_mapping": list(ams_mapping)}}


def check(cfg):
    missing = [k for k in ("ip", "serial", "access_code") if not cfg.get(k)]
    if missing:
        raise ValueError("printer not set up: " + ", ".join(missing))


def send(sliced_3mf, cfg, name, ams_mapping, timeout=60):
    """Upload a sliced 3MF (must contain Metadata/plate_1.gcode) and start it. Returns the command sent."""
    import zipfile
    check(cfg)
    path = pathlib.Path(sliced_3mf)
    with zipfile.ZipFile(path) as z:
        if "Metadata/plate_1.gcode" not in z.namelist():
            raise ValueError("that project isn't sliced")
    md5 = hashlib.md5(path.read_bytes()).hexdigest()
    remote = "".join(c if c.isalnum() or c in "-_." else "_" for c in path.stem)[:60] + ".3mf"
    ftp = _ImplicitFTPS(context=_ctx(), timeout=timeout)
    ftp.connect(cfg["ip"], 990); ftp.login("bblp", cfg["access_code"]); ftp.prot_p()
    with path.open("rb") as f:
        ftp.storbinary(f"STOR {remote}", f)
    ftp.quit()
    import paho.mqtt.client as mqtt
    cmd = project_command(remote, name, ams_mapping, md5)
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"text2print-{int(time.time())}")
    client.username_pw_set("bblp", cfg["access_code"]); client.tls_set_context(_ctx()); client.tls_insecure_set(True)
    client.connect(cfg["ip"], 8883, keepalive=30); client.loop_start()
    info = client.publish(f"device/{cfg['serial']}/request", json.dumps(cmd), qos=1); info.wait_for_publish(timeout)
    client.loop_stop(); client.disconnect()
    return cmd


def test(cfg, timeout=12):
    """Check the connection without printing: FTPS login + listing, then MQTT — ask for a status report (pushall)
    and read the printer's state and the AMS colours. -> {'ftps': ..., 'mqtt': ..., 'state', 'ams': [...]}"""
    check(cfg)
    out = {"ftps": None, "mqtt": None, "state": None, "nozzle_temp": None, "ams": []}
    try:
        ftp = _ImplicitFTPS(context=_ctx(), timeout=timeout)
        ftp.connect(cfg["ip"], 990); ftp.login("bblp", cfg["access_code"]); ftp.prot_p()
        names = ftp.nlst(); ftp.quit()
        out["ftps"] = f"ok — {len(names)} files on the printer"
    except Exception as e:
        out["ftps"] = f"failed: {type(e).__name__}: {e}"[:200]
    try:
        import paho.mqtt.client as mqtt
        got = {}

        def on_message(client, userdata, msg):
            try:
                d = json.loads(msg.payload)
            except ValueError:
                return
            if "print" in d:
                got.update(d["print"])

        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"text2print-test-{int(time.time())}")
        client.username_pw_set("bblp", cfg["access_code"]); client.tls_set_context(_ctx()); client.tls_insecure_set(True)
        client.on_message = on_message
        client.connect(cfg["ip"], 8883, keepalive=30); client.loop_start()
        client.subscribe(f"device/{cfg['serial']}/report")
        client.publish(f"device/{cfg['serial']}/request", json.dumps({"pushing": {"sequence_id": "0", "command": "pushall"}}))
        t0 = time.time()
        while time.time() - t0 < timeout and "gcode_state" not in got:
            time.sleep(0.2)
        client.loop_stop(); client.disconnect()
        if got:
            out["mqtt"] = "ok"; out["state"] = got.get("gcode_state"); out["nozzle_temp"] = got.get("nozzle_temper")
            for unit in (got.get("ams") or {}).get("ams", []):
                for tray in unit.get("tray", []):
                    if tray.get("tray_color"):
                        out["ams"].append({"slot": int(unit.get("id", 0)) * 4 + int(tray.get("id", 0)) + 1,
                                           "colour": "#" + tray["tray_color"][:6], "type": tray.get("tray_type", "")})
        else:
            out["mqtt"] = "connected, but no status report arrived — check the serial number"
    except Exception as e:
        out["mqtt"] = f"failed: {type(e).__name__}: {e}"[:200]
    return out
