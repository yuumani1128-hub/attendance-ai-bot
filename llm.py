"""OpenAI API を用いたルール確認回答の生成。"""

from __future__ import annotations

import logging
import os

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

logger = logging.getLogger("attendance_bot")

# モデル名はここ1か所で変更
OPENAI_MODEL = "gpt-4o-mini"

MAX_OUTPUT_TOKENS = 300

LLM_UNAVAILABLE_MESSAGE = "現在AI回答を利用できません。管理者へ確認してください。"

SYSTEM_PROMPT = (
    "社内勤怠問い合わせアシスタント。"
    "提供されたルールのみを根拠に、簡潔な日本語で回答する。"
    "ルールに無いことは推測せず、"
    "「ルール上確認できないため、管理者へ確認してください」と案内する。"
    "存在しない制度や手続きは作らない。"
)


def ensure_dev_logging() -> None:
    """開発用ログをターミナル（stderr）へ出力する。Streamlit 画面には出さない。"""
    if logger.handlers:
        return
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("[dev] %(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False


def dev_log_llm(called: bool, reason: str = "") -> None:
    """LLM（OpenAI API）を呼び出したかどうかだけを記録する。"""
    ensure_dev_logging()
    if called:
        logger.info("LLM呼び出し: あり")
    elif reason:
        logger.info("LLM呼び出し: なし (%s)", reason)
    else:
        logger.info("LLM呼び出し: なし")


def generate_llm_response(question: str, rule_context: str) -> str:
    """
    ユーザー質問と関連ルールだけを OpenAI API に送り、回答文を返す。
    過去のチャット履歴は送らない（1質問1回の API 呼び出し）。
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        dev_log_llm(called=False, reason="APIキー未設定")
        return LLM_UNAVAILABLE_MESSAGE

    user_content = f"【ルール】\n{rule_context}\n\n【質問】\n{question}"

    try:
        dev_log_llm(called=True)
        client = OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            max_tokens=MAX_OUTPUT_TOKENS,
            temperature=0.2,
        )
        answer = (response.choices[0].message.content or "").strip()
        if not answer:
            return LLM_UNAVAILABLE_MESSAGE
        return answer
    except Exception:
        return LLM_UNAVAILABLE_MESSAGE
