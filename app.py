"""Streamlit UI: 勤怠問い合わせAIボット（モダンチャットUI）。"""

from __future__ import annotations

import html

import streamlit as st

from main import load_rules, process_inquiry, trim_stored_messages

# ---------------------------------------------------------------------------
# 定数（UI表示用。判定ロジック自体は main.py に任せる）
# ---------------------------------------------------------------------------

SUGGESTED_QUESTIONS: tuple[str, ...] = (
    "遅刻した場合の対応は？",
    "打刻を忘れた場合は？",
    "午前休・午後休の申請方法は？",
    "休日出勤の申請について",
)

SIDEBAR_FAQ: tuple[str, ...] = (
    "遅刻した場合の対応は？",
    "打刻を忘れた場合は？",
    "午前休・午後休の申請方法は？",
    "休日出勤の申請について",
    "電車遅延の場合は？",
)

# ルール確認時の導入文（カテゴリ名 → 表示テキスト）
CATEGORY_INTROS: dict[str, str] = {
    "遅刻": "遅刻の場合の勤怠記載ルールは以下の通りです。",
    "電車遅延": "電車遅延の場合の勤怠記載ルールは以下の通りです。",
    "打刻漏れ": "打刻漏れの場合の対応は以下の通りです。",
    "記載ミス": "記載ミスの場合の対応は以下の通りです。",
    "午前休/午後休": "午前休・午後休の勤怠記載ルールは以下の通りです。",
    "休日出勤": "休日出勤の勤怠記載ルールは以下の通りです。",
    "有給": "有給取得の勤怠記載ルールは以下の通りです。",
}


# ---------------------------------------------------------------------------
# CSS（Streamlit 標準UIを業務向けチャット風に整える）
# ---------------------------------------------------------------------------


