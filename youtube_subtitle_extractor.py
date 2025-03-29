import os
import sys
import re
import json
import subprocess
import urllib.parse
import concurrent.futures
from queue import Queue, Empty
from flask import Flask, request, Response, send_file, render_template_string, jsonify
import googleapiclient.discovery
import keyring
import threading
import socket
import webbrowser
import time

# --- 正規表現のコンパイル ---
PROGRESS_REGEX = re.compile(r'(\d{1,3}\.\d)%')
TAG_REGEX = re.compile(r"<[^>]+>")
TIME_REGEX = re.compile(r"\d{2}:\d{2}:\d{2}\.\d+")

# 設定ファイルパス（ユーザのホームディレクトリ直下に .subtitle_app_config.json）
CONFIG_PATH = os.path.join(os.path.expanduser("~"), ".subtitle_app_config.json")

def load_config():
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_config_to_file(config):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f)

# 出力先フォルダ選択（macOSはAppleScript、WindowsはTkinterを使用）
def choose_output_folder():
    folder = ""
    if sys.platform == "darwin":
        try:
            output = subprocess.check_output(
                ["osascript", "-e", 'POSIX path of (choose folder with prompt "出力先フォルダを選択してください")']
            )
            folder = output.decode('utf-8').strip()
        except Exception:
            folder = ""
    else:
        try:
            import tkinter as tk
            from tkinter import filedialog
            root = tk.Tk()
            root.withdraw()
            folder = filedialog.askdirectory(title="出力先フォルダを選択")
            root.destroy()
        except Exception:
            folder = ""
    return folder

# 履歴（簡易なグローバル変数；プロセス終了時にリセットされます）
HISTORY = []

app = Flask(__name__)

