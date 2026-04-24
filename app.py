"""Streamlit UI: 勤怠問い合わせAIボット（最小構成）。"""

from __future__ import annotations

import streamlit as st

from main import load_rules, process_inquiry


def build_bot_reply(result: dict[str, str]) -> str:
    """
    画面に出す最終返信文だけを組み立てる。

    - ルール確認: `回答: ...` の本文だけを表示
    - それ以外: main.py が返す案内 + テンプレをそのまま表示
    """
    message = result["message"]
    if result["type"] == "ルール確認" and message.startswith("回答: "):
        return message[len("回答: ") :]
    return message


def render_chat_bubble(role: str, content: str) -> None:
    """
    1件分のメッセージを描画する。
    - user: 右寄せ
    - assistant: 左寄せ
    """
    with st.chat_message(role):
        # Streamlit の列を使って、確実に左右どちらに寄せるかを制御する。
        if role == "user":
            left, right = st.columns([1, 2])
            with right:
                st.markdown(f"<div class='chat-bubble'>{content}</div>", unsafe_allow_html=True)
        else:
            left, right = st.columns([2, 1])
            with left:
                st.markdown(f"<div class='chat-bubble'>{content}</div>", unsafe_allow_html=True)


def run_app() -> None:
    """チャット形式のWeb画面を描画し、会話履歴をセッション内で保持する。"""
    st.title("勤怠問い合わせAIボット")
    st.write("勤怠の質問にチャット形式で回答します。")

    # 見た目のみ調整:
    # - 画面背景: 緑
    # - 吹き出し: 白
    # ※ 判定ロジックや表示内容そのものは変更しない。
    st.markdown(
        """
        <style>
        .stApp,
        [data-testid="stAppViewContainer"] {
            background-color: #8adf8a;
        }

        /* 指定クラスの透過背景を無効化 */
        .st-emotion-cache-1c7y2kd {
            background-color: unset !important;
        }

        /* user 側のアイコンだけ非表示（assistant は表示のまま） */
        [data-testid="chatAvatarIcon-user"] {
            display: none !important;
        }
        .st-emotion-cache-1ghhuty {
            display: none !important;
        }

        .chat-bubble {
            background-color: #ffffff;
            border-radius: 12px;
            padding: 0.6rem 0.9rem;
            max-width: 75%;
            white-space: pre-wrap;
            box-shadow: 0 1px 4px rgba(0, 0, 0, 0.12);
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    # セッション内だけ会話履歴を保持する。ページをリフレッシュすると初期化される。
    if "messages" not in st.session_state:
        st.session_state.messages = []

    # rules.txt は現在のセッションで使うデータとして読み込む。
    if "rules_data" not in st.session_state:
        st.session_state.rules_data = load_rules()

    # これまでの会話を、ユーザー/ボットの吹き出しで再表示する。
    for msg in st.session_state.messages:
        render_chat_bubble(msg["role"], msg["content"])

    # 下部の入力欄。Enter で送信される。
    user_input = st.chat_input("問い合わせ内容を入力してください")
    if user_input is None:
        return

    text = user_input.strip()
    if not text:
        return

    # 1) ユーザー吹き出しを表示して履歴に保存
    st.session_state.messages.append({"role": "user", "content": text})
    render_chat_bubble("user", text)

    # 2) 既存ロジックで内部判定し、最終返信だけをボット吹き出しで表示
    result = process_inquiry(text, st.session_state.rules_data)
    bot_reply = build_bot_reply(result)

    st.session_state.messages.append({"role": "assistant", "content": bot_reply})
    render_chat_bubble("assistant", bot_reply)


if __name__ == "__main__":
    run_app()
