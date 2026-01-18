"""
Zoom出席自動カウントアプリ
OpenAI GPT-4oを使用してZoomの参加者パネルから出席者を抽出
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from PIL import ImageGrab, Image
import csv
import base64
import io
import os
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI


# .envファイルを読み込む
ENV_FILE = Path(__file__).parent / ".env"
load_dotenv(ENV_FILE)


class ScreenSelector:
    """画面範囲を選択するためのオーバーレイウィンドウ"""

    def __init__(self, callback):
        self.callback = callback
        self.start_x = None
        self.start_y = None
        self.rect = None

        # フルスクリーンのオーバーレイを作成
        self.root = tk.Toplevel()
        self.root.attributes('-fullscreen', True)
        self.root.attributes('-alpha', 0.3)
        self.root.attributes('-topmost', True)
        self.root.configure(bg='gray')

        # キャンバスを作成
        self.canvas = tk.Canvas(self.root, cursor='cross', bg='gray', highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)

        # イベントバインド
        self.canvas.bind('<Button-1>', self.on_press)
        self.canvas.bind('<B1-Motion>', self.on_drag)
        self.canvas.bind('<ButtonRelease-1>', self.on_release)
        self.root.bind('<Escape>', lambda e: self.cancel())

        # 説明テキスト
        self.canvas.create_text(
            self.root.winfo_screenwidth() // 2,
            50,
            text="Zoomの参加者パネルをドラッグで選択してください（ESCでキャンセル）",
            font=('Meiryo UI', 16),
            fill='white'
        )

    def on_press(self, event):
        self.start_x = event.x
        self.start_y = event.y
        if self.rect:
            self.canvas.delete(self.rect)
        self.rect = self.canvas.create_rectangle(
            self.start_x, self.start_y, self.start_x, self.start_y,
            outline='red', width=2
        )

    def on_drag(self, event):
        if self.rect:
            self.canvas.coords(self.rect, self.start_x, self.start_y, event.x, event.y)

    def on_release(self, event):
        if self.start_x is None:
            return

        # 座標を正規化（左上から右下になるように）
        x1 = min(self.start_x, event.x)
        y1 = min(self.start_y, event.y)
        x2 = max(self.start_x, event.x)
        y2 = max(self.start_y, event.y)

        # 最小サイズチェック
        if x2 - x1 < 10 or y2 - y1 < 10:
            self.cancel()
            return

        self.root.destroy()
        self.callback((x1, y1, x2, y2))

    def cancel(self):
        self.root.destroy()
        self.callback(None)


class ZoomAttendanceApp:
    """メインアプリケーション"""

    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Zoom出席カウント")
        self.root.geometry("600x500")
        self.root.resizable(True, True)

        # OpenAIクライアント
        self.client = None
        self._init_openai_client()

        # 出席者データ: {名前: [記録時刻のリスト]}
        self.attendance_data = {}

        # 選択した範囲を保存
        self.capture_region = None

        self.setup_ui()

    def _init_openai_client(self):
        """OpenAIクライアントを初期化"""
        api_key = os.environ.get('OPENAI_API_KEY')
        if api_key:
            self.client = OpenAI(api_key=api_key)

    def setup_ui(self):
        """UIを構築"""
        # メインフレーム
        main_frame = ttk.Frame(self.root, padding=10)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # === APIキー状態表示 ===
        api_frame = ttk.Frame(main_frame)
        api_frame.pack(fill=tk.X, pady=(0, 10))

        if self.client:
            api_key = os.environ.get('OPENAI_API_KEY', '')
            masked_key = f"sk-...{api_key[-4:]}" if len(api_key) > 4 else "設定済み"
            status_text = f"API Key: {masked_key}"
            status_color = 'green'
        else:
            status_text = "API Key: 未設定（.envファイルを確認してください）"
            status_color = 'red'

        api_status_label = ttk.Label(api_frame, text=status_text, foreground=status_color)
        api_status_label.pack(side=tk.LEFT)

        # === 操作ボタン ===
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill=tk.X, pady=(0, 10))

        self.capture_btn = ttk.Button(
            btn_frame,
            text="📷 範囲を選択してキャプチャ",
            command=self.select_and_capture
        )
        self.capture_btn.pack(side=tk.LEFT, padx=(0, 5))

        self.recapture_btn = ttk.Button(
            btn_frame,
            text="🔄 同じ範囲で再キャプチャ",
            command=self.recapture,
            state=tk.DISABLED
        )
        self.recapture_btn.pack(side=tk.LEFT, padx=(0, 5))

        self.export_btn = ttk.Button(
            btn_frame,
            text="💾 CSVエクスポート",
            command=self.export_csv
        )
        self.export_btn.pack(side=tk.LEFT, padx=(0, 5))

        self.clear_btn = ttk.Button(
            btn_frame,
            text="🗑️ クリア",
            command=self.clear_data
        )
        self.clear_btn.pack(side=tk.LEFT)

        # === ステータス ===
        initial_status = "範囲を選択してキャプチャしてください" if self.client else ".envファイルにOPENAI_API_KEYを設定してください"
        self.status_var = tk.StringVar(value=initial_status)
        status_label = ttk.Label(main_frame, textvariable=self.status_var, foreground='gray')
        status_label.pack(fill=tk.X, pady=(0, 10))

        # === 出席者リスト ===
        list_frame = ttk.LabelFrame(main_frame, text="出席者リスト", padding=5)
        list_frame.pack(fill=tk.BOTH, expand=True)

        # Treeview
        columns = ('name', 'first_time', 'count')
        self.tree = ttk.Treeview(list_frame, columns=columns, show='headings', height=15)
        self.tree.heading('name', text='名前')
        self.tree.heading('first_time', text='初回記録時刻')
        self.tree.heading('count', text='記録回数')
        self.tree.column('name', width=250)
        self.tree.column('first_time', width=150)
        self.tree.column('count', width=80)

        # スクロールバー
        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)

        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # === 統計 ===
        stats_frame = ttk.Frame(main_frame)
        stats_frame.pack(fill=tk.X, pady=(10, 0))

        self.stats_var = tk.StringVar(value="出席者: 0人")
        stats_label = ttk.Label(stats_frame, textvariable=self.stats_var, font=('Meiryo UI', 12, 'bold'))
        stats_label.pack(side=tk.LEFT)

    def select_and_capture(self):
        """範囲選択してキャプチャ"""
        if not self.client:
            messagebox.showerror(
                "エラー",
                ".envファイルにOPENAI_API_KEYが設定されていません。\n\n"
                f"設定ファイルの場所:\n{ENV_FILE}"
            )
            return

        self.root.withdraw()  # メインウィンドウを隠す
        self.root.after(200, self._start_selection)  # 少し待ってから選択開始

    def _start_selection(self):
        """範囲選択を開始"""
        ScreenSelector(self._on_region_selected)

    def _on_region_selected(self, region):
        """範囲選択完了時のコールバック"""
        self.root.deiconify()  # メインウィンドウを表示

        if region is None:
            self.status_var.set("キャンセルされました")
            return

        self.capture_region = region
        self.recapture_btn.configure(state=tk.NORMAL)
        self._do_capture(region)

    def recapture(self):
        """同じ範囲で再キャプチャ"""
        if not self.client:
            messagebox.showerror("エラー", ".envファイルにOPENAI_API_KEYを設定してください")
            return

        if self.capture_region:
            self._do_capture(self.capture_region)

    def _do_capture(self, region):
        """実際のキャプチャとOCR処理"""
        try:
            # 画面キャプチャ
            self.status_var.set("キャプチャ中...")
            self.root.update()

            # 少し待ってからキャプチャ
            self.root.after(100)
            screenshot = ImageGrab.grab(bbox=region)

            # 画像をbase64エンコード
            buffer = io.BytesIO()
            screenshot.save(buffer, format='PNG')
            image_base64 = base64.b64encode(buffer.getvalue()).decode('utf-8')

            # OpenAI APIで解析
            self.status_var.set("AI解析中...")
            self.root.update()

            names = self._extract_names_with_openai(image_base64)

            if not names:
                self.status_var.set("参加者が検出されませんでした。範囲を調整してください。")
                return

            # 出席データに追加
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            new_count = 0
            for name in names:
                if name not in self.attendance_data:
                    self.attendance_data[name] = []
                    new_count += 1
                self.attendance_data[name].append(now)

            # リスト更新
            self._update_list()

            self.status_var.set(f"検出: {len(names)}人（新規: {new_count}人）- {now}")

        except Exception as e:
            messagebox.showerror("エラー", f"処理中にエラーが発生しました:\n{str(e)}")
            self.status_var.set("エラーが発生しました")

    def _extract_names_with_openai(self, image_base64):
        """OpenAI GPT-4oで参加者名を抽出"""
        response = self.client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": """この画像はZoomミーティングの参加者パネルのスクリーンショットです。
