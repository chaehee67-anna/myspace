#!/usr/bin/env python3
"""
run_slot.py - 슬롯 실행 메인 스크립트
GitHub Actions에서 호출됨
"""

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import anthropic
import feedparser
import pytz
import requests

KST = pytz.timezone("Asia/Seoul")
BASE_DIR = Path(__file__).parent
SKILLS_DIR = BASE_DIR / "skills"
HISTORY_FILE = BASE_DIR / "history" / "history.json"
RETENTION_DAYS = 3

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

RSS_FEEDS = {
    "politics": "https://news.naver.com/main/rss/listRss.naver?sectionId=100",
    "economy":  "https://news.naver.com/main/rss/listRss.naver?sectionId=101",
    "society":  "https://news.naver.com/main/rss/listRss.naver?sectionId=102",
    "world":    "https://news.naver.com/main/rss/listRss.naver?sectionId=104",
    "it":       "https://news.naver.com/main/rss/listRss.naver?sectionId=105",
}

# Naver 차단 시 폴백 (Google News - 해외 IP 항상 접근 가능)
RSS_FALLBACK = {
    "politics": "https://news.google.com/rss/search?q=한국+정치&hl=ko&gl=KR&ceid=KR:ko",
    "economy":  "https://news.google.com/rss/search?q=한국+경제&hl=ko&gl=KR&ceid=KR:ko",
    "society":  "https://news.google.com/rss/search?q=한국+사회&hl=ko&gl=KR&ceid=KR:ko",
    "world":    "https://news.google.com/rss/search?q=한국+국제&hl=ko&gl=KR&ceid=KR:ko",
    "it":       "https://news.google.com/rss/search?q=한국+IT+기술&hl=ko&gl=KR&ceid=KR:ko",
}

SLOT_RSS_MAP = {
    1: ["politics", "society"],
    2: ["politics", "economy"],
    3: ["politics", "society"],
    4: ["politics", "society"],
    5: ["society", "world", "it"],
    6: ["society", "it"],
}


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


HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept-Language": "ko-KR,ko;q=0.9",
}


def fetch_rss_articles(slot: int, max_articles: int = 15) -> str:
    feed_keys = SLOT_RSS_MAP[slot]
    articles = []

    for key in feed_keys:
        urls = [(RSS_FEEDS[key], "Naver"), (RSS_FALLBACK[key], "Google")]
        for url, source in urls:
            try:
                resp = requests.get(url, headers=HEADERS, timeout=10)
                resp.raise_for_status()
                feed = feedparser.parse(resp.text)
                count = len(feed.entries)
                print(f"RSS [{key}] {source}: {count}개 항목 수신")
                if count == 0:
                    continue
                for entry in feed.entries[:10]:
                    title = entry.get("title", "").strip()
                    link = entry.get("link", "").strip()
                    summary = re.sub(r"<[^>]+>", "", entry.get("summary", ""))[:200].strip()
                    if title and link:
                        articles.append(f"제목: {title}\n요약: {summary}\n링크: {link}")
                break  # 성공하면 폴백 불필요
            except Exception as e:
                print(f"RSS 파싱 실패 [{key}] {source}: {e}")

    seen, unique = set(), []
    for a in articles:
        k = a[:50]
        if k not in seen:
            seen.add(k)
            unique.append(a)

    print(f"RSS 총 수집: {len(unique)}개 (중복 제거 후)")
    return "\n\n".join(unique[:max_articles])


def build_system_prompt(slot: int, blacklist: list) -> str:
    core = (SKILLS_DIR / "core.md").read_text(encoding="utf-8")
    slot_skill = (SKILLS_DIR / SLOT_SKILL_MAP[slot]).read_text(encoding="utf-8")
    bl = ", ".join(blacklist) if blacklist else "없음"
    return f"{core}\n\n---\n\n{slot_skill}\n\n---\n\n재제안 금지 소재: {bl}"


