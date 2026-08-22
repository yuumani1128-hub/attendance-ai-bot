"""勤怠問い合わせボット（最小構成）: 入力を3カテゴリに分類する。"""

from __future__ import annotations

import logging
from pathlib import Path

from llm import analyze_intent, dev_log_llm, ensure_dev_logging, generate_llm_response, intent_analysis_to_dict

logger = logging.getLogger("attendance_bot")

# 分類ラベル
RULE_CHECK = "ルール確認"
MISTAKE_REPORT = "勤怠ミス報告"
CLARIFICATION = "追加確認"
OTHER = "その他"

# カテゴリ分類ラベル
CATEGORY_DESCRIPTION_MISTAKE = "記載ミス"
CATEGORY_CLOCK_MISS = "打刻漏れ"
CATEGORY_LATE = "遅刻"
CATEGORY_TRAIN_DELAY = "電車遅延"
CATEGORY_HALF_DAY_OFF = "午前休/午後休"
CATEGORY_HOLIDAY_WORK = "休日出勤"
CATEGORY_PAID_LEAVE = "有給"

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

# rules.txt 各セクションの検索用キーワード（自然言語問い合わせとの照合）
RULE_SECTION_KEYWORDS: dict[str, tuple[str, ...]] = {
    CATEGORY_LATE: ("遅刻", "遅れ", "遅れます", "間に合わない"),
    CATEGORY_TRAIN_DELAY: ("電車遅延", "電車", "遅延", "遅延証明", "人身事故", "運転見合わせ"),
    CATEGORY_CLOCK_MISS: (
        "打刻漏れ",
        "打刻忘れ",
        "打刻を忘れ",
        "打刻し忘れ",
        "打刻",
        "押し忘れ",
        "勤怠漏れ",
        "忘れ",
        "退勤",
        "出勤",
    ),
    CATEGORY_DESCRIPTION_MISTAKE: ("記載ミス", "記載", "入力ミス", "誤記", "誤入力"),
    CATEGORY_PAID_LEAVE: (
        "有給",
        "年休",
        "年次有給",
        "休暇",
        "休みたい",
        "休み",
        "申請期限",
        "申請",
        "取得",
        "取得希望",
    ),
    CATEGORY_HALF_DAY_OFF: ("午前休", "午後休", "半休", "午前だけ", "午後だけ"),
    CATEGORY_HOLIDAY_WORK: ("休日出勤", "休日勤務", "土日出勤", "祝日出勤", "休出"),
}

# 意図理解結果から検索候補セクションを絞り込む（None=全セクション、()=ルール検索しない）
INTENT_SECTION_CANDIDATES: dict[str, tuple[str, ...] | None] = {
    "rule_check": None,
    "attendance_correction": (CATEGORY_CLOCK_MISS, CATEGORY_DESCRIPTION_MISTAKE),
    "leave": (CATEGORY_PAID_LEAVE, CATEGORY_HALF_DAY_OFF),
    "needs_individual_handling": (),
    "insufficient_info": None,
    "other": (),
}

# 勤怠ドメイン語（rule_check 時に勤怠関連か判定する）
ATTENDANCE_DOMAIN_KEYWORDS: tuple[str, ...] = (
    "有給",
    "年休",
    "休暇",
    "休み",
    "打刻",
    "遅刻",
    "早退",
    "出勤",
    "退勤",
    "勤怠",
    "残業",
    "休出",
    "休日出勤",
    "午前休",
    "午後休",
    "半休",
    "電車遅延",
    "届出",
    "申請",
    "記載",
    "修正",
    "忘れ",
    "漏れ",
)

# 勤怠外と判断する語
NON_ATTENDANCE_KEYWORDS: tuple[str, ...] = (
    "ランチ",
    "おすすめ",
    "コンビニ",
    "レストラン",
    "昼食",
    "夕食",
    "食事",
    "天気",
    "株価",
)

OUT_OF_SCOPE_MESSAGE = (
    "勤怠に関するご質問に回答できます。"
    "ランチや社内施設など、勤怠ルール以外の内容にはお答えできません。"
)

# ルール検索の閾値
MIN_RULE_SEARCH_SCORE = 8
MAX_RULE_SEARCH_RESULTS = 3
# 最高スコアとの差がこの値より大きい候補は、関連性が低いとみなして除外
SCORE_RELATIVE_GAP = 10

# セクション横断で共通のため、本文ラベル一致の加点対象外
GENERIC_BODY_LABELS = frozenset({"時刻", "届出", "備考欄", "その他"})

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