# HTMLテンプレート
HTML_TEMPLATE = """
<!doctype html>
<html lang="ja">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>字幕取得アプリ</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <link href="https://cdn.jsdelivr.net/npm/@mdi/font@7.2.96/css/materialdesignicons.min.css" rel="stylesheet">
    <style>
      :root {
        --primary-color: #6366f1;
        --success-color: #22c55e;
        --error-color: #ef4444;
        --background-light: #ffffff;
        --background-dark: #0f172a;
        --text-light: #1e293b;
        --text-dark: #f8fafc;
      }
      html, body {
        height: 100%;
      }
      body {
        font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
        background-color: var(--background-light);
        color: var(--text-light);
        transition: all 0.3s ease;
        overflow-y: auto;
      }
      /* ダークモード */
      body.dark-mode {
        background-color: var(--background-dark);
        color: var(--text-dark);
      }
      /* メインコンテナ */
      .main-container {
        max-width: 800px;
        margin: 2rem auto;
        padding: 0 1rem;
      }
      /* ヘッダー */
      .app-header {
        text-align: center;
        margin-bottom: 2.5rem;
      }
      .app-title {
        font-size: 2rem;
        font-weight: 700;
        letter-spacing: -0.025em;
        color: var(--primary-color);
        margin-bottom: 0.5rem;
      }
      /* 通知表示エリア */
      #notificationContainer {
        margin-bottom: 1rem;
      }
      /* 入力フォーム */
      .input-card {
        background: var(--background-light);
        border-radius: 1rem;
        padding: 2rem;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
        margin-bottom: 2rem;
      }
      body.dark-mode .input-card {
        background: #1e293b;
      }
      .form-control {
        border-radius: 0.75rem;
        padding: 1rem;
        border: 2px solid #e2e8f0;
        transition: all 0.3s ease;
      }
      .form-control:focus {
        border-color: var(--primary-color);
        box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.2);
      }
      /* プログレスバー */
      .progress-container {
        margin-top: 1.5rem;
      }
      .progress {
        height: 12px;
        border-radius: 6px;
        background-color: #e2e8f0;
        overflow: hidden;
      }
      .progress-bar {
        background-color: var(--primary-color);
        transition: width 0.3s ease;
      }
      /* ステータス表示 */
      .status-card {
        background: var(--background-light);
        border-radius: 1rem;
        padding: 1.5rem;
        margin-top: 1.5rem;
        box-shadow: 0 2px 4px rgba(0, 0, 0, 0.05);
      }
      body.dark-mode .status-card {
        background: #1e293b;
      }
      .status-item {
        display: flex;
        align-items: center;
        padding: 0.75rem 0;
        border-bottom: 1px solid #e2e8f0;
      }
      .status-item:last-child {
        border-bottom: none;
      }
      .status-icon {
        font-size: 1.25rem;
        margin-right: 1rem;
        width: 24px;
        text-align: center;
      }
      /* アクションボタン */
      .action-buttons {
        display: flex;
        gap: 0.75rem;
        justify-content: flex-end;
        margin-top: 1.5rem;
      }
      .btn-icon {
        display: inline-flex;
        align-items: center;
        gap: 0.5rem;
      }
      /* 設定モーダル */
      .modal-content {
        border-radius: 1rem;
        padding: 1.5rem;
      }
      body.dark-mode .modal-content {
        background-color: #1e293b;
      }
    </style>
    <script>
      // ページ読み込み時に保存されたテーマを復元
      document.addEventListener("DOMContentLoaded", function() {
        const theme = localStorage.getItem('theme') || 'light';
        if (theme === 'dark') {
          document.body.classList.add('dark-mode');
        } else {
          document.body.classList.remove('dark-mode');
        }
        // （通知音設定は削除済み）
      });
    </script>
  </head>
  <body class="light-mode">
    <div class="main-container">
      <!-- ヘッダー -->
      <div class="app-header">
        <h1 class="app-title">YouTube Subtitle Extractor</h1>
        <div class="action-buttons">
          <button id="toggleThemeBtn" class="btn btn-outline-secondary btn-icon">
            <i class="mdi mdi-theme-light-dark"></i>
          </button>
          <button id="settingsBtn" class="btn btn-outline-secondary btn-icon">
            <i class="mdi mdi-cog"></i>
          </button>
        </div>
      </div>
      <!-- 通知表示エリア（常時表示） -->
      <div id="notificationContainer"></div>
      <!-- メイン入力エリア -->
      <div class="input-card">
        <form id="mainForm">
          <div class="input-group">
            <input type="text" class="form-control" id="url" name="url" 
                   placeholder="https://www.youtube.com/..." 
                   aria-label="YouTube URL">
            <button type="submit" class="btn btn-primary btn-icon">
              <i class="mdi mdi-play"></i>
              実行
            </button>
          </div>
          <div class="progress-container">
            <div class="progress">
              <div id="overallProgress" class="progress-bar" role="progressbar" style="width: 0%"></div>
            </div>
          </div>
        </form>
      </div>
      <!-- ステータス表示 -->
      <div id="statusContainer" class="status-card"></div>
    </div>
    <!-- 設定モーダル -->
    <div class="modal fade" id="settingsModal" tabindex="-1" aria-labelledby="settingsModalLabel" aria-hidden="true">
      <div class="modal-dialog modal-dialog-centered">
        <form id="settingsForm" class="modal-content">
          <div class="modal-header">
            <h5 class="modal-title">アプリ設定</h5>
            <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="閉じる"></button>
          </div>
          <div class="modal-body">
            <!-- APIキーはパスワード入力で非表示 -->
            <div class="mb-3">
              <label for="api_key" class="form-label">API Key</label>
              <input type="password" class="form-control" id="api_key" name="api_key" placeholder="Your API Key">
            </div>
            <!-- 出力先はOSの標準機能で選択 -->
            <div class="mb-3">
              <label for="output_dest" class="form-label">出力先</label>
              <div class="input-group">
                <input type="text" class="form-control" id="output_dest" name="output_dest" placeholder="出力先ファイルパス" readonly>
                <button class="btn btn-outline-secondary" type="button" id="chooseFolderBtn">フォルダ選択</button>
              </div>
            </div>
            <div class="mb-3">
              <label for="port" class="form-label">ポート番号</label>
              <input type="text" class="form-control" id="port" name="port" placeholder="5000">
            </div>
            <div class="form-check">
              <input class="form-check-input" type="checkbox" id="auto_open_browser" name="auto_open_browser">
              <label class="form-check-label" for="auto_open_browser">
                自動ブラウザ起動
              </label>
            </div>
          </div>
          <div class="modal-footer">
            <button type="submit" class="btn btn-primary">保存</button>
          </div>
        </form>
      </div>
    </div>
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
    <script>
      // テーマ切り替え（選択色を localStorage に保存）
      document.getElementById('toggleThemeBtn').addEventListener('click', function() {
        const body = document.body;
        const isDark = body.classList.toggle('dark-mode');
        localStorage.setItem('theme', isDark ? 'dark' : 'light');
        this.innerHTML = isDark 
          ? '<i class="mdi mdi-weather-sunny"></i>'
          : '<i class="mdi mdi-weather-night"></i>';
      });

      // 設定モーダル表示
      document.getElementById('settingsBtn').addEventListener('click', function() {
        var settingsModal = new bootstrap.Modal(document.getElementById('settingsModal'));
        settingsModal.show();
      });

      // 出力フォルダ選択ボタンの処理
      document.getElementById('chooseFolderBtn').addEventListener('click', function() {
        fetch('/choose_output')
          .then(response => response.json())
          .then(data => {
            document.getElementById('output_dest').value = data.output_dest;
          });
      });

      // ステータス表示更新
      function addStatus(message, type = 'info') {
        const container = document.getElementById('statusContainer');
        const item = document.createElement('div');
        item.className = 'status-item';
        
        const iconMap = {
          info: 'mdi-information',
          success: 'mdi-check-circle',
          error: 'mdi-alert-circle'
        };
        
        // HTMLエスケープを簡易的に回避してリンクなどを埋め込むため innerHTML を使用
        item.innerHTML = `
          <i class="mdi ${iconMap[type]} status-icon text-${type}"></i>
          <div>${message}</div>
        `;
        container.prepend(item);
      }

      // メインフォーム送信処理
      document.getElementById('mainForm').addEventListener('submit', function(e) {
        e.preventDefault();
        // 前回の通知（画面上の通知）を消去
        document.getElementById('notificationContainer').innerHTML = '';
        // ステータス表示エリアをリセット
        document.getElementById('statusContainer').innerHTML = '';
        document.getElementById('overallProgress').style.width = '0%';

        const formData = new FormData(e.target);
        fetch('/process', { method: 'POST', body: formData }).then(response => {
          const reader = response.body.getReader();
          const decoder = new TextDecoder();
          
          function read() {
            reader.read().then(({done, value}) => {
              if (done) return;
              const text = decoder.decode(value);
              text.split("\\n").forEach(line => {
                try {
                  const msg = JSON.parse(line);
                  if(msg.type === "log") {
                    addStatus(msg.message, 'info');
                  } else if(msg.type === "overall_progress") {
                    const bar = document.getElementById('overallProgress');
                    bar.style.width = msg.progress + '%';
                  } else if(msg.type === "confirm") {
                    // 処理完了
                    addStatus('処理が完了しました', 'success');

                    // 結果確認ボタン
                    const btn = document.createElement('button');
                    btn.className = 'btn btn-success mt-2';
                    btn.innerHTML = '<i class="mdi mdi-file-document-outline"></i> 結果を確認';
                    btn.onclick = () => window.open(msg.preview, '_blank');
                    document.getElementById('statusContainer').appendChild(btn);

                    // 出力先を1回だけ表示
                    addStatus("出力先: <a href='/preview?file=" + msg.output + "' target='_blank'>" + msg.output + "</a>", 'info');

                    // 固定通知エリアに表示
                    const notifContainer = document.getElementById('notificationContainer');
                    const notifDiv = document.createElement('div');
                    notifDiv.className = 'alert alert-info';
                    notifDiv.innerHTML = "処理が完了しました。出力先: <a href='/preview?file=" + msg.output + "' target='_blank'>" + msg.output + "</a>";
                    notifContainer.innerHTML = "";
                    notifContainer.appendChild(notifDiv);

                    // デスクトップ通知
                    if (Notification.permission === "default") {
                      Notification.requestPermission();
                    }
                    if (Notification.permission === "granted") {
                      new Notification("処理完了", { body: "全動画の処理が完了しました。" });
                    }
                    // ※通知音再生処理は削除しました
                  }
                } catch(e) {}
              });
              read();
            });
          }
          read();
        });
      });

      // 設定フォーム送信処理
      document.getElementById('settingsForm').addEventListener('submit', function(e) {
        e.preventDefault();
        const formData = new FormData(e.target);
        fetch('/save_config', { method: 'POST', body: formData })
          .then(response => response.json())
          .then(data => {
            addStatus(data.message, 'success');
            // モーダルを閉じる
            var modalEl = document.getElementById('settingsModal');
            var modal = bootstrap.Modal.getInstance(modalEl);
            modal.hide();
          });
      });
    </script>
  </body>
</html>
"""

