#!/usr/bin/env python3
import json
import socket
import threading
import time
import os
import subprocess

import netifaces
import ipaddress

import logging
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

from flask import Flask, request, jsonify

from openpilot.common.params import Params, ParamKeyType

# =========================
# 기본 설정
# =========================
UDP_PORT = 5004
HTTP_PORT = 5005
UDP_INTERVAL = 2.0
CLIENT_TIMEOUT = 5.0   # 초

PARAM_SCHEMA_PATH = "/data/openpilot/selfdrive/kisapilot/param_schema.json"
CMD_SCHEMA_PATH = "/data/openpilot/selfdrive/kisapilot/cmd_schema.json"

app = Flask(__name__)
params = Params()

# =========================
# 연결 상태 관리
# =========================
client_connected = False
last_seen = 0.0
running_cmds = {}


def is_client_alive():
    return client_connected and (time.time() - last_seen < CLIENT_TIMEOUT)


# =========================
# Param get / set
# =========================
def get_param_value(key: str):
    param_type = params.get_type(key)

    if param_type == ParamKeyType.BOOL:
        return params.get_bool(key), "BOOL"

    val = params.get(key)
    if val is None:
        return None, "STRING"

    try:
        if param_type == ParamKeyType.INT:
            return int(val), "INT"
        elif param_type == ParamKeyType.FLOAT:
            return float(val), "FLOAT"
        else:
            return val, "STRING"
    except Exception:
        return val, "STRING"


def set_param_value(key: str, val):
    param_type = params.get_type(key)

    if param_type == ParamKeyType.BOOL:
        params.put_bool(key, bool(val))
    else:
        if param_type == ParamKeyType.INT:
            params.put(key, int(val))
        elif param_type == ParamKeyType.FLOAT:
            params.put(key, float(val))
        else:
            params.put(key, str(val))


@app.route("/param/get_all", methods=["GET"])
def param_get_all():
    try:
        with open(PARAM_SCHEMA_PATH, "r") as f:
            schema = json.load(f)
            
        all_values = {}
        for item in schema:
            key = item["param"]
            val, _ = get_param_value(key)
            all_values[key] = val
            
        return jsonify(all_values)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/log/tmux", methods=["GET"])
def get_tmux_log():
    try:
        # tmux 세션의 화면을 캡처하는 명령어
        # -pt 0 : 타겟 세션 '0'의 패널 내용을 출력(p)
        # -S -100 : 최근 100줄만 가져오기 (너무 많으면 느려질 수 있음)
        # -e : ANSI 색상 코드 포함 (앱에서 색상 파싱을 하므로 포함해서 보냄)

        cmd = ["tmux", "capture-pane", "-pt", "comma", "-S", "-300", "-e", "-J"]

        
        # 명령어 실행
        # errors='ignore' 또는 'replace'를 써서 디코딩 에러 방지
        output = subprocess.check_output(cmd, encoding='utf-8', errors='replace')
        
        return jsonify({"log": output})

    except subprocess.CalledProcessError as e:
        # tmux가 실행 중이지 않거나 세션이 없을 때
        return jsonify({"log": f"Error: tmux session not found or command failed.\n{str(e)}"}), 500
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# =========================
# HTTP API
# =========================
@app.route("/health", methods=["GET"])
def health():
    global client_connected, last_seen
    client_connected = True
    last_seen = time.time()

    return jsonify({
        "status": "ok",
        "device": "kisapilot",
        "port": HTTP_PORT
    })


@app.route("/ping", methods=["GET"])
def ping():
    global client_connected, last_seen
    client_connected = True
    last_seen = time.time()
    return "ok"


@app.route("/param/schema", methods=["GET"])
def param_schema():
    with open(PARAM_SCHEMA_PATH, "r") as f:
        return jsonify(json.load(f))


@app.route("/param/get", methods=["GET"])
def param_get():
    key = request.args.get("name")
    if not key:
        return jsonify({"error": "missing param name"}), 400

    value, value_type = get_param_value(key)

    return jsonify({
        "param": key,
        "value": value,
        "value_type": value_type
    })


