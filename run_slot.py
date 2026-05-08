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
from datetime import datetime, timedelta, timezone
from pathlib import Path

import anthropic
import feedparser
import requests

KST = timezone(timedelta(hours=9))
BASE_DIR = Path(__file__).parent
SKILLS_DIR = BASE_DIR / "skills"
HISTORY_FILE = BASE_DIR / "history" / "history.json"
RETENTION_DAYS = 3

SLOT_SKILL_MAP = {
    1: "slot1.md",
    2: "slot2.md",
    3: "slot3.md",
    4: "slot4.md",
    5: "slot5.md",
    6: "slot6.md",
}

SLOT_LABEL = {
    1: "SLOT 1 - 조간 (07:00)",
    2: "SLOT 2 - 정부브리핑 (09:30)",
    3: "SLOT 3 - 커뮤니티 (12:00)",
    4: "SLOT 4 - 커뮤니티 심화 (15:00)",
    5: "SLOT 5 - 뉴스속보+커뮤니티 (17:30)",
    6: "SLOT 6 - 유튜브 리서치 (19:00)",
}

RSS_FEEDS = {
    # Naver 섹션
    "politics": "https://news.naver.com/main/rss/listRss.naver?sectionId=100",
    "economy":  "https://news.naver.com/main/rss/listRss.naver?sectionId=101",
    # 진보 미디어 직접
    "ohmynews":   "https://www.ohmynews.com/NWS_Web/Rss/rss.aspx",
    "hani":       "https://www.hani.co.kr/rss/politics/",
    "kyunghyang": "https://www.khan.co.kr/rss/rssdata/politic_news.xml",
    "newstapa":   "https://newstapa.org/feed",
    "pressian":   "https://www.pressian.com/rss",
    # 방송사 RSS
    "mbc":  "https://imnews.imbc.com/rss/news/news_00.xml",
    "ytn":  "https://www.ytn.co.kr/_ln/rss/0101.xml",
    "jtbc": "https://news.jtbc.co.kr/rss/politics.xml",
    # 커뮤니티 반응 정치 뉴스
    "community": "https://news.google.com/rss/search?q=이재명+OR+윤석열+OR+국힘+OR+민주당+누리꾼+OR+커뮤니티+OR+반응&hl=ko&gl=KR&ceid=KR:ko",
    # 슬롯6 전용: 유튜브 채널 언급 뉴스
    "youtube_politics": "https://news.google.com/rss/search?q=매불쇼+OR+뉴스하이킥+OR+뉴스타파+OR+장르만여의도+OR+시방쇼&hl=ko&gl=KR&ceid=KR:ko",
    "youtube_media":    "https://news.google.com/rss/search?q=MBC뉴스+유튜브+OR+JTBC+유튜브+OR+시사IN+유튜브&hl=ko&gl=KR&ceid=KR:ko",
}

# 접근 실패 시 폴백 (Google News - 해외 IP 항상 접근 가능)
RSS_FALLBACK = {
    "politics":   "https://news.google.com/rss/search?q=한국+정치&hl=ko&gl=KR&ceid=KR:ko",
    "economy":    "https://news.google.com/rss/search?q=한국+경제&hl=ko&gl=KR&ceid=KR:ko",
    "ohmynews":   "https://news.google.com/rss/search?q=오마이뉴스+정치&hl=ko&gl=KR&ceid=KR:ko",
    "hani":       "https://news.google.com/rss/search?q=한겨레+정치&hl=ko&gl=KR&ceid=KR:ko",
    "kyunghyang": "https://news.google.com/rss/search?q=경향신문+정치&hl=ko&gl=KR&ceid=KR:ko",
    "newstapa":   "https://news.google.com/rss/search?q=뉴스타파&hl=ko&gl=KR&ceid=KR:ko",
    "pressian":   "https://news.google.com/rss/search?q=프레시안+정치&hl=ko&gl=KR&ceid=KR:ko",
    "mbc":        "https://news.google.com/rss/search?q=MBC+뉴스+정치&hl=ko&gl=KR&ceid=KR:ko",
    "ytn":        "https://news.google.com/rss/search?q=YTN+속보+정치&hl=ko&gl=KR&ceid=KR:ko",
    "jtbc":       "https://news.google.com/rss/search?q=JTBC+뉴스+정치&hl=ko&gl=KR&ceid=KR:ko",
    "community":        "https://news.google.com/rss/search?q=이재명+OR+윤석열+OR+국힘+누리꾼+OR+커뮤니티&hl=ko&gl=KR&ceid=KR:ko",
    "youtube_politics": "https://news.google.com/rss/search?q=매불쇼+OR+뉴스하이킥+OR+뉴스타파&hl=ko&gl=KR&ceid=KR:ko",
    "youtube_media":    "https://news.google.com/rss/search?q=유튜브+정치+클립+화제&hl=ko&gl=KR&ceid=KR:ko",
}