def already_asked_clarification(history: list[dict[str, str]] | None) -> bool:
    """直近のアシスタント発言が追加確認だったかどうか。"""
    if not history:
        return False
    for msg in reversed(history):
        if msg.get("role") == "assistant":
            return bool(msg.get("is_clarification"))
    return False


def needs_clock_type_clarification(conversation_text: str) -> bool:
    """打刻漏れ報告で、出勤/退勤/休憩のどれかが会話上まだ特定できない場合。"""
    if not any(kw in conversation_text for kw in ("打刻", "忘れ", "漏れ")):
        return False
    if any(kw in conversation_text for kw in ("出勤", "退勤", "休憩")):
        return False
    return True


def needs_leave_date_clarification(conversation_text: str) -> bool:
    """有給・休暇の取得希望で、取得予定日などが会話上まだ特定できない場合。"""
    if not any(kw in conversation_text for kw in ("有給", "休暇", "休み", "午前休", "午後休", "半休")):
        return False
    date_hints = (
        "今日",
        "明日",
        "明後日",
        "来週",
        "再来週",
        "来月",
        "月曜",
        "火曜",
        "水曜",
        "木曜",
        "金曜",
        "土曜",
        "日曜",
        "取得予定",
        "予定日",
        "年",
        "/",
        "日から",
        "日まで",
        "日に",
    )
    if any(hint in conversation_text for hint in date_hints):
        return False
    for day in range(1, 32):
        if f"{day}日" in conversation_text:
            return False
    return True


def should_request_clarification(
    intent_result,
    conversation_history: list[dict[str, str]] | None,
    intent_context: str,
) -> bool:
    """追加確認が必要かどうか（LLM 判定 + 最小限のフォールバック）。"""
    if not intent_result or already_asked_clarification(conversation_history):
        return False
    if intent_result.needs_clarification:
        return True
    if (
        intent_result.intent in ("attendance_correction", "insufficient_info")
        and needs_clock_type_clarification(intent_context)
    ):
        return True
    if intent_result.intent == "leave" and needs_leave_date_clarification(intent_context):
        return True
    return False


def clarification_message(intent_result, intent_context: str = "") -> str:
    """意図理解結果から、ユーザーへ返す追加質問文を作る。"""
    question = intent_result.clarification_question.strip()
    if question:
        return question
    if needs_clock_type_clarification(intent_context):
        return "出勤と退勤、どちらの打刻でしょうか？"
    if intent_result.intent == "leave" and needs_leave_date_clarification(intent_context):
        return "有給取得についてですね。いつ取得予定ですか？"
    reason = intent_result.reason.strip()
    if reason:
        return f"確認させてください。{reason}"
    return "もう少し詳しく教えてください。"


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


def is_leave_policy_question(query: str) -> bool:
    """有給・休暇の制度・期限に関するルール確認か（取得申告ではない）。"""
    if not any(kw in query for kw in ("有給", "年休", "休暇", "休み")):
        return False
    return any(
        kw in query
        for kw in (
            "いつまで",
            "何日前",
            "申請期限",
            "期限",
            "ルール",
            "方法",
            "教えて",
            "確認",
            "できますか",
        )
    )


def is_attendance_inquiry(query: str, intent: str | None) -> bool:
    """勤怠に関する問い合わせかどうか（勤怠外はルール検索前に除外）。"""
    if any(kw in query for kw in NON_ATTENDANCE_KEYWORDS):
        return False
    if intent == "other":
        return False
    if intent in (
        "attendance_correction",
        "leave",
        "needs_individual_handling",
        "insufficient_info",
    ):
        return True
    if intent in ("rule_check", None):
        return any(kw in query for kw in ATTENDANCE_DOMAIN_KEYWORDS)
    return False


def _has_direct_section_match(section_name: str, query: str) -> bool:
    """問い合わせ文にセクション名またはセクション固有キーワードが含まれるか。"""
    if section_name in query:
        return True
    return any(
        kw in query for kw in RULE_SECTION_KEYWORDS.get(section_name, (section_name,))
    )


def dev_log_rule_search(
    query: str,
    intent: str | None,
    matches: list[tuple[str, int]],
) -> None:
    """ルール検索結果を開発用ログに出す（本番 UI には表示しない）。"""
    ensure_dev_logging()
    if not matches:
        logger.info(
            "ルール検索: query=%r intent=%s 件数=0 sections=[]",
            query,
            intent or "-",
        )
        return
    sections = [f"{name}(score={score})" for name, score in matches]
    logger.info(
        "ルール検索: query=%r intent=%s 件数=%d sections=%s",
        query,
        intent or "-",
        len(matches),
        sections,
    )


