#!/usr/bin/env python3
"""
run_slot.py - 슬롯 실행 메인 스크립트
GitHub Actions 또는 로컬에서 실행, 결과는 stdout 출력
"""

import argparse
import json
import os
import re
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path

import anthropic
import requests

try:
    import feedparser
    FEEDPARSER_AVAILABLE = True
except Exception:
    FEEDPARSER_AVAILABLE = False

try:
    from bs4 import BeautifulSoup
    BS4_AVAILABLE = True
except ImportError:
    BS4_AVAILABLE = False

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
    "mbc":   "https://imnews.imbc.com/rss/news/news_00.xml",
    "ytn":   "https://www.ytn.co.kr/_ln/rss/0101.xml",
    "jtbc":  "https://news.jtbc.co.kr/rss/politics.xml",
    "kbs":   "https://news.kbs.co.kr/rss/rss.do?scd=politics",
    "sbs":   "https://news.sbs.co.kr/news/SectionRssFeed.do?sectionType=02",
    # 통신사
    "yonhap":    "https://www.yonhapnewstv.co.kr/browse/feed/",
    "nocutnews": "https://www.nocutnews.co.kr/rss/S1N0.xml",
    # 커뮤니티 RSS
    "clien_rss": "https://www.clien.net/service/rss",
    # 커뮤니티 반응 (Google News)
    "community":     "https://news.google.com/rss/search?q=이재명+OR+윤석열+OR+국힘+OR+민주당+누리꾼+OR+커뮤니티+OR+반응&hl=ko&gl=KR&ceid=KR:ko",
    "community_hot": "https://news.google.com/rss/search?q=이재명+OR+국힘+OR+윤석열+화제+OR+논란+OR+분노+OR+비판&hl=ko&gl=KR&ceid=KR:ko",
    "community_fem": "https://news.google.com/rss/search?q=온라인+반응+OR+여론+OR+지지층+이재명+OR+국힘+OR+윤석열&hl=ko&gl=KR&ceid=KR:ko",
    # 국무회의
    "cabinet": "https://news.google.com/rss/search?q=국무회의&hl=ko&gl=KR&ceid=KR:ko",
    # 슬롯6: 유튜브 채널 언급 뉴스
    "youtube_politics": "https://news.google.com/rss/search?q=매불쇼+OR+뉴스하이킥+OR+뉴스타파+OR+장르만여의도+OR+시방쇼+OR+알릴레오+OR+이동형TV+OR+오마이TV&hl=ko&gl=KR&ceid=KR:ko",
    "youtube_media":    "https://news.google.com/rss/search?q=MBC뉴스+유튜브+OR+JTBC+유튜브+OR+시사IN+유튜브+OR+KBS뉴스+유튜브+OR+SBS뉴스+유튜브+OR+한겨레TV&hl=ko&gl=KR&ceid=KR:ko",
    "youtube_viral":    "https://news.google.com/rss/search?q=정치+유튜브+클립+OR+유튜브+화제+OR+유튜브+조회수+OR+정치+유튜브+바이럴&hl=ko&gl=KR&ceid=KR:ko",
}

