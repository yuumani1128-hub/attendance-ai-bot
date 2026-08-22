"""OpenAI API を用いたルール確認回答の生成。"""

from __future__ import annotations

import json
import logging
import os
from typing import Literal

from dotenv import load_dotenv
from openai import OpenAI
from pydantic import BaseModel, Field

load_dotenv()

logger = logging.getLogger("attendance_bot")

# モデル名はここ1か所で変更
OPENAI_MODEL = "gpt-4o-mini"

MAX_OUTPUT_TOKENS = 300

LLM_UNAVAILABLE_MESSAGE = "現在AI回答を利用できません。管理者へ確認してください。"

SYSTEM_PROMPT = (
    "社内勤怠問い合わせアシスタント。"
    "【ルール】に記載された内容のみを根拠に、簡潔な日本語で回答する。"
    "質問が短くても、提供されたルールに該当する記載があれば、その内容を説明する。"
    "ルールに記載が無いことだけ推測せず、"
    "「ルール上確認できないため、管理者へ確認してください」と案内する。"
    "存在しない制度や手続きは作らない。"
)

IntentType = Literal[
    "rule_check",
    "attendance_correction",
    "leave",
    "needs_individual_handling",
    "insufficient_info",
    "other",
]


class IntentAnalysis(BaseModel):
    """LLM による意図理解結果（Structured Output）。"""

    intent: IntentType = Field(
        description=(
            "rule_check=ルール確認, attendance_correction=打刻ミス, "
            "leave=有給・休暇, needs_individual_handling=個別対応, "
            "insufficient_info=情報不足, other=その他"
        )
    )
    needs_clarification: bool = Field(
        description="追加で1回ユーザーへ確認すべき情報がある場合 true"
    )
    reason: str = Field(description="意図判定の理由（日本語・簡潔）")


INTENT_SYSTEM_PROMPT = (
    "社内勤怠問い合わせの意図分類アシスタント。"
    "会話履歴と最新のユーザー発言を読み、intent を1つ選ぶ。"
    "rule_check=ルール・制度・手続きの確認。"
    "attendance_correction=打刻漏れ・記載ミス・打刻修正。"
    "leave=有給・休暇・午前休・午後休。"
    "needs_individual_handling=管理者判断が必要（承認、個別可否、実績確定など）。"
    "insufficient_info=意図は推測できるが回答に必要な情報が不足。"
    "other=上記に当てはまらない。"
    "needs_clarification は、1回の追加質問で足りる情報が欠けている場合 true。"
    "reason には判定理由を日本語で簡潔に書く。"
    "会話履歴に既にある情報を再度不足としない。"
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


def dev_log_intent_analysis(analysis: IntentAnalysis | None, reason: str = "") -> None:
    """意図理解（Structured Output）の結果を開発用ログに出す。"""
    ensure_dev_logging()
    if analysis is None:
        logger.info("意図理解: 取得不可 (%s)", reason or "不明")
        return
    payload = {
        "intent": analysis.intent,
        "needs_clarification": analysis.needs_clarification,
        "reason": analysis.reason,
    }
    logger.info("意図理解: %s", json.dumps(payload, ensure_ascii=False))


def intent_analysis_to_dict(analysis: IntentAnalysis) -> dict[str, str | bool]:
    """IntentAnalysis を process_inquiry の結果に載せやすい dict に変換する。"""
    return {
        "intent": analysis.intent,
        "needs_clarification": analysis.needs_clarification,
        "reason": analysis.reason,
    }


def analyze_intent(conversation_text: str) -> IntentAnalysis | None:
    """
    会話文脈からユーザーの意図を Structured Output で解釈する。
    この段階では最終回答には使わず、デバッグ・後続 Step 用。
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        dev_log_intent_analysis(None, reason="APIキー未設定")
        return None

    try:
        client = OpenAI(api_key=api_key)
        response = client.beta.chat.completions.parse(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": INTENT_SYSTEM_PROMPT},
                {"role": "user", "content": conversation_text},
            ],
            response_format=IntentAnalysis,
            temperature=0,
        )
        analysis = response.choices[0].message.parsed
        if analysis is None:
            dev_log_intent_analysis(None, reason="パース結果が空")
            return None
        dev_log_intent_analysis(analysis)
        return analysis
    except Exception as exc:
        dev_log_intent_analysis(None, reason=str(exc))
        return None


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
