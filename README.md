# Zoom出席カウント

Zoomミーティングの参加者パネルのスクリーンショットから、出席者を自動で抽出・集計するWebアプリです。

## 機能

- 📷 スクリーンショットから参加者名を自動抽出（OpenAI GPT-4o使用）
- 📊 出席者リストの表示・管理
- 📥 CSV形式でのエクスポート
- 🔄 複数回のキャプチャで出席回数をカウント

## 使い方

### Webアプリ版（推奨）

1. アプリにアクセス
2. サイドバーでOpenAI APIキーを入力
3. Zoomの参加者パネルのスクリーンショットを撮影
4. 画像をアップロード
5. 「解析する」ボタンをクリック
6. 結果を確認し、必要に応じてCSVダウンロード

### ローカル実行

```bash
# リポジトリをクローン
git clone https://github.com/ToYamane/zoom_attend.git
cd zoom_attend

# 依存関係をインストール
pip install -r requirements.txt

# アプリを起動
streamlit run app.py
```

## 必要なもの

- OpenAI APIキー（[こちら](https://platform.openai.com/api-keys)から取得）

## デスクトップ版

GUIアプリ版も利用可能です（`zoom_attendance.py`）。

```bash
# .envファイルを作成してAPIキーを設定
cp .env.example .env
# .envファイルを編集してOPENAI_API_KEYを設定

# デスクトップ版の依存関係をインストール
pip install pillow openai python-dotenv

# 実行
python zoom_attendance.py
```

## 料金について

OpenAI GPT-4oの画像解析を使用するため、1回の解析あたり約1〜3円の料金が発生します。

## ライセンス

MIT License
