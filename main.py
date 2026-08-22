"""勤怠問い合わせボット（最小構成）: 入力を3カテゴリに分類する。"""

from __future__ import annotations

from pathlib import Path

from llm import analyze_intent, dev_log_llm, generate_llm_response, intent_analysis_to_dict

# 分類ラベル
RULE_CHECK = "ルール確認"
MISTAKE_REPORT = "勤怠ミス報告"
OTHER = "その他"

# カテゴリ分類ラベル
CATEGORY_DESCRIPTION_MISTAKE = "記載ミス"
CATEGORY_CLOCK_MISS = "打刻漏れ"
CATEGORY_LATE = "遅刻"
CATEGORY_TRAIN_DELAY = "電車遅延"
CATEGORY_HALF_DAY_OFF = "午前休/午後休"
CATEGORY_HOLIDAY_WORK = "休日出勤"

# 勤怠ミス報告（「報告」単体はルール確認と被りやすいので、ミス系を優先）
MISTAKE_KEYWORDS = (
    "ミス",
    "間違",
    "打刻",
    "修正",
    "忘れ",
    "誤",
    "取り消",
    "やり直",
    "訂正",
)

# ルール・制度の確認
RULE_KEYWORDS = (
    "ルール",
    "規定",
    "制度",
    "休暇",
    "有給",
    "遅刻",
    "電車遅延",
    "遅延",
    "早退",
    "勤務時間",
    "残業",
    "申請",
    "方法",
    "できますか",
    "いいですか",
    "大丈夫",
    "教えて",
)

# rules.txt はこのスクリプトと同じフォルダに置く（[カテゴリ名] 形式のルール本文）
RULES_PATH = Path(__file__).resolve().parent / "rules.txt"

# 処理・API に渡す会話履歴の上限（メッセージ件数）
MAX_PROCESSING_HISTORY = 10
# セッションに保持する会話履歴の上限（UI 表示もこの範囲）
MAX_STORED_MESSAGES = 50

# カテゴリ判定用のキーワード。
# 似た内容が重なる場合があるため、判定順（下の関数内）で優先度を調整します。
CATEGORY_KEYWORDS = (
    (
        CATEGORY_TRAIN_DELAY,
        ("電車遅延", "電車", "遅延", "人身事故", "運転見合わせ"),
    ),
    (
        CATEGORY_CLOCK_MISS,
        ("打刻漏れ", "打刻忘れ", "打刻を忘れ", "打刻", "勤怠漏れ", "押し忘れ"),
    ),
    (
        CATEGORY_HALF_DAY_OFF,
        ("午前休", "午後休", "半休", "午前だけ", "午後だけ"),
    ),
    (
        CATEGORY_HOLIDAY_WORK,
        ("休日出勤", "休日勤務", "土日出勤", "祝日出勤"),
    ),
    (
        CATEGORY_LATE,
        ("遅刻", "遅れます", "遅れ", "間に合わない"),
    ),
    (
        CATEGORY_DESCRIPTION_MISTAKE,
        ("記載ミス", "記載", "入力ミス", "間違", "誤記", "訂正", "修正"),
    ),
)

# 人に回す（担当者へ渡す）ときに、そのカテゴリで揃えてほしい情報のテンプレ。
# キーは classify_category() が返すカテゴリ名と一致させます。
HANDOFF_TEMPLATES: dict[str, str] = {
    CATEGORY_DESCRIPTION_MISTAKE: (
        "【担当者へ回すときのメモ】\n"
        "・対象日時\n"
        "・記載ミスの詳細\n"
    ),
    CATEGORY_CLOCK_MISS: (
        "【担当者へ回すときのメモ】\n"
        "・対象日時\n"
        "・漏れた打刻（出勤/退勤/休憩など）\n"
        "・本来の時刻（分かる範囲で）\n"
    ),
    CATEGORY_LATE: (
        "【担当者へ回すときのメモ】\n"
        "・対象日時\n"
        "・遅刻の理由・到着予定（分かる範囲で）\n"
    ),
    CATEGORY_TRAIN_DELAY: (
        "【担当者へ回すときのメモ】\n"
        "・対象日時\n"
        "・路線名・遅延証明の有無\n"
    ),
    CATEGORY_HALF_DAY_OFF: (
        "【担当者へ回すときのメモ】\n"
        "・対象日\n"
        "・午前休 / 午後休 のどちらか\n"
        "・取得理由（任意）\n"
    ),
    CATEGORY_HOLIDAY_WORK: (
        "【担当者へ回すときのメモ】\n"
        "・対象日時\n"
        "・休日出勤の内容（任意）\n"
    ),
    # どのキーワードにも当てはまらなかったときのカテゴリ「その他」用
    OTHER: (
        "【担当者へ回すときのメモ】\n"
        "・問い合わせ内容\n"
    ),
}