@app.route("/param/set", methods=["POST"])
def param_set():
    data = request.json
    key = data.get("param")
    val = data.get("value")

    if key is None:
        return jsonify({"error": "missing param"}), 400

    set_param_value(key, val)

    if key == "UpdaterTargetBranch":
        try:
            os.system("pkill -SIGHUP -f system.updated.updated")
            print(f"Executed os.system(pkill -SIGHUP) for branch: {val}")
        except Exception as e:
            print(f"Failed to execute pkill: {e}")

    return jsonify({"status": "ok"})

@app.route("/cmd/list", methods=["GET"])
def cmd_list():
    try:
        with open(CMD_SCHEMA_PATH, "r") as f:
            schema = json.load(f)

        cmds = []
        for c in schema:
            cmds.append({
                "title": c.get("title"),
                "cmd": c.get("cmd"),
                "description": c.get("description", ""),
                "confirm": c.get("confirm", False),
                "onroad": c.get("onroad", True)
            })

        return jsonify(cmds)

    except FileNotFoundError:
        return jsonify({"error": "cmd_schema.json not found"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500


import uuid

@app.route("/cmd/run", methods=["POST"])
def run_cmd():
    data = request.json
    cmd_id = data.get("cmd")

    with open(CMD_SCHEMA_PATH) as f:
        schema = json.load(f)

    entry = next((c for c in schema if c["cmd"] == cmd_id), None)
    if not entry:
        return jsonify({"error": "cmd not found"}), 404

    if entry.get("onroad") is False and params.get_bool("IsOnroad"):
        return jsonify({"error": "blocked while driving"}), 403

    cmd_uuid = str(uuid.uuid4())
    running_cmds[cmd_uuid] = {
        "output": "",
        "done": False
    }

    def runner():
        proc = subprocess.Popen(
            entry["exec"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True
        )

        for line in proc.stdout:
            running_cmds[cmd_uuid]["output"] += line

        proc.wait()
        running_cmds[cmd_uuid]["done"] = True

    threading.Thread(target=runner, daemon=True).start()

    return jsonify({
        "status": "started",
        "id": cmd_uuid
    })

@app.route("/cmd/output", methods=["GET"])
def cmd_output():
    cmd_id = request.args.get("id")
    if not cmd_id or cmd_id not in running_cmds:
        return jsonify({"error": "invalid id"}), 404

    return jsonify(running_cmds[cmd_id])


def get_broadcast_addresses():
    results = []

    for iface in netifaces.interfaces():
        if iface == "lo":
            continue

        iface_addrs = netifaces.ifaddresses(iface)
        if netifaces.AF_INET not in iface_addrs:
            continue

        for link in iface_addrs[netifaces.AF_INET]:
            ip = link.get("addr")
            netmask = link.get("netmask")

            if not ip or not netmask:
                continue

            try:
                network = ipaddress.IPv4Network(f"{ip}/{netmask}", strict=False)
                results.append((str(network.broadcast_address), ip))
            except Exception:
                pass

    return results


# =========================
# UDP 브로드캐스트
# =========================
def udp_broadcast_loop():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

    while True:
        if not is_client_alive():
            for bcast, local_ip in get_broadcast_addresses():
                msg = json.dumps({
                    "device": "kisapilot",
                    "ip": local_ip,
                    "port": HTTP_PORT
                }).encode("utf-8")

                try:
                    sock.sendto(msg, (bcast, UDP_PORT))
                    # print(
                    #     f"UDP Broadcasting: {bcast}:{UDP_PORT} "
                    #     f"msg={msg.decode('utf-8')}"
                    # )
                except Exception as e:
                    print("UDP error:", e)

        time.sleep(UDP_INTERVAL)



# =========================
# Main
# =========================
def main():
    t = threading.Thread(target=udp_broadcast_loop, daemon=True)
    t.start()

    app.run(host="0.0.0.0", port=HTTP_PORT, threaded=True)


if __name__ == "__main__":
    main()