# --- YouTube API／字幕取得関連の関数 ---
def get_youtube_client(api_key):
    return googleapiclient.discovery.build("youtube", "v3", developerKey=api_key)

def extract_channel_id(url, api_key, youtube_client=None):
    if youtube_client is None:
        youtube_client = get_youtube_client(api_key)
    if "/channel/" in url:
        return url.split("/channel/")[1].split("/")[0]
    elif "/user/" in url:
        username = url.split("/user/")[1].split("/")[0]
        req = youtube_client.channels().list(part="id", forUsername=username)
        resp = req.execute()
        items = resp.get("items", [])
        if not items:
            raise ValueError("チャンネルが見つかりません。")
        return items[0]["id"]
    elif "/@" in url:
        start = url.find("/@") + 2
        end = url.find("/", start)
        handle = url[start:] if end == -1 else url[start:end]
        req = youtube_client.search().list(part="snippet", q=handle, type="channel", maxResults=1)
        resp = req.execute()
        items = resp.get("items", [])
        if not items:
            raise ValueError("handleからチャンネルが見つかりません。")
        return items[0]["id"]["channelId"]
    elif "/c/" in url:
        raise ValueError("カスタムURL（/c/）の解決には未対応です。")
    else:
        raise ValueError("URL形式が認識できません。")