def get_recent_history(
    messages: list[dict[str, str]],
    max_messages: int = MAX_PROCESSING_HISTORY,
) -> list[dict[str, str]]:
    """処理・API 用に、直近の会話履歴だけを返す。"""
    if max_messages <= 0 or not messages:
        return []
    return messages[-max_messages:]


def build_inquiry_context(
    history: list[dict[str, str]],
    current_input: str,
    max_messages: int = MAX_PROCESSING_HISTORY,
    *,
    user_only: bool = False,
) -> str:
    """
    直近の会話と現在の入力を1つの文字列にまとめる。
    種別・カテゴリ判定および LLM への質問文に使う（判定関数自体は変更しない）。
    """
    recent = get_recent_history(history, max_messages)
    lines: list[str] = []
    for msg in recent:
        role = msg.get("role", "")
        if user_only and role != "user":
            continue
        content = msg.get("content", "").strip()
        if not content:
            continue
        label = "ユーザー" if role == "user" else "アシスタント"
        lines.append(f"{label}: {content}")
    lines.append(f"ユーザー: {current_input.strip()}")
    return "\n".join(lines)


def resolve_inquiry_text(
    history: list[dict[str, str]] | None,
    current_input: str,
) -> str:
    """
    判定・回答に使う問い合わせ文を決める。

    現在の発言だけで種別・カテゴリが判別できる場合は履歴を混ぜない。
    短い返答などで判別できない場合だけ、直近のユーザー発言を文脈として足す。
    """
    current = current_input.strip()
    if not history:
        return current

    if classify(current) != OTHER or classify_category(current) != OTHER:
        return current

    return build_inquiry_context(history, current_input, user_only=True)


def build_intent_context(
    history: list[dict[str, str]] | None,
    current_input: str,
) -> str:
    """意図理解 LLM 用に、ユーザー・アシスタント双方の直近履歴を含めた文脈を作る。"""
    if not history:
        return current_input.strip()
    return build_inquiry_context(history, current_input, user_only=False)


def trim_stored_messages(
    messages: list[dict[str, str]],
    max_messages: int = MAX_STORED_MESSAGES,
) -> list[dict[str, str]]:
    """セッション内の会話履歴が上限を超えたら古いものから切り捨てる。"""
    if max_messages <= 0 or len(messages) <= max_messages:
        return messages
    return messages[-max_messages:]


def classify(text: str) -> str:
    """問い合わせ文を1カテゴリに分類する。"""
    if not text or not text.strip():
        return OTHER

    t = text.strip()

    for kw in MISTAKE_KEYWORDS:
        if kw in t:
            return MISTAKE_REPORT

    for kw in RULE_KEYWORDS:
        if kw in t:
            return RULE_CHECK

    return OTHER


def classify_category(text: str) -> str:
    """問い合わせ文を詳細カテゴリに分類する。"""
    if not text or not text.strip():
        return OTHER

    t = text.strip()

    # 上から順に判定します（例: 「電車遅延で遅刻」は電車遅延を優先）。
    for label, keywords in CATEGORY_KEYWORDS:
        for kw in keywords:
            if kw in t:
                return label

    return OTHER


def handoff_template_for_category(category: str) -> str:
    """カテゴリに対応する人への引き継ぎテンプレを返す。未定義なら「その他」用を使う。"""
    return HANDOFF_TEMPLATES.get(category, HANDOFF_TEMPLATES[OTHER])