def _intent_search_candidates(intent: str | None) -> set[str] | None:
    """
    intent に応じて検索対象セクションを絞る。
    None=全セクション、set()=検索しない。
    """
    if intent is None:
        return None
    candidates = INTENT_SECTION_CANDIDATES.get(intent)
    if candidates is None:
        return None
    return set(candidates)


def _format_rule_section(section_name: str, body: str) -> str:
    """LLM に渡す1セクション分のテキスト。"""
    return f"[{section_name}]\n{body.strip()}"


def _score_rule_section(
    section_name: str,
    body: str,
    query: str,
    category_hint: str | None = None,
) -> int:
    """問い合わせ文とセクションの関連度スコア（セクション固有キーワードのみ）。"""
    score = 0

    if section_name in query:
        score += 10

    matched_keywords = 0
    for keyword in RULE_SECTION_KEYWORDS.get(section_name, (section_name,)):
        if keyword in query:
            score += 5
            matched_keywords += 1

    # セクション固有の本文ラベルのみ加点（「届出」「備考欄」等の汎用語は除外）
    for line in body.splitlines():
        label = line.split("：", 1)[0].strip()
        if label in GENERIC_BODY_LABELS:
            continue
        if len(label) >= 2 and label in query:
            score += 3

    if category_hint and category_hint != OTHER and category_hint == section_name:
        score += 8

    # キーワード一致が1件も無く、セクション名も無い場合は加点しない
    if matched_keywords == 0 and section_name not in query:
        if not (category_hint and category_hint == section_name):
            return 0

    return score


def search_rules(
    query: str,
    rules: dict[str, str] | None = None,
    intent: str | None = None,
    category_hint: str | None = None,
    max_results: int = MAX_RULE_SEARCH_RESULTS,
) -> list[str]:
    """
    自然言語の問い合わせから関連ルールを検索し、セクション単位のリストを返す。

    intent は検索対象セクションの絞り込みに使う補助情報。
    関連度が MIN_RULE_SEARCH_SCORE 未満の場合は空リストを返す。
    """
    rule_data = load_rules() if rules is None else rules
    if not rule_data or not query.strip():
        dev_log_rule_search(query, intent, [])
        return []

    candidate_sections = _intent_search_candidates(intent)
    if candidate_sections is not None and not candidate_sections:
        dev_log_rule_search(query, intent, [])
        return []

    scored: list[tuple[str, str, int]] = []
    for section_name, body in rule_data.items():
        if candidate_sections is not None and section_name not in candidate_sections:
            continue
        body = body.strip()
        if not body:
            continue
        score = _score_rule_section(section_name, body, query, category_hint)
        if score > 0:
            scored.append((section_name, body, score))

    scored.sort(key=lambda item: item[2], reverse=True)
    qualified = [
        (name, body, score)
        for name, body, score in scored
        if score >= MIN_RULE_SEARCH_SCORE and _has_direct_section_match(name, query)
    ]

    if not qualified:
        dev_log_rule_search(query, intent, [])
        return []

    best_score = qualified[0][2]
    selected: list[tuple[str, int]] = []
    for name, body, score in qualified:
        if len(selected) >= max_results:
            break
        if selected and score < best_score - SCORE_RELATIVE_GAP:
            break
        selected.append((name, score))

    dev_log_rule_search(query, intent, selected)
    body_by_name = {name: body for name, body, _ in qualified}
    return [_format_rule_section(name, body_by_name[name]) for name, _ in selected]


def _section_name_from_rule_block(rule_block: str) -> str | None:
    """search_rules が返す `[セクション名]\\n...` 形式からセクション名を取り出す。"""
    if rule_block.startswith("[") and "]" in rule_block:
        return rule_block[1 : rule_block.index("]")].strip()
    return None


def resolve_handoff_category(
    inquiry_text: str,
    intent: str | None,
    legacy_category: str,
) -> str:
    """管理者案内テンプレート用カテゴリ（旧 classify_category は補助）。"""
    if legacy_category != OTHER:
        return legacy_category
    if intent == "leave":
        if any(kw in inquiry_text for kw in ("有給", "年休", "休暇")):
            return CATEGORY_PAID_LEAVE
        return CATEGORY_HALF_DAY_OFF
    if intent == "attendance_correction":
        if any(kw in inquiry_text for kw in ("記載", "入力ミス", "誤記")):
            return CATEGORY_DESCRIPTION_MISTAKE
        return CATEGORY_CLOCK_MISS
    return OTHER


