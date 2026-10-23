"""Doble del proceso `codex app-server` para probar el cliente: habla el protocolo, no inventa datos de uso.

Modo (variable FAKE_CODEX_MODE): ok | noisy | nologin | error | hang | die.
La respuesta de limites sale de la captura real indicada en FAKE_CODEX_FIXTURE.
"""
import json
import os
import sys
import time

mode = os.environ.get("FAKE_CODEX_MODE", "ok")
if os.environ.get("FAKE_CODEX_PIDFILE"):
    with open(os.environ["FAKE_CODEX_PIDFILE"], "w") as fh:
        fh.write(str(os.getpid()))
if mode == "die":
    sys.exit(1)


def send(obj):
    sys.stdout.write(json.dumps(obj) + "\n")
    sys.stdout.flush()


for line in sys.stdin:
    msg = json.loads(line)
    method = msg.get("method")
    if method == "initialize":
        if mode == "noisy":
            send({"method": "remoteControl/status/changed", "params": {}})
            send({"method": "account/updated", "params": {}})
        send({"id": msg["id"], "result": {"codexHome": "x", "platformFamily": "windows", "platformOs": "windows",
                                           "userAgent": "fake"}})
    elif method == "account/rateLimits/read":
        if mode == "hang":
            time.sleep(60)
        elif mode == "nologin":
            send({"id": msg["id"], "error": {"code": -32000, "message": "Not logged in: please sign in first"}})
        elif mode == "error":
            send({"id": msg["id"], "error": {"code": -32603, "message": "boom"}})
        else:
            with open(os.environ["FAKE_CODEX_FIXTURE"], encoding="utf-8") as fh:
                send({"id": msg["id"], "result": json.load(fh)["result"]})