def load_rules() -> dict[str, str]:
    """
    rules.txt を読み込み、[セクション名] と次の [ までの本文を辞書にまとめる。

    例:
        [遅刻]
        遅刻する場合は...

    → {"遅刻": "遅刻する場合は..."}
    """
    if not RULES_PATH.is_file():
        return {}

    try:
        raw = RULES_PATH.read_text(encoding="utf-8")
    except OSError:
        return {}

    # セクション名 → 本文（外部APIなしの「擬似AI」で参照するデータ）
    sections: dict[str, str] = {}
    current_title: str | None = None
    body_lines: list[str] = []

    for line in raw.splitlines():
        s = line.strip()
        # [遅刻] のような行を見つけたら、直前のセクションを確定して次へ
        if s.startswith("[") and s.endswith("]") and len(s) >= 2:
            if current_title is not None:
                sections[current_title] = "\n".join(body_lines).strip()
            current_title = s[1:-1].strip()
            body_lines = []
            continue

        if current_title is not None:
            body_lines.append(line)

    if current_title is not None:
        sections[current_title] = "\n".join(body_lines).strip()

    return sections


def get_rule_answer(category: str, rules: dict[str, str]) -> str | None:
    """
    カテゴリ名に一致するセクション本文を返す。
    rules.txt に [カテゴリ名] が無い、または本文が空なら None。
    """
    text = rules.get(category)
    if text is None:
        return None
    text = text.strip()
    return text if text else None


def generate_answer(user_input: str, category: str, rules: dict[str, str]) -> str:
    """ルール確認向けの回答文を LLM で生成する（関連ルールのみ API に送信）。"""
    rule_context = get_rule_answer(category, rules)
    if rule_context is None:
        dev_log_llm(called=False, reason="ルール未該当")
        return "該当するルールが見つかりません。管理者に確認してください。"
    return generate_llm_response(user_input, rule_context)


def process_inquiry(
    user_input: str,
    rules: dict[str, str] | None = None,
    conversation_history: list[dict[str, str]] | None = None,
) -> dict[str, str | dict[str, str | bool] | None]:
    """
    1件の問い合わせを処理して、画面表示に必要な結果をまとめて返す。

    Streamlit UI と CLI の両方から同じ処理を呼べるようにしておくと、
    判定ロジックの修正が1か所で済みます。

    conversation_history が渡された場合、直近の履歴と合わせた文脈で判定する。
    履歴は MAX_PROCESSING_HISTORY 件までに制限する。
    """
    rule_data = load_rules() if rules is None else rules

    if conversation_history:
        inquiry_text = resolve_inquiry_text(conversation_history, user_input)
    else:
        inquiry_text = user_input.strip()

    intent_context = build_intent_context(conversation_history, user_input)
    intent_result = analyze_intent(intent_context)

    inquiry_type = classify(inquiry_text)
    inquiry_category = classify_category(inquiry_text)

    result: dict[str, str | dict[str, str | bool] | None] = {
        "type": inquiry_type,
        "category": inquiry_category,
        "intent_analysis": (
            intent_analysis_to_dict(intent_result) if intent_result else None
        ),
    }

    if inquiry_type == RULE_CHECK:
        result["message"] = f"回答: {generate_answer(inquiry_text, inquiry_category, rule_data)}"
    else:
        dev_log_llm(called=False, reason=f"種別={inquiry_type}")
        template_body = handoff_template_for_category(inquiry_category)
        header = "【担当者へ回すときのメモ】\n"
        if template_body.startswith(header):
            template_body = template_body[len(header) :]
        result["message"] = (
            "管理者に確認してください。\n"
            "確認前に以下を整理してください:\n"
            f"{template_body}"
        )

    return result


def main() -> None:
    print("勤怠問い合わせボット（終了: 空行または quit）")
    # rules.txt は起動時に一度読み込む（ファイルを書き換えたらアプリを再起動）
    rules_data = load_rules()

    while True:
        line = input("> ").strip()
        if not line or line.lower() in ("quit", "exit", "q"):
            break
        result = process_inquiry(line, rules_data)

        print(f"種別: {result['type']}")
        print(f"カテゴリ: {result['category']}")
        if result.get("intent_analysis"):
            print(f"意図理解: {result['intent_analysis']}")
        print(result["message"])


if __name__ == "__main__":
    main()
