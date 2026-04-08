"""勤怠問い合わせボット（最小構成）: 入力を3カテゴリに分類する。"""

from __future__ import annotations

# 分類ラベル
RULE_CHECK = "ルール確認"
MISTAKE_REPORT = "勤怠ミス報告"
OTHER = "その他"

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


def main() -> None:
    print("勤怠問い合わせボット（終了: 空行または quit）")
    while True:
        line = input("> ").strip()
        if not line or line.lower() in ("quit", "exit", "q"):
            break
        category = classify(line)
        print(f"分類: {category}")


if __name__ == "__main__":
    main()
