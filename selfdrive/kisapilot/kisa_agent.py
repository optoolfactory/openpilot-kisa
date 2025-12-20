#!/usr/bin/env python3
import json
import socket
import threading
import time
import datetime
import os
import subprocess

import netifaces
import ipaddress
import requests

import logging
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

from flask import Flask, request, jsonify, send_from_directory, Response, render_template_string, send_file

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

MODEL_LIST_PATH = "/data/openpilot/selfdrive/modeld/models/ModelList"
MODELS_PATH = "/data/openpilot/selfdrive/modeld/models/"

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


def ffmpeg_mp4_wrap_process_builder(filename):
  command_line = [
      "ffmpeg",      "-f", "hevc",
      "-r", "20",
      "-i", filename,
      "-c", "copy",
      "-vtag", "hvc1",
      "-movflags", "faststart+frag_keyframe+default_base_moof",
      "-f", "mp4",
      "-"
  ]
  return subprocess.Popen(command_line, stdout=subprocess.PIPE)

def video_to_img(input_path, output_path):
    if os.path.exists(output_path):
        return
    try:
        command = []
        frame_to_extract = 5
        time_to_extract = "3"

        if input_path.endswith('.hevc'):
            print(f"-> Using HEVC optimized command for: {input_path}")
            command = [
                "ffmpeg",
                "-skip_frame", "nokey",
                "-i", input_path,
                "-vf", f"select=gte(n\,{frame_to_extract}),scale=640:-1",
                "-frames:v", "1",
                "-vsync", "0",
                "-an", "-sn", "-dn",
                "-q:v", "3",
                "-y", output_path
            ]
        else:
            print(f"-> Using MP4 optimized command for: {input_path}")
            command = [
                "ffmpeg",
                "-i", input_path,
                "-ss", time_to_extract,
                "-vf", "scale=640:-1",
                "-frames:v", "1",
                "-y", output_path
            ]

        subprocess.run(command, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print(f"Thumbnail created: {output_path}")
    except Exception as e:
        print(f"Failed to create thumbnail for {input_path}: {e}")

def update_thumbnails_in_background(path):
    try:
        current_folder = os.path.basename(path)
        videos_thumbnail_dir = "/data/media/0/videos"
        if not os.path.exists(videos_thumbnail_dir):
            os.makedirs(videos_thumbnail_dir)

        for item_name in sorted(os.listdir(path)):
            item_path = os.path.join(path, item_name)
            is_dir = os.path.isdir(item_path)

            if current_folder == 'realdata' and is_dir and item_name.endswith("--0"):
                fcamera_path = os.path.join(item_path, "fcamera.hevc")

                preview_path = os.path.join(item_path, "preview.jpg")

                if os.path.exists(fcamera_path):
                    video_to_img(fcamera_path, preview_path)

            elif current_folder == 'videos' and not is_dir and item_name.endswith('.mp4'):
                mp4_path = item_path
                preview_path = os.path.join(videos_thumbnail_dir, os.path.splitext(item_name)[0] + '.jpg')
                video_to_img(mp4_path, preview_path)
                
    except Exception as e:
        print(f"[BG Thread] Error during thumbnail generation: {e}")

def get_item_details(item_path):
    is_dir = os.path.isdir(item_path)
    name = os.path.basename(item_path)
    try:
        size = os.path.getsize(item_path)
        modified_time = os.path.getmtime(item_path)
        modified_date = datetime.datetime.fromtimestamp(modified_time).strftime('%Y-%m-%d %H:%M:%S')
    except Exception:
        size = -1
        modified_date = "N/A"
    return {"name": name, "path": item_path, "is_dir": is_dir, "size": size, "modified": modified_date}

@app.route('/files', methods=['GET'])
def list_files():
    path = request.args.get('path', '/data/openpilot')
    
    if not os.path.isdir(path):
        return jsonify({"error": "Path is not a valid directory"}), 404

    items = []
    try:
        for item_name in sorted(os.listdir(path)):
            try:
                items.append(get_item_details(os.path.join(path, item_name)))
            except Exception:
                pass
        return jsonify({"path": path, "items": items})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/realdata_files', methods=['GET'])
def list_realdata_files_recursively():
    path = '/data/media/0/realdata'

    if not os.path.isdir(path):
        return jsonify({"error": "Realdata path not found"}), 404

    thread = threading.Thread(target=update_thumbnails_in_background, args=(path,))
    thread.start()

    items = []
    try:
        for dirpath, dirnames, filenames in os.walk(path):
            if dirpath == path:
                for dirname in dirnames:
                    try: items.append(get_item_details(os.path.join(dirpath, dirname)))
                    except Exception: pass
            for filename in filenames:
                try: items.append(get_item_details(os.path.join(dirpath, filename)))
                except Exception: pass
        
        return jsonify({"path": path, "items": items})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/videos_files', methods=['GET'])
def list_videos_files_filtered():
    path = '/data/media/0/videos'

    if not os.path.isdir(path):
        return jsonify({"error": "Videos path not found"}), 404

    thread = threading.Thread(target=update_thumbnails_in_background, args=(path,))
    thread.start()

    items = []
    try:
        for item_name in sorted(os.listdir(path)):
            if item_name.endswith('.mp4'):
                try:
                    items.append(get_item_details(os.path.join(path, item_name)))
                except Exception:
                    pass
        
        return jsonify({"path": path, "items": items})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/file/image', methods=['GET'])
def get_image_content():
    file_path = request.args.get('path', '')

    if not file_path:
        return Response("Path parameter is missing", status=400)

    try:
        if os.path.exists(file_path) and os.path.isfile(file_path) and file_path.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.bmp')):
            with open(file_path, 'rb') as f:
                image_data = f.read()
            import io
            return send_file(io.BytesIO(image_data),
                mimetype='image/jpeg'
            )
        else:
            return Response("Image not found or not a valid image file", status=404)
    except Exception as e:
        print(f"Error reading image file {file_path}: {e}")
        return Response(f"Error: {str(e)}", status=500)

@app.route('/playlist/<path:segment_path>')
def create_playlist_player(segment_path):
    try:
        route_segment_full, video_filename = os.path.split(segment_path)
        current_segment_name = os.path.basename(route_segment_full)
        route_name = current_segment_name.rsplit('--', 1)[0]
        realdata_path = '/data/media/0/realdata'
        all_segments = sorted([
            d for d in os.listdir(realdata_path)
            if os.path.isdir(os.path.join(realdata_path, d)) and d.startswith(route_name)
        ])

        video_playlist = []
        for segment in all_segments:
            video_url = f"/media/realdata/{segment}/{video_filename}"
            video_playlist.append(video_url)

        current_video_full_url = f"/media/{segment_path}"
        try:
            start_index = video_playlist.index(current_video_full_url)
        except ValueError:
            start_index = 0

        return render_template_string('''
            <!DOCTYPE html>
            <html>
            <head>
                <title>KisaPilot Video Player</title>
                <meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=no">
                <style>
                    body, html { margin: 0; padding: 0; width: 100%; height: 100%; overflow: hidden; background-color: black; color: white; font-family: sans-serif; }
                    video { width: 100%; height: 100%; object-fit: contain; }
                    .controls {
                        position: absolute;
                        bottom: 20px;
                        left: 50%;
                        transform: translateX(-50%);
                        display: flex;
                        gap: 20px;
                        background-color: rgba(0, 0, 0, 0.5);
                        padding: 10px 20px;
                        border-radius: 20px;
                        opacity: 0; /* 평소에는 숨김 */
                        transition: opacity 0.3s;
                    }
                    body:hover .controls {
                        opacity: 1; /* 마우스 올리면 보이게 */
                    }
                    .controls button {
                        background: none;
                        border: 2px solid white;
                        color: white;
                        border-radius: 50%;
                        width: 50px;
                        height: 50px;
                        font-size: 24px;
                        cursor: pointer;
                        display: flex;
                        align-items: center;
                        justify-content: center;
                    }
                </style>
            </head>
            <body>
                <video id="player" controls autoplay muted playsinline></video>

                <!-- ★★★ 이전/다음 버튼 UI 추가 ★★★ -->
                <div class="controls">
                    <button id="prevBtn">«</button>
                    <button id="nextBtn">»</button>
                </div>

                <script>
                    const videoPlayer = document.getElementById('player');
                    const prevBtn = document.getElementById('prevBtn');
                    const nextBtn = document.getElementById('nextBtn');

                    const playlist = {{ playlist_json | safe }};
                    let currentIndex = {{ start_index }};

                    function playVideo(index) {
                        if (index >= 0 && index < playlist.length) {
                            currentIndex = index;
                            videoPlayer.src = playlist[currentIndex];
                            videoPlayer.load();
                            videoPlayer.play();
                        }
                    }

                    // --- 버튼 클릭 이벤트 ---
                    prevBtn.addEventListener('click', () => {
                        let prevIndex = currentIndex - 1;
                        if (prevIndex < 0) {
                            prevIndex = playlist.length - 1; // 마지막 영상으로 이동
                        }
                        playVideo(prevIndex);
                    });

                    nextBtn.addEventListener('click', () => {
                        let nextIndex = currentIndex + 1;
                        if (nextIndex >= playlist.length) {
                            nextIndex = 0; // 처음 영상으로 이동
                        }
                        playVideo(nextIndex);
                    });

                    // --- 영상 종료 시 자동 다음 재생 ---
                    videoPlayer.addEventListener('ended', () => {
                        nextBtn.click(); // 다음 버튼을 클릭하는 것과 동일하게 처리
                    });

                    // 페이지 로드 시 첫 비디오 재생 시작
                    playVideo(currentIndex);
                </script>
            </body>
            </html>
        ''', playlist_json=json.dumps(video_playlist), start_index=start_index)

    except Exception as e:
        return f"Error creating playlist: {str(e)}", 500

@app.route('/file/delete', methods=['POST'])
def delete_files():
    data = request.get_json()
    if not data or 'paths' not in data:
        return jsonify({"error": "Paths parameter is missing in request body"}), 400

    paths_to_delete = data['paths']
    if not isinstance(paths_to_delete, list):
        return jsonify({"error": "Paths parameter must be a list"}), 400

    allowed_dirs = ['/data/media/0/videos', '/data/media/0/realdata']
    deleted_count = 0
    errors = []

    for item_path in paths_to_delete:
        try:
            is_allowed = any(os.path.commonpath([allowed_dir, os.path.abspath(item_path)]) == allowed_dir for allowed_dir in allowed_dirs)
            if not is_allowed:
                errors.append(f"Deletion not allowed for: {item_path}")
                continue

            if os.path.isdir(item_path):
                import shutil
                shutil.rmtree(item_path)
                print(f"Directory deleted: {item_path}")
                deleted_count += 1
            elif os.path.exists(item_path):
                os.remove(item_path)
                thumbnail_path = os.path.splitext(item_path)[0] + '.jpg'
                if os.path.exists(thumbnail_path):
                    os.remove(thumbnail_path)
                print(f"File deleted: {item_path}")
                deleted_count += 1
            else:
                errors.append(f"Not found: {item_path}")

        except Exception as e:
            errors.append(f"Error deleting {item_path}: {str(e)}")
            print(f"Error deleting {item_path}: {e}")

    if not errors:
        return jsonify({"success": True, "message": f"{deleted_count} items deleted."})
    else:
        return jsonify({"success": False, "message": f"{deleted_count} items deleted, but some errors occurred.", "errors": errors}), 207


@app.route('/file/exists', methods=['GET'])
def file_exists():
    path = request.args.get('path')
    if not path:
        return jsonify({"error": "Path parameter is missing"}), 400

    if os.path.exists(path):
        return jsonify({"exists": True, "path": path})
    else:
        return jsonify({"exists": False, "path": path})


@app.route('/media/<path:filename>')
def serve_media(filename):
    file_path = os.path.join('/data/media/0', filename)

    if not os.path.exists(file_path):
        return "File not found", 404

    if file_path.lower().endswith('.hevc'):
        process = ffmpeg_mp4_wrap_process_builder(file_path)
        
        def generate():
            with process.stdout as pipe:
                while True:
                    chunk = pipe.read(4096)
                    if not chunk:
                        break
                    yield chunk
        
        return Response(generate(), mimetype='video/mp4')
    
    else:
        return send_from_directory('/data/media/0', filename)


# =========================
# Model Selector
# =========================
@app.route('/models', methods=['GET'])
def get_models():
    current_model_prefix = params.get("DrivingModel")
    current_model_display_name = "Original Model"

    if current_model_prefix:
        current_model_display_name = current_model_prefix.replace("_", " ")

    all_custom_models = []
    try:
        with open(MODEL_LIST_PATH, 'r') as f:
            for line in f:
                parts = line.strip().split()
                if len(parts) >= 3:
                    all_custom_models.append(parts[2])
    except Exception:
        pass

    display_model_list = []
    
    is_latest_model = False
    if all_custom_models and current_model_prefix == all_custom_models[0]:
        is_latest_model = True

    if not is_latest_model:
        latest_model_for_display = None
        if all_custom_models:
            for model_prefix in all_custom_models:
                if model_prefix != current_model_prefix:
                    latest_model_for_display = model_prefix.replace("_", " ")
                    break
            if latest_model_for_display is None:
                latest_model_for_display = all_custom_models[0].replace("_", " ")

        restore_item_name = "Original" 
        if latest_model_for_display:
            restore_item_name = f"Original_with_latest:{latest_model_for_display}"

        display_model_list.append({
            "name": restore_item_name,
            "prefix": "Original"
        })

    latest_model_prefix_for_restore = None
    if not is_latest_model and 'latest_model_for_display' in locals() and locals()['latest_model_for_display']:
        latest_model_prefix_for_restore = locals()['latest_model_for_display'].replace(" ", "_")

    for model_prefix in all_custom_models:
        if model_prefix != current_model_prefix and model_prefix != latest_model_prefix_for_restore:
            display_model_list.append({
                "name": model_prefix.replace("_", " "),
                "prefix": model_prefix
            })

    response_data = {
        "current_model": current_model_display_name,
        "models": display_model_list
    }
    
    return jsonify(response_data)


@app.route('/file/size', methods=['GET'])
def get_file_size():
    file_path = request.args.get("path")
    if not file_path:
        return jsonify({"error": "missing file path"}), 400

    try:
        if os.path.exists(file_path):
            size = os.path.getsize(file_path)
            return jsonify({"path": file_path, "size": size})
        else:
            return jsonify({"path": file_path, "size": -1})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/file/remote_size', methods=['GET'])
def get_remote_file_size():
    url = request.args.get("url")
    if not url:
        return jsonify({"error": "missing url"}), 400

    try:
        response = requests.head(url, timeout=5, allow_redirects=True)
        response.raise_for_status()
        
        size = int(response.headers.get('Content-Length', -1))
        
        return jsonify({"url": url, "size": size})
    except Exception as e:
        return jsonify({"error": str(e), "size": -1}), 500


def change_model_task(model_prefix):
    log_path = "/data/model/download.log"
    subprocess.run(f"mkdir -p /data/model && > {log_path}", shell=True)
    
    subprocess.run(f"echo 'Removing old model files...' >> {log_path}", shell=True)
    subprocess.run("rm -f /data/openpilot/selfdrive/modeld/models/driving_*", shell=True)

    subprocess.run(f"echo 'Downloading driving_policy...' >> {log_path}", shell=True)
    policy_url = f"https://raw.githubusercontent.com/kisapilot/model/main/models/{model_prefix}_driving_policy"
    policy_dest = f"/data/model/{model_prefix}_driving_policy"
    subprocess.run(f"wget -O {policy_dest} {policy_url}", shell=True, stderr=subprocess.STDOUT, stdout=open(log_path, 'a'))

    subprocess.run(f"echo 'Downloading driving_vision...' >> {log_path}", shell=True)
    vision_url = f"https://raw.githubusercontent.com/kisapilot/model/main/models/{model_prefix}_driving_vision"
    vision_dest = f"/data/model/{model_prefix}_driving_vision"
    subprocess.run(f"wget -O {vision_dest} {vision_url}", shell=True, stderr=subprocess.STDOUT, stdout=open(log_path, 'a'))

    subprocess.run(f"echo 'Applying model...' >> {log_path}", shell=True)
    subprocess.run(f"cp -f {policy_dest} /data/openpilot/selfdrive/modeld/models/driving_policy.onnx", shell=True)
    subprocess.run(f"cp -f {vision_dest} /data/openpilot/selfdrive/modeld/models/driving_vision.onnx", shell=True)

    subprocess.run("touch /data/ks", shell=True)
    subprocess.run(f"echo 'Rebooting...' >> {log_path}", shell=True)
    
    params = Params()
    params.put("DrivingModel", model_prefix)
    params.put_bool("DoReboot", True)


@app.route('/model/change', methods=['POST'])
def change_model():
    data = request.get_json()
    model_prefix = data.get('prefix')
    if not model_prefix:
        return jsonify({"error": "Missing model prefix"}), 400
    
    task_thread = threading.Thread(target=change_model_task, args=(model_prefix,))
    task_thread.start()
    
    return jsonify({"status": "Model change process started"}), 200


@app.route('/log/download', methods=['GET'])
def get_download_log():
    try:
        with open("/data/model/download.log", "r") as f:
            return f.read()
    except FileNotFoundError:
        return "Log file not found."
    except Exception as e:
        return str(e)

@app.route('/model/restore_original', methods=['POST'])
def restore_original_model():
    params.put("DrivingModel", "")
    
    cmd = "rm -f /data/openpilot/selfdrive/modeld/models/driving_*; " + \
          "git -C /data/openpilot/selfdrive/modeld/models checkout driving_policy.onnx; " + \
          "git -C /data/openpilot/selfdrive/modeld/models checkout driving_vision.onnx; " + \
          "touch /data/ks"
          
    subprocess.run(cmd, shell=True)
    params.put_bool("DoReboot", True)
    
    return jsonify({"status": "Original model restoration process started"}), 200

# =========================
# Param get / set
# =========================
@app.route("/param_schema.json", methods=["GET"])
def get_param_schema():
    try:
        if not os.path.exists(PARAM_SCHEMA_PATH):
            return jsonify({"error": "Schema file not found"}), 404

        with open(PARAM_SCHEMA_PATH, "r") as f:
            schema_list = json.load(f)

        for item in schema_list:
            key = item.get("param")
            if key:
                current_val, val_type = get_param_value(key)

                if current_val is None:
                    default_val = item.get("default", "")
                    item["value"] = str(default_val)
                else:
                    if isinstance(current_val, bytes):
                         try:
                             item["value"] = current_val.decode("utf-8").strip()
                         except:
                             item["value"] = str(current_val)
                    else:
                        item["value"] = str(current_val)
                
                item["value_type"] = val_type

        return jsonify(schema_list)

    except Exception as e:
        return jsonify({"error": str(e)}), 500

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
        if isinstance(val, str):
            val_bool = val.lower() in ("1", "true", "yes", "on")
        else:
            val_bool = bool(val)
        params.put_bool(key, val_bool)
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
            # -SIGHUP : 즉시 다운로드 시작 (Fetch)
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


@app.route("/cmd/exec_raw", methods=["POST"])
def exec_raw_cmd():
    try:
        data = request.json
        cmd_str = data.get("cmd")

        if not cmd_str:
            return jsonify({"error": "missing cmd"}), 400

        print(f"Executing RAW command: {cmd_str}")

        def runner():
            subprocess.run(cmd_str, shell=True)

        threading.Thread(target=runner, daemon=True).start()

        return jsonify({"status": "started", "cmd": cmd_str})

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/cmd/output", methods=["GET"])
def cmd_output():
    cmd_id = request.args.get("id")
    if not cmd_id or cmd_id not in running_cmds:
        return jsonify({"error": "invalid id"}), 404

    return jsonify(running_cmds[cmd_id])


@app.route('/file/content', methods=['GET'])
def get_file_content():
    path = request.args.get('path')

    if not path or not os.path.exists(path) or os.path.isdir(path):
        return "File not found or is a directory.", 404

    try:
        with open(path, 'r', errors='ignore') as f:
            content = f.read()
            return content
    except Exception as e:
        return f"Error reading file: {str(e)}", 500


@app.route('/execute_fingerprint', methods=['GET'])
def execute_fingerprint():
    realdata_path = '/data/media/0/realdata'
    
    if not os.path.exists(realdata_path) or not os.path.isdir(realdata_path):
        return jsonify({"error": "Drive log directory (/data/media/0/realdata) not found."}), 404

    all_segments = [d for d in os.listdir(realdata_path) if os.path.isdir(os.path.join(realdata_path, d))]
    if not all_segments:
        return jsonify({"error": "No drive logs found. Please enable the drive log toggle and drive for about 10 minutes."}), 404
    
    latest_segment_folder = sorted(all_segments)[-1]
    qlog_path = os.path.join(realdata_path, latest_segment_folder, 'qlog.zst')
    
    if not os.path.exists(qlog_path):
        return jsonify({"error": f"qlog.zst not found in the latest drive log: {qlog_path}"}), 404

    script_path = '/data/openpilot/selfdrive/debug/fingerprint_from_route.py'
    command = ['python', script_path, qlog_path]
    
    print(f"Executing command: {' '.join(command)}")

    try:
        result = subprocess.run(command, capture_output=True, text=True, check=True)
        full_output = result.stdout
        
        lines = full_output.splitlines()
        
        start_index = -1
        for i, line in enumerate(lines):
            if "FW fingerprint:" in line:
                start_index = i + 1
                break
        
        if start_index == -1:
            return jsonify({"error": "Could not find 'FW fingerprint:' in the script output.", "output": full_output}), 500

        end_index = -1
        for i, line in enumerate(lines[start_index:], start=start_index):
            if "VIN:" in line:
                end_index = i
                break

        if end_index == -1:
            extracted_lines = lines[start_index:]
        else:
            extracted_lines = lines[start_index:end_index]
        
        final_result = "\n".join([line for line in extracted_lines if line.strip()])

        return jsonify({"fingerprint": final_result})

    except subprocess.CalledProcessError as e:
        error_message = f"Script execution failed (Exit Code: {e.returncode}):\n{e.stderr}"
        print(error_message)
        return jsonify({"error": error_message}), 500
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        return jsonify({"error": str(e)}), 500


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