RSS_FALLBACK = {
    "politics":      "https://news.google.com/rss/search?q=한국+정치&hl=ko&gl=KR&ceid=KR:ko",
    "economy":       "https://news.google.com/rss/search?q=한국+경제&hl=ko&gl=KR&ceid=KR:ko",
    "ohmynews":      "https://news.google.com/rss/search?q=오마이뉴스+정치&hl=ko&gl=KR&ceid=KR:ko",
    "hani":          "https://news.google.com/rss/search?q=한겨레+정치&hl=ko&gl=KR&ceid=KR:ko",
    "kyunghyang":    "https://news.google.com/rss/search?q=경향신문+정치&hl=ko&gl=KR&ceid=KR:ko",
    "newstapa":      "https://news.google.com/rss/search?q=뉴스타파&hl=ko&gl=KR&ceid=KR:ko",
    "pressian":      "https://news.google.com/rss/search?q=프레시안+정치&hl=ko&gl=KR&ceid=KR:ko",
    "mbc":           "https://news.google.com/rss/search?q=MBC+뉴스+정치&hl=ko&gl=KR&ceid=KR:ko",
    "ytn":           "https://news.google.com/rss/search?q=YTN+속보+정치&hl=ko&gl=KR&ceid=KR:ko",
    "jtbc":          "https://news.google.com/rss/search?q=JTBC+뉴스+정치&hl=ko&gl=KR&ceid=KR:ko",
    "kbs":           "https://news.google.com/rss/search?q=KBS+뉴스+정치&hl=ko&gl=KR&ceid=KR:ko",
    "sbs":           "https://news.google.com/rss/search?q=SBS+뉴스+정치&hl=ko&gl=KR&ceid=KR:ko",
    "yonhap":        "https://news.google.com/rss/search?q=연합뉴스+정치&hl=ko&gl=KR&ceid=KR:ko",
    "nocutnews":     "https://news.google.com/rss/search?q=노컷뉴스+정치&hl=ko&gl=KR&ceid=KR:ko",
    "clien_rss":     "https://news.google.com/rss/search?q=클리앙+정치+이슈&hl=ko&gl=KR&ceid=KR:ko",
    "community":     "https://news.google.com/rss/search?q=이재명+OR+윤석열+OR+국힘+누리꾼+OR+커뮤니티&hl=ko&gl=KR&ceid=KR:ko",
    "community_hot": "https://news.google.com/rss/search?q=이재명+OR+국힘+화제+OR+논란&hl=ko&gl=KR&ceid=KR:ko",
    "community_fem": "https://news.google.com/rss/search?q=온라인+반응+이재명+OR+국힘&hl=ko&gl=KR&ceid=KR:ko",
    "youtube_politics": "https://news.google.com/rss/search?q=매불쇼+OR+뉴스하이킥+OR+뉴스타파+OR+알릴레오+OR+이동형TV&hl=ko&gl=KR&ceid=KR:ko",
    "youtube_media":    "https://news.google.com/rss/search?q=MBC뉴스+유튜브+OR+JTBC+유튜브+OR+KBS뉴스+유튜브&hl=ko&gl=KR&ceid=KR:ko",
    "youtube_viral":    "https://news.google.com/rss/search?q=정치+유튜브+화제+OR+유튜브+바이럴+정치&hl=ko&gl=KR&ceid=KR:ko",
}

SLOT_RSS_MAP = {
    1: ["ohmynews", "hani", "mbc", "ytn", "kbs", "nocutnews"],
    2: ["politics", "economy", "kyunghyang", "cabinet", "yonhap", "sbs"],
    3: ["community", "community_hot", "clien_rss", "ohmynews", "pressian"],
    4: ["community", "community_hot", "community_fem", "hani", "kyunghyang"],
    5: ["ytn", "mbc", "jtbc", "sbs", "community", "community_hot"],
    6: ["youtube_politics", "youtube_media", "youtube_viral", "newstapa"],
}

