"""Streamlit UI: 勤怠問い合わせAIボット（最小構成）。"""

from __future__ import annotations

import streamlit as st

from main import load_rules, process_inquiry


def run_app() -> None:
    """Web画面を描画して、入力に対する判定結果を表示する。"""
    st.title("勤怠問い合わせAIボット")
    st.write("勤怠ルール確認や勤怠ミス報告を分類します")

    # rules.txt は毎回読み直さず、最初に1回だけ読み込む。
    rules_data = load_rules()

    user_input = st.text_area(
        "問い合わせ内容を入力してください",
        placeholder="例: 遅刻しそうです。どうすればいいですか？",
        height=120,
    )

    if st.button("判定する"):
        if not user_input.strip():
            st.warning("問い合わせ内容を入力してください。")
            return

        # CLI と同じ共通ロジックを使う。
        result = process_inquiry(user_input, rules_data)

        st.subheader("結果")
        st.write(f"問い合わせ種別: {result['type']}")
        st.write(f"カテゴリ: {result['category']}")
        st.write(result["message"])


if __name__ == "__main__":
    run_app()
