#!/usr/bin/env python3
"""
run_slot.py — 슬롯 실행 메인 스크립트
GitHub Actions에서 호출됨
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

import anthropic
import pytz
import requests

KST = pytz.timezone("Asia/Seoul")
BASE_DIR = Path(__file__).parent
SKILLS_DIR = BASE_DIR / "skills"
HISTORY_FILE = BASE_DIR / "history" / "history.json"
RETENTION_DAYS = 3


# ── 슬롯별 스킬 파일 매핑 ──────────────────────────────────────
SLOT_SKILL_MAP = {
    1: "slot1.md",
    2: "slot2.md",
    3: "slot3-4.md",
    4: "slot3-4.md",
    5: "slot5-6.md",
    6: "slot5-6.md",
}

SLOT_LABEL = {
    1: "SLOT 1 - 조간 (07:00)",
    2: "SLOT 2 - 정부브리핑 (09:30)",
    3: "SLOT 3 - 커뮤니티 (12:00)",
    4: "SLOT 4 - 커뮤니티 심화 (15:00)",
    5: "SLOT 5 - 유튜브+비주류 (17:30)",
    6: "SLOT 6 - 유튜브 클립 (19:00)",
}


# ── 이력 관리 ───────────────────────────────────────────────────
def load_history():
    if not HISTORY_FILE.exists():
        return {"version": "1.0", "retention_days": RETENTION_DAYS, "entries": []}
    with open(HISTORY_FILE, encoding="utf-8") as f:
        return json.load(f)


def save_history(data):
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def today_kst():
    return datetime.now(KST).strftime("%Y-%m-%d")


def get_blacklist(data):
    today = today_kst()
    items = []
    for entry in data.get("entries", []):
        if entry["expires"] >= today:
            items.extend(entry["items"])
    return items


def clean_expired(data):
    today = today_kst()
    data["entries"] = [e for e in data["entries"] if e["expires"] >= today]
    return data


def add_to_history(data, new_items):
    today = today_kst()
    expires = (datetime.strptime(today, "%Y-%m-%d") + timedelta(days=RETENTION_DAYS)).strftime("%Y-%m-%d")
    existing = next((e for e in data["entries"] if e["date"] == today), None)
    if existing:
        for item in new_items:
            if item not in existing["items"]:
                existing["items"].append(item)
    else:
        data["entries"].append({"date": today, "expires": expires, "items": list(new_items)})
    return data


# ── 시스템 프롬프트 조립 ─────────────────────────────────────────
def build_system_prompt(slot: int, blacklist: list) -> str:
    core = (SKILLS_DIR / "core.md").read_text(encoding="utf-8")
    slot_skill = (SKILLS_DIR / SLOT_SKILL_MAP[slot]).read_text(encoding="utf-8")

    blacklist_section = "## 금일 소재 블랙리스트 (재제안 금지)\n"
    if blacklist:
        blacklist_section += "\n".join(f"- {item}" for item in blacklist)
    else:
        blacklist_section += "- (없음)"

    return f"{core}\n\n---\n\n{slot_skill}\n\n---\n\n{blacklist_section}"


# ── Anthropic API 호출 (web_search 툴 포함) ─────────────────────
def call_claude(system_prompt: str, slot: int) -> str:
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    today = today_kst()

    user_message = (
        f"오늘 날짜: {today} KST\n"
        f"현재 슬롯: {SLOT_LABEL[slot]}\n\n"
        f"위 지침에 따라 web_search 툴을 사용해 실시간 리서치를 진행하고, "
        f"소재 팩트 + 출처 링크 형태로만 결과를 전달해줘."
    )

    # web_search 툴 활성화 (Sonnet 이상에서만 지원)
    tools = [{"type": "web_search_20250305", "name": "web_search"}]

    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=2000,
        system=system_prompt,
        tools=tools,
        messages=[{"role": "user", "content": user_message}],
    )

    # 텍스트 블록만 추출 (tool_use / tool_result 블록 제외)
    result_parts = [
        block.text for block in message.content
        if hasattr(block, "text")
    ]
    raw = "\n".join(result_parts).strip()

    # 마크다운 특수문자 제거 (텔레그램 plain text 전송용)
    clean = re.sub(r'[*_`#\[\]()~>+=|{}.!-]', '', raw)
    return clean


# ── 텔레그램 발송 ───────────────────────────────────────────────
def send_telegram(text: str, slot: int):
    bot_token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]
    label = SLOT_LABEL[slot]
    today = today_kst()

    # plain text 전송 (parse_mode 없음)
    full_message = f"📋 {label}\n🗓 {today}\n\n{text}"

    # 텔레그램 메시지 최대 4096자 제한
    if len(full_message) > 4096:
        full_message = full_message[:4090] + "\n..."

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": full_message,
        "disable_web_page_preview": False,
    }
    resp = requests.post(url, json=payload, timeout=10)

    if resp.status_code != 200:
        print(f"텔레그램 발송 실패: {resp.status_code} {resp.text}", file=sys.stderr)
        sys.exit(1)

    print(f"텔레그램 발송 완료 → chat_id: {chat_id}")


# ── 결과에서 소재 키워드 추출 (이력 등록용) ──────────────────────
def extract_keywords(result_text: str) -> list:
    keywords = []
    for line in result_text.split("\n"):
        line = line.strip().lstrip("-•*").strip()
        if len(line) > 4 and not line.startswith("http"):
            keyword = line[:20].replace(" ", "")
            if keyword:
                keywords.append(keyword)
        if len(keywords) >= 5:
            break
    return keywords


# ── 메인 ────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--slot", type=int, required=True, choices=range(1, 7))
    args = parser.parse_args()
    slot = args.slot

    print(f"=== {SLOT_LABEL[slot]} 실행 시작 ===")

    # 이력 로드 + 만료 정리
    history_data = load_history()
    history_data = clean_expired(history_data)
    blacklist = get_blacklist(history_data)
    print(f"블랙리스트 항목: {len(blacklist)}개")

    # 시스템 프롬프트 조립
    system_prompt = build_system_prompt(slot, blacklist)
    print(f"시스템 프롬프트: {len(system_prompt)}자")

    # Claude API 호출
    print("Claude API 호출 중...")
    result = call_claude(system_prompt, slot)
    print(f"결과 수신 완료 ({len(result)}자)")
    print("\n--- 결과 미리보기 ---")
    print(result[:300] + "..." if len(result) > 300 else result)
    print("---\n")

    # 텔레그램 발송
    send_telegram(result, slot)

    # 이력 업데이트
    keywords = extract_keywords(result)
    if keywords:
        history_data = add_to_history(history_data, keywords)
        save_history(history_data)
        print(f"이력 추가: {keywords}")

    print(f"=== SLOT {slot} 완료 ===")


if __name__ == "__main__":
    main()