参加者の名前のみを抽出してください。

ルール:
- 1行に1人の名前を出力
- 名前の後ろにある「(ホスト)」「(自分)」「(me)」「(host)」などの表記は除去
- 「ミュート」「ビデオ」などのUIボタンは無視
- アイコンや絵文字は無視
- 名前が読み取れない場合は出力しない

出力形式（名前のみ、余計な説明は不要）:
山田太郎
John Smith
..."""
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{image_base64}"
                            }
                        }
                    ]
                }
            ],
            max_tokens=1000
        )

        # レスポンスから名前を抽出
        text = response.choices[0].message.content.strip()
        names = [line.strip() for line in text.split('\n') if line.strip()]

        # 重複を除去しつつ順序を保持
        seen = set()
        unique_names = []
        for name in names:
            if name and name not in seen and len(name) >= 2:
                seen.add(name)
                unique_names.append(name)

        return unique_names

    def _update_list(self):
        """リストビューを更新"""
        # 既存のアイテムをクリア
        for item in self.tree.get_children():
            self.tree.delete(item)

        # データを追加
        for name, times in sorted(self.attendance_data.items()):
            first_time = times[0] if times else ""
            count = len(times)
            self.tree.insert('', tk.END, values=(name, first_time, count))

        # 統計更新
        self.stats_var.set(f"出席者: {len(self.attendance_data)}人")

    def export_csv(self):
        """CSVファイルにエクスポート"""
        if not self.attendance_data:
            messagebox.showwarning("警告", "エクスポートするデータがありません")
            return

        # ファイル保存ダイアログ
        now = datetime.now().strftime("%Y%m%d_%H%M%S")
        default_name = f"zoom_attendance_{now}.csv"

        filepath = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv")],
            initialfile=default_name
        )

        if not filepath:
            return

        try:
            with open(filepath, 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                writer.writerow(['名前', '初回記録時刻', '記録回数', '全記録時刻'])

                for name, times in sorted(self.attendance_data.items()):
                    first_time = times[0] if times else ""
                    count = len(times)
                    all_times = "; ".join(times)
                    writer.writerow([name, first_time, count, all_times])

            messagebox.showinfo("完了", f"CSVファイルを保存しました:\n{filepath}")
            self.status_var.set(f"エクスポート完了: {filepath}")

        except Exception as e:
            messagebox.showerror("エラー", f"保存中にエラーが発生しました:\n{str(e)}")

    def clear_data(self):
        """データをクリア"""
        if not self.attendance_data:
            return

        if messagebox.askyesno("確認", "すべての出席データをクリアしますか？"):
            self.attendance_data.clear()
            self._update_list()
            self.status_var.set("データをクリアしました")

    def run(self):
        """アプリケーションを実行"""
        self.root.mainloop()


def main():
    app = ZoomAttendanceApp()
    app.run()


if __name__ == '__main__':
    main()