def call_claude(system_prompt: str, slot: int, articles: str) -> str:
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    today = today_kst()

    user_message = (
        f"오늘: {today} KST\n"
        f"슬롯: {SLOT_LABEL[slot]}\n\n"
        f"아래 기사 목록에서 슬롯 조건에 가장 가까운 기사를 반드시 1개 선택해 X 게시글을 작성하라.\n"
        f"완벽한 조건의 기사가 없어도 목록 중 가장 적합한 기사로 작성한다. 거절하지 마라.\n"
        f"출력 형식 (이것만 출력):\n[게시글 본문]\n\n출처: [URL]\n\n"
        f"--- 기사 목록 ---\n{articles}"
    )

    for attempt in range(3):
        try:
            message = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=400,
                system=system_prompt,
                messages=[{"role": "user", "content": user_message}],
            )
            break
        except anthropic.RateLimitError:
            if attempt < 2:
                print(f"Rate limit 초과. 60초 후 재시도 ({attempt+1}/3)...")
                time.sleep(60)
            else:
                raise

    result_parts = [block.text for block in message.content if hasattr(block, "text")]
    raw = "\n".join(result_parts).strip()
    clean = re.sub(r"[*_`\[\]()~>+=|{}!]", "", raw)
    clean = re.sub(r"(?<!\w)#", "", clean)
    return clean


def _send_debug(msg: str, slot: int):
    try:
        bot_token = os.environ["TELEGRAM_BOT_TOKEN"]
        chat_id = os.environ["TELEGRAM_CHAT_ID"]
        requests.post(
            f"https://api.telegram.org/bot{bot_token}/sendMessage",
            json={"chat_id": chat_id, "text": f"🔧 DEBUG SLOT {slot}\n\n{msg}"},
            timeout=10,
        )
    except Exception:
        pass


def send_telegram(text: str, slot: int):
    bot_token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]
    today = today_kst()

    full_message = f"📋 {SLOT_LABEL[slot]}\n🗓 {today}\n\n{text}"
    if len(full_message) > 4096:
        full_message = full_message[:4090] + "\n..."

    resp = requests.post(
        f"https://api.telegram.org/bot{bot_token}/sendMessage",
        json={"chat_id": chat_id, "text": full_message, "disable_web_page_preview": False},
        timeout=10,
    )
    if resp.status_code != 200:
        print(f"텔레그램 발송 실패: {resp.status_code} {resp.text}", file=sys.stderr)
        sys.exit(1)
    print(f"텔레그램 발송 완료 → chat_id: {chat_id}")


def extract_keywords(result_text: str) -> list:
    keywords = []
    for line in result_text.split("\n"):
        line = line.strip().lstrip("-").strip()
        if len(line) > 4 and not line.startswith("http"):
            keywords.append(line[:20].replace(" ", ""))
        if len(keywords) >= 5:
            break
    return keywords


NO_CONTENT_MARKERS = [
    "소재 없음", "채택 불가", "접근 불가", "데이터 부재", "결과 없음",
    "기사 없음", "없음", "불가", "모의 실행", "확인 불가", "찾을 수 없",
]


def is_valid_result(text: str) -> bool:
    if len(text) < 30:
        return False
    if "출처:" not in text and "http" not in text:
        return False
    if any(m in text for m in NO_CONTENT_MARKERS):
        return False
    return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--slot", type=int, required=True, choices=range(1, 7))
    args = parser.parse_args()
    slot = args.slot

    print(f"=== {SLOT_LABEL[slot]} 실행 시작 ===")

    history_data = load_history()
    history_data = clean_expired(history_data)
    blacklist = get_blacklist(history_data)
    print(f"블랙리스트: {len(blacklist)}개")

    print("RSS 기사 수집 중...")
    articles = fetch_rss_articles(slot)
    article_count = articles.count("제목:")
    print(f"수집된 기사: {article_count}개")

    if not articles:
        _send_debug(f"[SLOT {slot}] RSS 기사 0건 — 수집 실패", slot)
        sys.exit(0)

    system_prompt = build_system_prompt(slot, blacklist)
    print(f"프롬프트: {len(system_prompt)}자")

    print("Claude API 호출 중 (포맷팅)...")
    result = call_claude(system_prompt, slot, articles)
    print(f"결과: {len(result)}자")
    print(result[:200] + "..." if len(result) > 200 else result)

    if not is_valid_result(result):
        _send_debug(
            f"[SLOT {slot}] is_valid_result 실패\n"
            f"길이: {len(result)}자\n"
            f"출처 포함: {'출처:' in result or 'http' in result}\n"
            f"Claude 출력:\n{result[:300]}",
            slot,
        )
        print("유효한 소재 없음 — 텔레그램 전송 건너뜀")
        print(f"=== SLOT {slot} 완료 (전송 없음) ===")
        sys.exit(0)

    send_telegram(result, slot)

    keywords = extract_keywords(result)
    if keywords:
        history_data = add_to_history(history_data, keywords)
        save_history(history_data)
        print(f"이력 추가: {keywords}")

    print(f"=== SLOT {slot} 완료 ===")


if __name__ == "__main__":
    main()