SLOT_RSS_MAP = {
    1: ["ohmynews", "hani", "mbc", "ytn"],               # 조간: 진보미디어 + 방송사
    2: ["politics", "economy", "kyunghyang"],              # 정부브리핑: 정치경제 + 경향
    3: ["community", "ohmynews", "pressian"],              # 커뮤니티: 반응 + 진보논평
    4: ["community", "hani", "kyunghyang"],                # 커뮤니티심화: 반응 + 심층
    5: ["ytn", "mbc", "jtbc", "community"],                # 속보+커뮤니티: 방송속보 + 반응
    6: ["youtube_politics", "youtube_media", "newstapa"],  # 유튜브리서치
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


def resolve_url(url: str) -> str:
    """Google News 리다이렉트 URL → 실제 기사 URL로 변환."""
    if "news.google.com" not in url:
        return url
    try:
        resp = requests.get(url, headers=HEADERS, timeout=8, allow_redirects=True)
        final = resp.url
        if "news.google.com" not in final:
            return final
        # HTTP 리다이렉트 실패 시 HTML에서 실제 기사 링크 추출
        match = re.search(
            r'<a[^>]+href="(https?://(?!(?:www\.)?news\.google\.com)[^"]+)"',
            resp.text,
        )
        if match:
            return match.group(1)
        return final
    except Exception:
        return url


SLOT_MAX_HOURS = {
    1: 12, 2: 12, 3: 24, 4: 24, 5: 24, 6: 48,
}


def fetch_rss_articles(slot: int, max_articles: int = 15) -> str:
    import calendar
    feed_keys = SLOT_RSS_MAP[slot]
    max_hours = SLOT_MAX_HOURS[slot]
    now = datetime.now(KST)
    cutoff = now - timedelta(hours=max_hours)
    wide_cutoff = now - timedelta(days=7)  # 폴백 재수집 시 최대 허용 범위
    articles: list[tuple[datetime, str]] = []

    for key in feed_keys:
        primary = RSS_FEEDS.get(key, "")
        fallback = RSS_FALLBACK.get(key, "")
        urls = [(u, label) for u, label in [(primary, "Primary"), (fallback, "Fallback")] if u]
        for url, source in urls:
            try:
                resp = requests.get(url, headers=HEADERS, timeout=10)
                resp.raise_for_status()
                feed = feedparser.parse(resp.text)
                count = len(feed.entries)
                print(f"RSS [{key}] {source}: {count}개 항목 수신")
                if count == 0:
                    continue
                batch: list[tuple[datetime, str]] = []
                for entry in feed.entries[:20]:
                    title = entry.get("title", "").strip()
                    link = resolve_url(entry.get("link", "").strip())
                    if not title or not link:
                        continue
                    pub = entry.get("published_parsed") or entry.get("updated_parsed")
                    if not pub:
                        continue  # 발행일 없는 항목 제외
                    pub_dt = datetime.fromtimestamp(calendar.timegm(pub), tz=KST)
                    if pub_dt < cutoff:
                        continue
                    summary = re.sub(r"<[^>]+>", "", entry.get("summary", ""))[:200].strip()
                    batch.append((pub_dt, f"제목: {title}\n요약: {summary}\n링크: {link}"))
                # 날짜 필터 후 0건이면 7일 이내로 완화해서 재시도
                if not batch:
                    print(f"  → 날짜 필터 후 0건, 7일 이내로 완화 재수집")
                    for entry in feed.entries[:10]:
                        title = entry.get("title", "").strip()
                        link = resolve_url(entry.get("link", "").strip())
                        if not title or not link:
                            continue
                        pub = entry.get("published_parsed") or entry.get("updated_parsed")
                        if not pub:
                            continue
                        pub_dt = datetime.fromtimestamp(calendar.timegm(pub), tz=KST)
                        if pub_dt < wide_cutoff:
                            continue
                        summary = re.sub(r"<[^>]+>", "", entry.get("summary", ""))[:200].strip()
                        batch.append((pub_dt, f"제목: {title}\n요약: {summary}\n링크: {link}"))
                print(f"  → 최종: {len(batch)}개")
                articles.extend(batch)
                if batch:
                    break
            except Exception as e:
                print(f"RSS 파싱 실패 [{key}] {source}: {e}")

    # 최신순 정렬 후 중복 제거
    articles.sort(key=lambda x: x[0], reverse=True)
    seen, unique = set(), []
    for _, text in articles:
        k = text[:50]
        if k not in seen:
            seen.add(k)
            unique.append(text)

    print(f"RSS 총 수집: {len(unique)}개 (중복 제거, 최신순 정렬 후)")
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
        f"아래 기사 목록에서 최대 3개를 골라 아래 형식으로만 출력하라.\n"
        f"조건과 맞지 않아도 목록에 있는 기사 중 가장 적합한 것을 반드시 선택한다. 거절·설명·분석 없이 형식만 출력한다.\n\n"
        f"형식:\n"
        f"1. [제목]\n[링크]\n\n"
        f"2. [제목]\n[링크]\n\n"
        f"3. [제목]\n[링크]\n\n"
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
        except Exception as e:
            if attempt < 2:
                print(f"Claude API 오류 ({type(e).__name__}), 30초 후 재시도...")
                time.sleep(30)
            else:
                raise

    result_parts = [block.text for block in message.content if hasattr(block, "text")]
    raw = "\n".join(result_parts).strip()
    clean = re.sub(r"[*_`\[\]()~>+|{}!]", "", raw)
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

    # 4096자 초과 시 분할 전송
    chunks = []
    while full_message:
        if len(full_message) <= 4096:
            chunks.append(full_message)
            break
        split_at = full_message.rfind("\n", 0, 4096)
        if split_at == -1:
            split_at = 4096
        chunks.append(full_message[:split_at])
        full_message = full_message[split_at:].lstrip("\n")

    for chunk in chunks:
        resp = requests.post(
            f"https://api.telegram.org/bot{bot_token}/sendMessage",
            json={"chat_id": chat_id, "text": chunk, "disable_web_page_preview": False},
            timeout=10,
        )
        if resp.status_code != 200:
            print(f"텔레그램 발송 실패: {resp.status_code} {resp.text}", file=sys.stderr)
            sys.exit(1)
    print(f"텔레그램 발송 완료 → chat_id: {chat_id} ({len(chunks)}개 메시지)")


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
    if len(text) < 20:
        return False
    if "http" not in text:
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
    try:
        _run(slot)
    except Exception as e:
        import traceback
        err = traceback.format_exc()
        print(err, file=sys.stderr)
        _send_debug(f"[SLOT {slot}] 예외 발생\n{type(e).__name__}: {e}\n\n{err[:500]}", slot)
        sys.exit(1)


def _run(slot: int):

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