def extract_playlist_id(url):
    parsed = urllib.parse.urlparse(url)
    query = urllib.parse.parse_qs(parsed.query)
    if 'list' in query:
        return query['list'][0]
    return None

def get_uploads_playlist_id(channel_id, api_key, youtube_client=None):
    if youtube_client is None:
        youtube_client = get_youtube_client(api_key)
    req = youtube_client.channels().list(part="contentDetails", id=channel_id)
    resp = req.execute()
    items = resp.get("items", [])
    if not items:
        raise ValueError("チャンネル情報が見つかりません。")
    return items[0]["contentDetails"]["relatedPlaylists"]["uploads"]

def get_video_list(playlist_id, api_key, youtube_client=None):
    if youtube_client is None:
        youtube_client = get_youtube_client(api_key)
    video_list = []
    nextPageToken = None
    while True:
        req = youtube_client.playlistItems().list(
            part="snippet",
            playlistId=playlist_id,
            maxResults=50,
            pageToken=nextPageToken
        )
        resp = req.execute()
        for item in resp.get("items", []):
            video_id = item["snippet"]["resourceId"]["videoId"]
            title = item["snippet"]["title"]
            video_list.append({"video_id": video_id, "title": title})
        nextPageToken = resp.get("nextPageToken")
        if not nextPageToken:
            break
    return video_list

def clean_vtt(vtt_content):
    lines = vtt_content.splitlines()
    cleaned = []
    last_line = None
    for line in lines:
        if line.startswith("WEBVTT") or line.startswith("Kind:") or line.startswith("Language:"):
            continue
        if "-->" in line:
            continue
        line = TAG_REGEX.sub("", line)
        line = TIME_REGEX.sub("", line)
        line = line.strip()
        if line and line != last_line:
            cleaned.append(line)
            last_line = line
    return "\n".join(cleaned)

def run_yt_dlp_command(command, video_id, progress_callback):
    proc = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    while True:
        line = proc.stdout.readline()
        if not line:
            break
        m = PROGRESS_REGEX.search(line)
        if m and progress_callback:
            try:
                progress = float(m.group(1))
                progress_callback(video_id, progress)
            except Exception:
                pass
    proc.wait()

