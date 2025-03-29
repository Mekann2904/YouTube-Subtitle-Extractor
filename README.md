# YouTube Subtitle Extractor

## 概要
YouTube Subtitle Extractor は、YouTube の動画、チャンネル、またはプレイリストから字幕を抽出し、Markdown 形式のファイルに保存する Python 製のウェブアプリケーションです。yt-dlp と YouTube Data API を利用して、指定された動画の字幕を取得します。

## 特徴
- **字幕抽出**: YouTube 動画の字幕（主に日本語）を抽出し、Markdown 形式で出力します。
- **チャンネル・プレイリスト対応**: チャンネル URL またはプレイリスト URL を指定して、複数の動画から字幕を抽出できます。
- **ウェブインターフェース**: Bootstrap を用いたシンプルで直感的なユーザーインターフェースにより、誰でも簡単に操作可能です。
- **設定機能**: API キー、出力先、ポート番号、自動ブラウザ起動などの各種設定が可能です。
- **マルチプラットフォーム対応**: macOS（AppleScript 使用）および Windows（Tkinter 使用）で動作します。
- **通知機能**: デスクトップ通知を利用して、処理完了を知らせます（通知音に関する設定は削除済みです）。

## 要件
- Python 3.6 以上
- [Flask](https://palletsprojects.com/p/flask/)
- [google-api-python-client](https://github.com/googleapis/google-api-python-client)
- [keyring](https://pypi.org/project/keyring/)
- [yt-dlp](https://github.com/yt-dlp/yt-dlp)
- 標準ライブラリ: os, sys, re, json, subprocess, urllib, concurrent.futures, threading, socket, webbrowser, time

## インストール
1. Python をインストールしてください。
2. 必要なパッケージを以下のように pip でインストールします:
    ```bash
    pip install Flask google-api-python-client keyring yt-dlp
    ```
3. このリポジトリのコードをクローンまたはダウンロードしてください。

## 設定
1. **API キーの取得**: YouTube Data API の API キーを Google Cloud Console から取得してください。
2. **設定の保存**: アプリケーション起動後、設定画面または設定ファイル（`~/.subtitle_app_config.json`）にて API キー、出力先、ポート番号、自動ブラウザ起動などを設定してください。
3. **通知音の設定**: 本バージョンでは通知音に関する設定は削除されています。

## 使い方
1. アプリケーションを起動します:
    ```bash
    python your_script_name.py
    ```
2. ブラウザで `http://127.0.0.1:<ポート番号>` にアクセスしてください。
3. 入力フォームに YouTube の動画、チャンネル、またはプレイリストの URL を入力し、**実行** ボタンをクリックします。
4. 画面上に処理の進捗状況とログが表示され、処理完了後に Markdown ファイルが生成されます。
5. 結果確認ボタンをクリックして、抽出された字幕を確認してください。

## 注意事項
- このアプリケーションは、YouTube の字幕が存在する動画のみ対応しています。
- 一部の URL 形式（例: カスタム URL `/c/`）には対応していません。
- 本ソフトウェアは現状のまま提供され、動作保証やサポートは行いません。自己責任でご利用ください。

## 貢献
バグの報告、機能改善の提案、Pull Request など、どなたからの貢献も歓迎します。

## ライセンス
このプロジェクトは [MIT License](LICENSE) の下でライセンスされています。