# Naver News API 슬롯별 검색 쿼리 (NAVER_CLIENT_ID 설정 시 사용)
SLOT_NAVER_QUERIES = {
    1: ["이재명 민주당", "윤석열 국힘 정치"],
    2: ["국무회의 오늘", "정부 브리핑 발표"],
    3: ["커뮤니티 반응 이재명", "온라인 반응 국힘 논란"],
    4: ["이재명 여론 지지율", "국힘 논란 이슈"],
    5: ["이재명 속보", "국힘 속보 윤석열"],
    6: ["정치 유튜브 화제", "매불쇼 뉴스하이킥 정치"],
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
        match = re.search(
            r'<a[^>]+href="(https?://(?!(?:www\.)?news\.google\.com)[^"]+)"',
            resp.text,
        )
        if match:
            return match.group(1)
        return final
    except Exception:
        return url


def search_naver_news(query: str, display: int = 30) -> list[dict]:
    """Naver News Search API 호출. NAVER_CLIENT_ID 없으면 빈 리스트."""
    client_id = os.environ.get("NAVER_CLIENT_ID")
    client_secret = os.environ.get("NAVER_CLIENT_SECRET")
    if not client_id or not client_secret:
        return []
    try:
        resp = requests.get(
            "https://openapi.naver.com/v1/search/news.json",
            headers={"X-Naver-Client-Id": client_id, "X-Naver-Client-Secret": client_secret},
            params={"query": query, "display": display, "sort": "date"},
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json().get("items", [])
    except Exception as e:
        print(f"Naver API 오류 [{query}]: {e}")
        return []


def scrape_clien_board(board: str = "park", count: int = 25) -> list[tuple[datetime, str]]:
    """클리앙 게시판 직접 스크래핑. BS4 없으면 빈 리스트."""
    if not BS4_AVAILABLE:
        return []
    url = f"https://www.clien.net/service/board/{board}"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(resp.text, "html.parser")
        results = []
        for item in soup.select("a.list_subject")[:count]:
            title = item.get_text(strip=True)
            href = item.get("href", "")
            if not title or not href:
                continue
            link = "https://www.clien.net" + href if href.startswith("/") else href
            results.append((datetime.now(KST), f"제목: [클리앙 파크] {title}\n요약: \n링크: {link}"))
        print(f"클리앙 {board} 스크래핑: {len(results)}개")
        return results
    except Exception as e:
        print(f"클리앙 스크래핑 실패 [{board}]: {e}")
        return []


SLOT_MAX_HOURS = {
    1: 12, 2: 12, 3: 24, 4: 24, 5: 24, 6: 48,
}


def _parse_pub_date(pub_str: str):
    """날짜 문자열 → KST datetime 변환 (RFC2822 / ISO8601)."""
    if not pub_str:
        return None
    try:
        from email.utils import parsedate_to_datetime
        return parsedate_to_datetime(pub_str.strip()).astimezone(KST)
    except Exception:
        pass
    for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            dt = datetime.strptime(pub_str.strip()[:19], fmt)
            return dt.replace(tzinfo=timezone.utc).astimezone(KST)
        except Exception:
            pass
    return None


def _parse_rss_xml(xml_text: str) -> list[dict]:
    """RSS 2.0 / Atom XML → 항목 리스트. feedparser 없을 때 사용."""
    xml_text = re.sub(r"&(?!amp;|lt;|gt;|quot;|apos;|#\w+;)", "&amp;", xml_text)
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []

    ATOM = "http://www.w3.org/2005/Atom"
    entries = []

    # RSS 2.0
    for item in root.findall(".//item"):
        title = (item.findtext("title") or "").strip()
        link_el = item.find("link")
        link = ""
        if link_el is not None:
            link = (link_el.text or "").strip()
            if not link and link_el.tail:
                link = link_el.tail.strip()
        pub_str = (item.findtext("pubDate") or "").strip()
        summary = re.sub(r"<[^>]+>", "", item.findtext("description") or "")[:200].strip()
        entries.append({"title": title, "link": link, "pub_str": pub_str, "summary": summary})

    if entries:
        return entries

    # Atom
    for item in (root.findall(f"{{{ATOM}}}entry") or root.findall("entry")):
        title_el = item.find(f"{{{ATOM}}}title") or item.find("title")
        title = (title_el.text or "").strip() if title_el is not None else ""
        link_el = item.find(f"{{{ATOM}}}link") or item.find("link")
        link = ""
        if link_el is not None:
            link = link_el.get("href", link_el.text or "").strip()
        pub_el = (item.find(f"{{{ATOM}}}published") or item.find("published")
                  or item.find(f"{{{ATOM}}}updated") or item.find("updated"))
        pub_str = (pub_el.text or "").strip() if pub_el is not None else ""
        sum_el = item.find(f"{{{ATOM}}}summary") or item.find("summary")
        summary = re.sub(r"<[^>]+>", "", sum_el.text or "")[:200].strip() if sum_el is not None else ""
        entries.append({"title": title, "link": link, "pub_str": pub_str, "summary": summary})

    return entries


def _parse_feed(xml_text: str) -> list[dict]:
    """feedparser 있으면 사용, 없으면 XML 직접 파싱."""
    import calendar
    if FEEDPARSER_AVAILABLE:
        feed = feedparser.parse(xml_text)
        result = []
        for e in feed.entries:
            pub = e.get("published_parsed") or e.get("updated_parsed")
            pub_dt = datetime.fromtimestamp(calendar.timegm(pub), tz=KST) if pub else None
            result.append({
                "title": e.get("title", "").strip(),
                "link": e.get("link", "").strip(),
                "pub_dt": pub_dt,
                "summary": re.sub(r"<[^>]+>", "", e.get("summary", ""))[:200].strip(),
            })
        return result
    else:
        result = []
        for e in _parse_rss_xml(xml_text):
            result.append({
                "title": e["title"],
                "link": e["link"],
                "pub_dt": _parse_pub_date(e["pub_str"]),
                "summary": e["summary"],
            })
        return result


def fetch_rss_articles(slot: int, max_articles: int = 30) -> str:
    feed_keys = SLOT_RSS_MAP[slot]
    max_hours = SLOT_MAX_HOURS[slot]
    now = datetime.now(KST)
    cutoff = now - timedelta(hours=max_hours)
    wide_cutoff = now - timedelta(days=7)
    articles: list[tuple[datetime, str]] = []

    for key in feed_keys:
        primary = RSS_FEEDS.get(key, "")
        fallback = RSS_FALLBACK.get(key, "")
        urls = [(u, label) for u, label in [(primary, "Primary"), (fallback, "Fallback")] if u]
        for url, source in urls:
            try:
                resp = requests.get(url, headers=HEADERS, timeout=10)
                resp.raise_for_status()
                parsed = _parse_feed(resp.text)
                count = len(parsed)
                print(f"RSS [{key}] {source}: {count}개 항목 수신")
                if count == 0:
                    continue
                batch: list[tuple[datetime, str]] = []
                for entry in parsed[:40]:
                    title = entry["title"]
                    link = resolve_url(entry["link"])
                    if not title or not link:
                        continue
                    pub_dt = entry["pub_dt"]
                    if pub_dt is None or pub_dt < cutoff:
                        continue
                    summary = entry["summary"]
                    batch.append((pub_dt, f"제목: {title}\n요약: {summary}\n링크: {link}"))
                if not batch:
                    print(f"  → 날짜 필터 후 0건, 7일 이내로 완화 재수집")
                    for entry in parsed[:20]:
                        title = entry["title"]
                        link = resolve_url(entry["link"])
                        if not title or not link:
                            continue
                        pub_dt = entry["pub_dt"]
                        if pub_dt is None or pub_dt < wide_cutoff:
                            continue
                        summary = entry["summary"]
                        batch.append((pub_dt, f"제목: {title}\n요약: {summary}\n링크: {link}"))
                print(f"  → 최종: {len(batch)}개")
                articles.extend(batch)
                if batch:
                    break
            except Exception as e:
                print(f"RSS 파싱 실패 [{key}] {source}: {e}")

    naver_queries = SLOT_NAVER_QUERIES.get(slot, [])
    for query in naver_queries:
        items = search_naver_news(query, display=30)
        if items:
            print(f"Naver API [{query}]: {len(items)}개")
        for item in items:
            title = re.sub(r"<[^>]+>", "", item.get("title", "")).strip()
            link = item.get("link") or item.get("originallink", "")
            desc = re.sub(r"<[^>]+>", "", item.get("description", ""))[:200].strip()
            pub_dt = _parse_pub_date(item.get("pubDate", ""))
            if pub_dt is None:
                pub_dt = datetime.now(KST)
            if pub_dt < cutoff:
                continue
            if title and link:
                articles.append((pub_dt, f"제목: {title}\n요약: {desc}\n링크: {link}"))

    if slot in (3, 4):
        articles.extend(scrape_clien_board("park", count=25))

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
        f"아래 기사 목록에서 최대 5개를 골라 아래 형식으로만 출력하라.\n"
        f"포지셔닝(이재명 지지·국힘 비판) 기준으로 가장 임팩트 있는 소재를 우선 선택한다.\n"
        f"조건과 맞지 않아도 목록에서 반드시 선택한다. 거절·설명·분석 없이 형식만 출력한다.\n\n"
        f"- 언론사 기사: 출처명만\n"
        f"- 커뮤니티 이슈: 게시판명 | 게시글 제목 | 키워드\n"
        f"- 유튜브 이슈: 채널명 | 영상 제목 | 키워드 | 인물명\n\n"
        f"형식:\n"
        f"1. [제목]\n[출처]\n\n"
        f"2. [제목]\n[출처]\n\n"
        f"3. [제목]\n[출처]\n\n"
        f"4. [제목]\n[출처]\n\n"
        f"5. [제목]\n[출처]\n\n"
        f"--- 기사 목록 ---\n{articles}"
    )

    for attempt in range(3):
        try:
            message = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=1000,
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


def print_result(text: str, slot: int):
    today = today_kst()
    print("\n" + "=" * 60)
    print(f"📋 {SLOT_LABEL[slot]}")
    print(f"🗓 {today}")
    print("=" * 60)
    print(text)
    print("=" * 60)


def extract_keywords(result_text: str) -> list:
    keywords = []
    for line in result_text.split("\n"):
        line = line.strip().lstrip("-").strip()
        if len(line) > 4 and not line.startswith("http"):
            keywords.append(line[:20].replace(" ", ""))
        if len(keywords) >= 7:
            break
    return keywords


NO_CONTENT_MARKERS = [
    "소재 없음", "채택 불가", "접근 불가", "데이터 부재", "결과 없음",
    "기사 없음", "없음", "불가", "모의 실행", "확인 불가", "찾을 수 없",
]


def is_valid_result(text: str) -> bool:
    if len(text) < 20:
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
        print(traceback.format_exc(), file=sys.stderr)
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
        print(f"[SLOT {slot}] RSS 기사 0건 — 수집 실패")
        sys.exit(0)

    system_prompt = build_system_prompt(slot, blacklist)
    print(f"프롬프트: {len(system_prompt)}자")

    print("Claude API 호출 중 (포맷팅)...")
    result = call_claude(system_prompt, slot, articles)
    print(f"결과: {len(result)}자")

    if not is_valid_result(result):
        print(f"유효한 소재 없음 (길이: {len(result)}자)")
        print(f"=== SLOT {slot} 완료 (출력 없음) ===")
        sys.exit(0)

    print_result(result, slot)

    keywords = extract_keywords(result)
    if keywords:
        history_data = add_to_history(history_data, keywords)
        save_history(history_data)
        print(f"이력 추가: {keywords}")

    print(f"=== SLOT {slot} 완료 ===")


if __name__ == "__main__":
    main()