def download_and_clean_subtitles(video_id, lang="ja", progress_callback=None):
    video_url = f"https://www.youtube.com/watch?v={video_id}"
    output_template = f"{video_id}.%(ext)s"
    command_manual = [
        "yt-dlp",
        "--skip-download",
        "--write-sub",
        "--sub-lang", lang,
        "--convert-subs", "vtt",
        "--newline",
        "-o", output_template,
        video_url
    ]
    run_yt_dlp_command(command_manual, video_id, progress_callback)
    subtitle_file = f"{video_id}.{lang}.vtt"
    if not os.path.exists(subtitle_file):
        command_auto = [
            "yt-dlp",
            "--skip-download",
            "--write-auto-sub",
            "--sub-lang", lang,
            "--convert-subs", "vtt",
            "--newline",
            "-o", output_template,
            video_url
        ]
        run_yt_dlp_command(command_auto, video_id, progress_callback)
        if not os.path.exists(subtitle_file):
            return None
    try:
        with open(subtitle_file, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception:
        return None
    cleaned = clean_vtt(content)
    os.remove(subtitle_file)
    return cleaned

def process_video(video, progress_callback):
    video_id = video["video_id"]
    title = video["title"]
    video_url = f"https://www.youtube.com/watch?v={video_id}"
    md = f"## [{title}]({video_url})\n\n"
    subtitle = download_and_clean_subtitles(video_id, lang="ja", progress_callback=progress_callback)
    if subtitle:
        md += " ".join(subtitle.split()) + "\n\n"
    else:
        md += "字幕が取得できませんでした。\n\n"
    return md

def process_and_stream(url, api_key, output_dest):
    yield json.dumps({"type": "log", "message": "URL受信: " + url}) + "\n"
    youtube_client = get_youtube_client(api_key)
    try:
        playlist_id = extract_playlist_id(url)
        if playlist_id:
            yield json.dumps({"type": "log", "message": "プレイリストURL検出。動画リスト取得中..."}) + "\n"
            video_list = get_video_list(playlist_id, api_key, youtube_client=youtube_client)
        else:
            yield json.dumps({"type": "log", "message": "チャンネルURLとして処理します。"}) + "\n"
            channel_id = extract_channel_id(url, api_key, youtube_client=youtube_client)
            yield json.dumps({"type": "log", "message": "チャンネルID: " + channel_id}) + "\n"
            uploads_playlist_id = get_uploads_playlist_id(channel_id, api_key, youtube_client=youtube_client)
            yield json.dumps({"type": "log", "message": "アップロード動画リスト取得中..."}) + "\n"
            video_list = get_video_list(uploads_playlist_id, api_key, youtube_client=youtube_client)
    except Exception as e:
        yield json.dumps({"type": "log", "message": "エラー: " + str(e)}) + "\n"
        return

    total = len(video_list)
    yield json.dumps({"type": "log", "message": f"{total} 本の動画が見つかりました。"}) + "\n"
    finished_count = 0
    results = [None] * total
    log_queue = Queue()

    def worker(video, idx):
        log_queue.put(json.dumps({"type": "log", "message": f"開始: {video['title']}"} ) + "\n")
        res = process_video(video, progress_callback=lambda vid, prog: None)
        log_queue.put(json.dumps({"type": "log", "message": f"完了: {video['title']}"} ) + "\n")
        return idx, res

    max_workers = (os.cpu_count() or 4) * 2
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(worker, video, idx): idx for idx, video in enumerate(video_list)}
        while futures:
            done, _ = concurrent.futures.wait(futures, timeout=0.1, return_when=concurrent.futures.FIRST_COMPLETED)
            for future in list(done):
                idx, res = future.result()
                results[idx] = res
                finished_count += 1
                overall = int((finished_count / total) * 100)
                yield json.dumps({"type": "overall_progress", "progress": overall}) + "\n"
                del futures[future]
            try:
                while True:
                    msg = log_queue.get_nowait()
                    yield msg
            except Empty:
                pass

    markdown = "\n".join(results)
    with open(output_dest, "w", encoding="utf-8") as f:
        f.write(markdown)
    yield json.dumps({"type": "log", "message": "全動画の処理完了。Markdownファイル生成。"}) + "\n"
    # 出力先パスは confirm メッセージ内でのみ通知
    yield json.dumps({
        "type": "confirm",
        "message": "内容確認",
        "preview": "/preview?file=" + output_dest,
        "output": output_dest
    }) + "\n"
    HISTORY.append({
        "url": url,
        "timestamp": time.time(),
        "preview": "/preview?file=" + output_dest
    })

@app.route("/", methods=["GET"])
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route("/process", methods=["POST"])
def process():
    url = request.form.get("url")
    if not url:
        return Response(json.dumps({"type": "log", "message": "URLが入力されていません。"}), mimetype='application/json')
    api_key = keyring.get_password("subtitle_app", "api_key")
    if not api_key:
        return Response(json.dumps({"type": "log", "message": "API Keyが設定されていません。設定画面から入力してください。"}), mimetype='application/json')
    config = load_config()
    default_dest = os.path.join(os.path.expanduser("~"), "Downloads", "subtitles.md")
    output_dest = config.get("output_dest", default_dest)
    return Response(process_and_stream(url, api_key, output_dest), mimetype='text/plain')

