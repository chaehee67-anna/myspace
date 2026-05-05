#!/usr/bin/env python3
"""
update_history.py — 소재 이력 추가 및 만료 정리
사용법:
  추가: python3 update_history.py add "소재키워드1" "소재키워드2" ...
  정리: python3 update_history.py clean
  조회: python3 update_history.py list
"""

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
import pytz

KST = pytz.timezone("Asia/Seoul")
HISTORY_FILE = Path(__file__).parent / "history" / "history.json"
RETENTION_DAYS = 7


def load():
    with open(HISTORY_FILE) as f:
        return json.load(f)


def save(data):
    with open(HISTORY_FILE, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def today_kst():
    return datetime.now(KST).strftime("%Y-%m-%d")


def expires(date_str):
    dt = datetime.strptime(date_str, "%Y-%m-%d") + timedelta(days=RETENTION_DAYS)
    return dt.strftime("%Y-%m-%d")


def clean(data):
    today = today_kst()
    before = len(data["entries"])
    data["entries"] = [e for e in data["entries"] if e["expires"] >= today]
    removed = before - len(data["entries"])
    return data, removed


def add(items):
    data = load()
    data, _ = clean(data)
    today = today_kst()

    existing = next((e for e in data["entries"] if e["date"] == today), None)
    if existing:
        new_items = [i for i in items if i not in existing["items"]]
        existing["items"].extend(new_items)
        added = len(new_items)
    else:
        data["entries"].append({
            "date": today,
            "expires": expires(today),
            "items": list(items)
        })
        added = len(items)

    save(data)
    print(f"추가: {added}건 / 날짜: {today} / 만료: {expires(today)}")


def list_items():
    data = load()
    today = today_kst()
    print(f"=== 소재 이력 (기준: {today}) ===")
    for entry in sorted(data["entries"], key=lambda e: e["date"]):
        expired = "만료" if entry["expires"] < today else "유효"
        print(f"\n[{entry['date']} ~ {entry['expires']} | {expired}]")
        for item in entry["items"]:
            print(f"  - {item}")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "list"

    if cmd == "add":
        items = sys.argv[2:]
        if not items:
            print("추가할 소재를 입력하세요")
            sys.exit(1)
        add(items)

    elif cmd == "clean":
        data = load()
        data, removed = clean(data)
        save(data)
        print(f"정리 완료: {removed}건 삭제")

    elif cmd == "list":
        list_items()

    else:
        print(f"알 수 없는 명령: {cmd}")
        sys.exit(1)