def build_handoff_message(category: str) -> str:
    """管理者確認案内メッセージを組み立てる。"""
    template_body = handoff_template_for_category(category)
    header = "【担当者へ回すときのメモ】\n"
    if template_body.startswith(header):
        template_body = template_body[len(header) :]
    return (
        "管理者に確認してください。\n"
        "確認前に以下を整理してください:\n"
        f"{template_body}"
    )


def result_type_for_intent(intent: str | None) -> str:
    """意図理解結果から UI 表示用の種別ラベルを決める。"""
    if intent == "rule_check":
        return RULE_CHECK
    if intent == "attendance_correction":
        return MISTAKE_REPORT
    return OTHER


def generate_answer(
    user_input: str,
    rules: dict[str, str],
    intent: str | None = None,
    category_hint: str | None = None,
) -> tuple[str, list[str]]:
    """
    ルール確認向けの回答文を LLM で生成する（関連ルールのみ API に送信）。

    Returns:
        (回答文, マッチしたルールブロックのリスト)
    """
    matched_rules = search_rules(
        user_input,
        rules=rules,
        intent=intent,
        category_hint=category_hint,
    )
    if not matched_rules:
        dev_log_llm(called=False, reason="ルール未該当")
        return ("該当するルールが見つかりません。管理者に確認してください。", [])
    rule_context = "\n\n".join(matched_rules)
    return (generate_llm_response(user_input, rule_context), matched_rules)


def process_inquiry(
    user_input: str,
    rules: dict[str, str] | None = None,
    conversation_history: list[dict[str, str]] | None = None,
) -> dict[str, str | dict[str, str | bool] | None | bool]:
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
    intent_name = intent_result.intent if intent_result else None

    # 旧カテゴリ判定は補助情報（検索精度・UI 表示用）。主経路では必須にしない。
    legacy_type = classify(inquiry_text)
    legacy_category = classify_category(inquiry_text)
    category_hint = legacy_category if legacy_category != OTHER else None

    result: dict[str, str | dict[str, str | bool] | None | bool] = {
        "type": legacy_type,
        "category": legacy_category,
        "intent_analysis": (
            intent_analysis_to_dict(intent_result) if intent_result else None
        ),
        "is_clarification": False,
    }

    if intent_result and should_request_clarification(
        intent_result, conversation_history, intent_context
    ):
        dev_log_llm(called=False, reason="追加確認")
        result["type"] = CLARIFICATION
        result["is_clarification"] = True
        result["message"] = clarification_message(intent_result, intent_context)
        return result

    if not is_attendance_inquiry(inquiry_text, intent_name):
        dev_log_llm(called=False, reason="勤怠外")
        result["type"] = OTHER
        result["message"] = OUT_OF_SCOPE_MESSAGE
        return result

    # --- 主経路: LLM 意図理解 → ルール検索 or 管理者案内 ---
    if intent_name in ("rule_check", None):
        answer, matched_rules = generate_answer(
            inquiry_text, rule_data, intent=intent_name, category_hint=category_hint
        )
        result["type"] = RULE_CHECK
        if matched_rules:
            section = _section_name_from_rule_block(matched_rules[0])
            if section:
                result["category"] = section
        result["message"] = f"回答: {answer}"
        return result

    if intent_name == "leave" and is_leave_policy_question(inquiry_text):
        answer, matched_rules = generate_answer(
            inquiry_text,
            rule_data,
            intent="rule_check",
            category_hint=CATEGORY_PAID_LEAVE,
        )
        result["type"] = RULE_CHECK
        if matched_rules:
            section = _section_name_from_rule_block(matched_rules[0])
            if section:
                result["category"] = section
        result["message"] = f"回答: {answer}"
        return result

    if intent_name in ("attendance_correction", "leave", "needs_individual_handling"):
        handoff_category = resolve_handoff_category(
            inquiry_text, intent_name, legacy_category
        )
        dev_log_llm(called=False, reason=f"意図={intent_name}")
        result["type"] = result_type_for_intent(intent_name)
        result["category"] = handoff_category
        result["message"] = build_handoff_message(handoff_category)
        return result

    # insufficient_info 等: ルール検索を試み、なければ該当なし
    answer, matched_rules = generate_answer(
        inquiry_text,
        rule_data,
        intent=intent_name,
        category_hint=category_hint,
    )
    if matched_rules:
        result["type"] = RULE_CHECK
        section = _section_name_from_rule_block(matched_rules[0])
        if section:
            result["category"] = section
        result["message"] = f"回答: {answer}"
        return result

    result["type"] = RULE_CHECK
    result["message"] = f"回答: {answer}"
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