@app.route("/download", methods=["GET"])
def download():
    file = request.args.get("file", os.path.join(os.path.expanduser("~"), "Downloads", "subtitles.md"))
    if os.path.exists(file):
        return send_file(file, as_attachment=True)
    return "ファイルが見つかりません。", 404

@app.route("/preview", methods=["GET"])
def preview():
    file = request.args.get("file", os.path.join(os.path.expanduser("~"), "Downloads", "subtitles.md"))
    if os.path.exists(file):
        with open(file, "r", encoding="utf-8") as f:
            content = f.read()
        preview_template = """
        <!doctype html>
        <html lang="ja">
          <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <title>プレビュー</title>
            <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
            <style>
              :root {
                --primary-color: #6366f1;
                --background-light: #ffffff;
                --text-light: #1e293b;
              }
              body {
                background-color: var(--background-light);
                color: var(--text-light);
                font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
                padding: 1rem;
              }
              .card {
                max-width: 800px;
                margin: auto;
              }
              pre {
                white-space: pre-wrap;
                word-break: break-all;
              }
            </style>
          </head>
          <body>
            <div class="card">
              <div class="card-header">
                ファイルプレビュー
              </div>
              <div class="card-body">
                <pre>{{ content }}</pre>
              </div>
            </div>
          </body>
        </html>
        """
        return render_template_string(preview_template, content=content)
    return "ファイルが見つかりません。", 404

@app.route("/save_config", methods=["POST"])
def save_config_route():
    new_api_key = request.form.get("api_key")
    output_dest = request.form.get("output_dest")
    port = request.form.get("port")
    auto_open_browser = request.form.get("auto_open_browser")
    config = load_config()
    msg = ""
    if new_api_key:
        keyring.set_password("subtitle_app", "api_key", new_api_key)
        msg += "API Keyを保存しました。"
    else:
        msg += "API Keyは既に設定済みです。"
    if output_dest:
        config["output_dest"] = output_dest
        msg += " 出力先も保存しました。"
    if port:
        config["port"] = port
        msg += " ポート番号も保存しました。"
    config["auto_open_browser"] = True if auto_open_browser == "on" else False
    # ※通知音に関する設定は削除しました
    msg += " 設定を保存しました。"
    save_config_to_file(config)
    return jsonify({"message": msg})

@app.route("/get_config", methods=["GET"])
def get_config_route():
    config = load_config()
    api_key = keyring.get_password("subtitle_app", "api_key")
    default_dest = os.path.join(os.path.expanduser("~"), "Downloads", "subtitles.md")
    port = config.get("port", "5000")
    auto_open_browser = config.get("auto_open_browser", False)
    return jsonify({
        "api_key_set": bool(api_key),
        "output_dest": config.get("output_dest", default_dest),
        "port": port,
        "auto_open_browser": auto_open_browser
    })

@app.route("/choose_output", methods=["GET"])
def choose_output():
    folder = choose_output_folder()
    if folder:
        return jsonify({"output_dest": os.path.join(folder, "subtitles.md")})
    else:
        return jsonify({"output_dest": ""})

@app.route("/get_history", methods=["GET"])
def get_history():
    return jsonify({"history": HISTORY})

@app.route("/shutdown", methods=["GET"])
def shutdown():
    shutdown_func = request.environ.get('werkzeug.server.shutdown')
    if shutdown_func is None:
        return "サーバー終了に失敗しました。", 500
    shutdown_func()
    return "サーバーを終了しました。"

if __name__ == "__main__":
    config = load_config()
    port = int(config.get("port", 5000))
    host = "127.0.0.1"

    def is_port_in_use(port):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            return s.connect_ex((host, port)) == 0

    original_port = port
    while is_port_in_use(port):
        port += 1
        if port > original_port + 100:
            print("空きポートが見つかりません。")
            sys.exit(1)
    print(f"サーバー起動ポート: {port}")

    auto_open = config.get("auto_open_browser", False)
    if auto_open:
        def open_browser():
            time.sleep(1)
            webbrowser.open(f"http://{host}:{port}")
        threading.Thread(target=open_browser).start()

    app.run(host=host, port=port, debug=True, use_reloader=False)

