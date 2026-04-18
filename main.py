"""勤怠問い合わせボット（最小構成）: 入力を3カテゴリに分類する。"""

from __future__ import annotations

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


def main() -> None:
    print("勤怠問い合わせボット（終了: 空行または quit）")
    while True:
        line = input("> ").strip()
        if not line or line.lower() in ("quit", "exit", "q"):
            break
        # 既存の大分類（種別）
        inquiry_type = classify(line)
        # 追加した詳細分類（カテゴリ）
        inquiry_category = classify_category(line)

        print(f"種別: {inquiry_type}")
        print(f"カテゴリ: {inquiry_category}")

        # ルール確認はFAQ等で完結させる想定のため、人への回し文は出さない。
        # 勤怠ミス報告・その他のときだけ、カテゴリに応じたテンプレを表示する。
        if inquiry_type in (MISTAKE_REPORT, OTHER):
            print(handoff_template_for_category(inquiry_category))


if __name__ == "__main__":
    main()
