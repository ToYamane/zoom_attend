"""
Zoom出席カウント Webアプリ
Zoomの参加者パネルのスクリーンショットから出席者を抽出
"""

import streamlit as st
import pandas as pd
import base64
import io
from datetime import datetime
from openai import OpenAI


def extract_names_with_openai(client, image_bytes):
    """OpenAI GPT-4oで参加者名を抽出"""
    image_base64 = base64.b64encode(image_bytes).decode('utf-8')

    response = client.chat.completions.create(
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


def main():
    st.set_page_config(
        page_title="Zoom出席カウント",
        page_icon="📋",
        layout="centered"
    )

    st.title("📋 Zoom出席カウント")
    st.markdown("Zoomの参加者パネルのスクリーンショットをアップロードして、出席者を自動抽出します。")

    # セッション状態の初期化
    if 'attendance_data' not in st.session_state:
        st.session_state.attendance_data = {}

    # サイドバー: APIキー設定
    with st.sidebar:
        st.header("⚙️ 設定")
        api_key = st.text_input(
            "OpenAI API Key",
            type="password",
            help="OpenAI APIキーを入力してください"
        )

        if api_key:
            st.success("APIキー設定済み")
        else:
            st.warning("APIキーを入力してください")

        st.markdown("---")
        st.markdown("### 使い方")
        st.markdown("""
        1. OpenAI APIキーを入力
        2. Zoomの参加者パネルのスクリーンショットを撮影
        3. 画像をアップロード
        4. 解析ボタンをクリック
        5. CSVでダウンロード
        """)

    # メインコンテンツ
    if not api_key:
        st.info("👈 サイドバーでOpenAI APIキーを設定してください")
        return

    # ファイルアップロード
    uploaded_file = st.file_uploader(
        "参加者パネルのスクリーンショットをアップロード",
        type=['png', 'jpg', 'jpeg'],
        help="Zoomの参加者パネルを含むスクリーンショットをアップロードしてください"
    )

    if uploaded_file:
        # 画像プレビュー
        col1, col2 = st.columns([1, 1])

        with col1:
            st.image(uploaded_file, caption="アップロードした画像", use_container_width=True)

        with col2:
            if st.button("🔍 解析する", type="primary", use_container_width=True):
                with st.spinner("AIが参加者を解析中..."):
                    try:
                        client = OpenAI(api_key=api_key)
                        image_bytes = uploaded_file.getvalue()
                        names = extract_names_with_openai(client, image_bytes)

                        if names:
                            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                            new_count = 0

                            for name in names:
                                if name not in st.session_state.attendance_data:
                                    st.session_state.attendance_data[name] = []
                                    new_count += 1
                                st.session_state.attendance_data[name].append(now)

                            st.success(f"✅ {len(names)}人検出（新規: {new_count}人）")
                        else:
                            st.warning("参加者が検出されませんでした。画像を確認してください。")

                    except Exception as e:
                        st.error(f"エラーが発生しました: {str(e)}")

    # 出席者リスト表示
    st.markdown("---")
    st.subheader(f"📊 出席者リスト（{len(st.session_state.attendance_data)}人）")

    if st.session_state.attendance_data:
        # データフレーム作成
        data = []
        for name, times in sorted(st.session_state.attendance_data.items()):
            data.append({
                '名前': name,
                '初回記録時刻': times[0] if times else "",
                '記録回数': len(times)
            })

        df = pd.DataFrame(data)
        st.dataframe(df, use_container_width=True, hide_index=True)

        # ボタン行
        col1, col2 = st.columns(2)

        with col1:
            # CSVダウンロード
            csv_data = []
            for name, times in sorted(st.session_state.attendance_data.items()):
                csv_data.append({
                    '名前': name,
                    '初回記録時刻': times[0] if times else "",
                    '記録回数': len(times),
                    '全記録時刻': "; ".join(times)
                })

            csv_df = pd.DataFrame(csv_data)
            csv_buffer = io.StringIO()
            csv_df.to_csv(csv_buffer, index=False, encoding='utf-8-sig')

            now = datetime.now().strftime("%Y%m%d_%H%M%S")
            st.download_button(
                label="📥 CSVダウンロード",
                data=csv_buffer.getvalue().encode('utf-8-sig'),
                file_name=f"zoom_attendance_{now}.csv",
                mime="text/csv",
                use_container_width=True
            )

        with col2:
            if st.button("🗑️ データをクリア", use_container_width=True):
                st.session_state.attendance_data = {}
                st.rerun()
    else:
        st.info("まだ出席者データがありません。スクリーンショットをアップロードして解析してください。")


if __name__ == '__main__':
    main()