def inject_global_css() -> None:
    """ページ全体の配色・余白・吹き出しなどを統一する。"""
    st.markdown(
        """
        <style>
        /* ---- ベースカラー ---- */
        :root {
            --green-main: #22C55E;
            --green-dark: #15803D;
            --green-light: #F0FDF4;
            --bg-page: #F8FAFC;
            --bg-white: #FFFFFF;
            --text-main: #1F2937;
            --text-sub: #6B7280;
            --border: #E5E7EB;
            --radius: 14px;
            --shadow: 0 1px 3px rgba(15, 23, 42, 0.06);
        }

        /* 画面全体：白〜薄グレー（強い緑の全面背景は使わない） */
        .stApp,
        [data-testid="stAppViewContainer"],
        [data-testid="stMain"] {
            background-color: var(--bg-page) !important;
            color: var(--text-main);
        }

        /* サイドバー幅 20〜25% 程度 */
        [data-testid="stSidebar"] {
            width: 22% !important;
            min-width: 260px !important;
            max-width: 320px !important;
            background-color: var(--bg-white) !important;
            border-right: 1px solid var(--border) !important;
        }
        [data-testid="stSidebar"] > div:first-child {
            padding-top: 1.5rem;
        }

        /* メインエリア：Streamlit 上部バー（Deploy 等）の高さぶん余白を確保 */
        section[data-testid="stMain"] .block-container {
            padding-top: 4.5rem !important;
            padding-bottom: 1rem !important;
            max-width: 100% !important;
        }

        /* ヘッダーカード（チャットと重ならないよう通常フローで配置） */
        .chat-header,
        .main-page-header {
            background: var(--bg-white);
            border: 1px solid var(--border);
            border-radius: var(--radius);
            padding: 1rem 1.25rem;
            margin-bottom: 1.5rem;
            box-shadow: var(--shadow);
            position: relative;
            z-index: 0;
        }
        /* ヘッダー行全体の下余白（使い方ボタン列との重なり防止） */
        div[data-testid="stHorizontalBlock"]:has(.main-page-header) {
            margin-bottom: 1.25rem !important;
            align-items: flex-start !important;
        }
        /* Streamlit 標準ヘッダー（上部バー） */
        header[data-testid="stHeader"] {
            position: sticky !important;
            top: 0;
            z-index: 999;
            background: var(--bg-page) !important;
        }
        .chat-header-title {
            font-size: 1.15rem;
            font-weight: 700;
            color: var(--text-main);
            margin: 0;
        }
        .chat-header-sub {
            font-size: 0.875rem;
            color: var(--text-sub);
            margin: 0.35rem 0 0 0;
            line-height: 1.5;
        }
        .online-badge {
            display: inline-flex;
            align-items: center;
            gap: 0.35rem;
            font-size: 0.75rem;
            color: var(--green-dark);
            background: var(--green-light);
            border-radius: 999px;
            padding: 0.15rem 0.55rem;
            margin-left: 0.5rem;
            vertical-align: middle;
        }
        .online-dot {
            width: 7px;
            height: 7px;
            border-radius: 50%;
            background: var(--green-main);
        }

        /* サイドバー内テキスト */
        .sidebar-brand-title {
            font-size: 1.1rem;
            font-weight: 700;
            color: var(--text-main);
            margin: 0.5rem 0 0.25rem 0;
        }
        .sidebar-brand-sub {
            font-size: 0.82rem;
            color: var(--text-sub);
            line-height: 1.5;
            margin-bottom: 1rem;
        }
        .sidebar-section-title {
            font-size: 0.78rem;
            font-weight: 600;
            color: var(--text-sub);
            text-transform: none;
            letter-spacing: 0.02em;
            margin: 1rem 0 0.5rem 0;
        }
        .sidebar-note {
            font-size: 0.72rem;
            color: var(--text-sub);
            line-height: 1.55;
            margin-top: 1.5rem;
            padding-top: 1rem;
            border-top: 1px solid var(--border);
        }

        /* チャットメッセージ共通 */
        div[data-testid="stChatMessage"] {
            background: transparent !important;
            border: none !important;
            padding: 0.35rem 0 !important;
            align-items: flex-start !important;
            gap: 0.65rem !important;
        }
        div[data-testid="stChatMessageContent"] {
            background: transparent !important;
            padding: 0 !important;
            min-width: 0 !important;
        }

        /* ユーザー：吹き出し → アイコン（右端）の順で右寄せ */
        div[data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-user"]) {
            flex-direction: row-reverse !important;
            justify-content: flex-start !important;
            width: fit-content !important;
            max-width: 100% !important;
            margin-left: auto !important;
            margin-right: 0 !important;
        }
        div[data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-user"])
        [data-testid="stChatMessageContent"] {
            flex: 0 1 auto !important;
            width: auto !important;
        }

        /* ボット：アイコン → 吹き出し（左端）の順で左寄せ */
        div[data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-assistant"]) {
            flex-direction: row !important;
            justify-content: flex-start !important;
            width: fit-content !important;
            max-width: 100% !important;
            margin-right: auto !important;
            margin-left: 0 !important;
        }
        div[data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-assistant"])
        [data-testid="stChatMessageContent"] {
            flex: 0 1 auto !important;
            width: auto !important;
        }

        /* 吹き出し */
        .bubble-user {
            background: var(--green-light);
            border: 1px solid #BBF7D0;
            border-radius: var(--radius);
            padding: 0.75rem 1rem;
            max-width: 520px;
            color: var(--text-main);
            font-size: 0.92rem;
            line-height: 1.6;
            white-space: pre-wrap;
            box-shadow: var(--shadow);
        }
        .bubble-assistant {
            max-width: 620px;
        }

        /* ボット回答カード */
        .reply-intro {
            font-size: 0.92rem;
            color: var(--text-main);
            margin: 0 0 0.65rem 0;
            line-height: 1.6;
        }
        .info-card,
        .handoff-card {
            background: var(--bg-white);
            border: 1px solid var(--border);
            border-radius: var(--radius);
            padding: 0.85rem 1rem;
            box-shadow: var(--shadow);
        }
        .info-card.plain p {
            margin: 0;
            font-size: 0.92rem;
            line-height: 1.6;
        }
        .info-row {
            display: grid;
            grid-template-columns: 5.5rem 1fr;
            gap: 0.75rem;
            padding: 0.45rem 0;
            border-bottom: 1px solid #F3F4F6;
            font-size: 0.88rem;
            line-height: 1.55;
        }
        .info-row:last-child {
            border-bottom: none;
        }
        .info-label {
            color: var(--text-sub);
            font-weight: 600;
        }
        .info-value {
            color: var(--text-main);
        }
        .handoff-line {
            margin: 0 0 0.5rem 0;
            font-size: 0.92rem;
            line-height: 1.6;
            color: var(--text-main);
        }
        .handoff-list {
            margin: 0.25rem 0 0 0;
            padding-left: 1.1rem;
            color: var(--text-main);
            font-size: 0.88rem;
            line-height: 1.65;
        }
        .handoff-list li {
            margin-bottom: 0.25rem;
        }

        /* おすすめ質問 */
        .suggested-heading {
            font-size: 0.82rem;
            font-weight: 600;
            color: var(--text-sub);
            margin: 0.75rem 0 0.35rem 0;
        }

        /* チップ風ボタン（おすすめ質問エリア） */
        div[data-testid="stHorizontalBlock"]:has(.chip-marker) button[kind="secondary"] {
            background: var(--green-light) !important;
            color: var(--green-dark) !important;
            border: 1px solid #BBF7D0 !important;
            border-radius: 999px !important;
            font-size: 0.78rem !important;
            padding: 0.35rem 0.75rem !important;
            box-shadow: none !important;
        }
        div[data-testid="stHorizontalBlock"]:has(.chip-marker) button[kind="secondary"]:hover {
            border-color: var(--green-main) !important;
            color: var(--green-dark) !important;
        }

        /* 入力欄まわり */
        [data-testid="stChatInput"] {
            background: var(--bg-white) !important;
            border: 1px solid var(--border) !important;
            border-radius: var(--radius) !important;
            padding: 0.35rem 0.5rem !important;
            box-shadow: var(--shadow) !important;
        }
        [data-testid="stChatInput"] textarea {
            border: 1px solid #BBF7D0 !important;
            border-radius: 10px !important;
            font-size: 0.92rem !important;
        }
        [data-testid="stChatInput"] textarea:focus {
            border-color: var(--green-main) !important;
            box-shadow: 0 0 0 2px rgba(34, 197, 94, 0.15) !important;
        }
        .input-disclaimer {
            font-size: 0.72rem;
            color: var(--text-sub);
            margin-top: 0.45rem;
            line-height: 1.5;
        }

        /* 透過背景の除去（以前の調整を維持） */
        .st-emotion-cache-1c7y2kd {
            background-color: unset !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# 回答文の整形（rules.txt から得た本文をそのまま活かし、見た目だけ整理）
# ---------------------------------------------------------------------------


def build_bot_reply(result: dict[str, str]) -> str:
    """
    process_inquiry() の結果から、画面表示用の本文だけ取り出す。
    main.py のロジックは変更せず、プレフィックス除去のみ行う。
    """
    message = result["message"]
    if result["type"] == "ルール確認" and message.startswith("回答: "):
        return message[len("回答: ") :]
    return message


def _parse_label_value_lines(text: str) -> list[tuple[str, str]]:
    """「ラベル：値」形式の行を抽出する（rules.txt の記載形式）。"""
    rows: list[tuple[str, str]] = []
    for line in text.strip().splitlines():
        s = line.strip()
        if not s:
            continue
        if "：" in s:
            label, value = s.split("：", 1)
            rows.append((label.strip(), value.strip()))
        elif ":" in s and not s.startswith("http"):
            label, value = s.split(":", 1)
            rows.append((label.strip(), value.strip()))
    return rows


def format_assistant_html(
    content: str,
    inquiry_type: str | None = None,
    category: str | None = None,
) -> str:
    """
    ボット回答を HTML カード形式に整形する。
    ※ 内容自体は main.py / rules.txt から得た文字列のみを使う（勝手な追記はしない）。
    """
    safe_content = html.escape(content)

    # 追加確認：自然な1文の質問として表示
    if inquiry_type == "追加確認":
        return f'<div class="info-card plain"><p>{safe_content}</p></div>'

    # ルール確認：ラベル/値の行があれば情報カード化
    if inquiry_type == "ルール確認":
        rows = _parse_label_value_lines(content)
        intro = html.escape(CATEGORY_INTROS.get(category or "", "勤怠記載ルールは以下の通りです。"))

        if rows:
            rows_html = "".join(
                f'<div class="info-row">'
                f'<span class="info-label">{html.escape(l)}</span>'
                f'<span class="info-value">{html.escape(v)}</span>'
                f"</div>"
                for l, v in rows
            )
            return (
                f'<p class="reply-intro">{intro}</p>'
                f'<div class="info-card">{rows_html}</div>'
            )

        return f'<div class="info-card plain"><p>{safe_content}</p></div>'

    # 勤怠ミス報告 / その他：案内文 + 箇条書きテンプレ
    lines = content.splitlines()
    intro_lines: list[str] = []
    bullets: list[str] = []

    for line in lines:
        s = line.strip()
        if not s:
            continue
        if s.startswith("・"):
            bullets.append(s[1:].strip())
        else:
            intro_lines.append(s)

    parts = ['<div class="handoff-card">']
    for line in intro_lines:
        parts.append(f'<p class="handoff-line">{html.escape(line)}</p>')
    if bullets:
        items = "".join(f"<li>{html.escape(b)}</li>" for b in bullets)
        parts.append(f'<ul class="handoff-list">{items}</ul>')
    parts.append("</div>")
    return "".join(parts)


# ---------------------------------------------------------------------------
# UI 描画
# ---------------------------------------------------------------------------


def init_session_state() -> None:
    """セッション内の会話履歴・ルールデータを初期化する。"""
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "rules_data" not in st.session_state:
        st.session_state.rules_data = load_rules()
    if "pending_message" not in st.session_state:
        st.session_state.pending_message = None
    if "show_admin_hint" not in st.session_state:
        st.session_state.show_admin_hint = False


def queue_message(text: str) -> None:
    """ボタンクリック等で送る質問を、次の rerun で処理するために保持する。"""
    st.session_state.pending_message = text.strip()


def process_and_append_message(text: str) -> None:
    """
    1件の問い合わせを main.py に渡し、ユーザー/ボットメッセージを履歴に追加する。
    種別・カテゴリは画面には出さず、ボット回答の整形にだけ内部利用する。

    処理時は現在の発言より前の履歴を渡し、会話の文脈を踏まえて判定する。
    """
    cleaned = text.strip()
    if not cleaned:
        return

    # 現在の発言を追加する前の履歴（role / content 形式）を処理に渡す
    history = list(st.session_state.messages)

    st.session_state.messages.append({"role": "user", "content": cleaned})

    result = process_inquiry(
        cleaned,
        st.session_state.rules_data,
        conversation_history=history,
    )
    bot_reply = build_bot_reply(result)

    st.session_state.messages.append(
        {
            "role": "assistant",
            "content": bot_reply,
            "inquiry_type": result["type"],
            "category": result["category"],
            "is_clarification": bool(result.get("is_clarification")),
        }
    )

    st.session_state.messages = trim_stored_messages(st.session_state.messages)


def render_sidebar() -> None:
    """左サイドバー（ブランド・新規チャット・FAQ・注意書き）。"""
    with st.sidebar:
        st.markdown("### 💬")
        st.markdown('<p class="sidebar-brand-title">勤怠AIボット</p>', unsafe_allow_html=True)
        st.markdown(
            '<p class="sidebar-brand-sub">勤怠の質問に回答します</p>',
            unsafe_allow_html=True,
        )

        # 新しいチャット：履歴をクリア
        if st.button("＋  新しいチャット", type="primary", use_container_width=True):
            st.session_state.messages = []
            st.session_state.pending_message = None
            st.session_state.show_admin_hint = False
            st.rerun()

        st.markdown('<p class="sidebar-section-title">よくある質問</p>', unsafe_allow_html=True)
        for i, question in enumerate(SIDEBAR_FAQ):
            if st.button(question, key=f"sidebar_faq_{i}", use_container_width=True):
                queue_message(question)
                st.rerun()

        st.markdown(
            """
            <div class="sidebar-note">
                <strong>ご利用にあたって</strong><br>
                回答は社内ルールに基づく参考情報です。
                不明点は管理者へ確認してください。
            </div>
            """,
            unsafe_allow_html=True,
        )

        if st.button("管理者に確認する", use_container_width=True, key="admin_link"):
            st.session_state.show_admin_hint = True


def render_main_header() -> None:
    """メインチャットエリア上部の固定ヘッダー。"""
    left, right = st.columns([6, 1])
    with left:
        st.markdown(
            """
            <div class="chat-header main-page-header">
                <p class="chat-header-title">
                    🤖 勤怠問い合わせAIボット
                    <span class="online-badge">
                        <span class="online-dot"></span>オンライン
                    </span>
                </p>
                <p class="chat-header-sub">
                    勤怠に関するご質問に、チャット形式でお答えします。
                </p>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with right:
        with st.popover("使い方"):
            st.markdown(
                """
                **基本的な使い方**

                1. 下の入力欄に質問を入力して送信
                2. 「おすすめの質問」や左の「よくある質問」から選んでもOK
                3. ルール確認は `rules.txt` に基づく回答を表示
                4. 勤怠ミスの報告は、管理者確認用の整理項目を表示

                **ご注意**

                回答は参考情報です。最終判断は管理者へご確認ください。
                """
            )


def render_chat_bubble(msg: dict[str, str]) -> None:
    """1件分のチャット吹き出しを描画する（user=右 / assistant=左）。"""
    role = msg["role"]
    content = msg["content"]

    with st.chat_message(role):
        if role == "user":
            st.markdown(
                f"<div class='bubble-user'>{html.escape(content)}</div>",
                unsafe_allow_html=True,
            )
        else:
            body_html = format_assistant_html(
                content,
                msg.get("inquiry_type"),
                msg.get("category"),
            )
            st.markdown(f"<div class='bubble-assistant'>{body_html}</div>", unsafe_allow_html=True)


def render_chat_history() -> None:
    """セッション内の会話履歴をすべて描画する。"""
    for msg in st.session_state.messages:
        render_chat_bubble(msg)


def render_suggested_questions() -> None:
    """入力欄の上に、横並びのおすすめ質問チップを表示する。"""
    st.markdown('<p class="suggested-heading">おすすめの質問</p>', unsafe_allow_html=True)
    st.markdown('<span class="chip-marker"></span>', unsafe_allow_html=True)

    cols = st.columns(len(SUGGESTED_QUESTIONS))
    for i, question in enumerate(SUGGESTED_QUESTIONS):
        with cols[i]:
            if st.button(question, key=f"chip_{i}", type="secondary", use_container_width=True):
                queue_message(question)
                st.rerun()


def render_admin_hint() -> None:
    """サイドバーの「管理者に確認する」押下時の案内。"""
    if st.session_state.show_admin_hint:
        st.info("最終的な判断が必要な場合は、所属の管理者・人事担当へ直接ご連絡ください。")


def run_app() -> None:
    """アプリ全体のエントリーポイント。"""
    st.set_page_config(
        page_title="勤怠問い合わせAIボット",
        page_icon="💬",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    inject_global_css()
    init_session_state()
    render_sidebar()

    render_main_header()
    render_admin_hint()

    # ボタンからキューされた質問を先に処理してから履歴を描画する
    if st.session_state.pending_message:
        pending = st.session_state.pending_message
        st.session_state.pending_message = None
        process_and_append_message(pending)

    render_chat_history()

    if not st.session_state.messages:
        render_suggested_questions()

    user_input = st.chat_input("質問を入力してください…")
    if user_input:
        process_and_append_message(user_input)
        st.rerun()

    st.markdown(
        '<p class="input-disclaimer">'
        "本AIの回答は社内ルールに基づく参考情報です。"
        "最終的な判断は管理者までご確認ください。"
        "</p>",
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    run_app()
