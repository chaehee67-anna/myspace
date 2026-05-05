#!/bin/bash
# run_slot.sh — @hee_lhm 슬롯 실행기
# 사용법: ./run_slot.sh [1|2|3|4|5|6]
# 예시:   ./run_slot.sh 1

SLOT=$1
BASE_DIR="$(dirname "$0")"
SKILLS_DIR="$BASE_DIR/skills"
HISTORY_FILE="$BASE_DIR/history/history.json"
TODAY=$(TZ="Asia/Seoul" date +"%Y-%m-%d")

if [ -z "$SLOT" ]; then
  echo "슬롯 번호를 입력하세요 (1~6)"
  exit 1
fi

# 슬롯별 스킬 파일 매핑
case $SLOT in
  1) SLOT_FILE="$SKILLS_DIR/slot1.md" ;;
  2) SLOT_FILE="$SKILLS_DIR/slot2.md" ;;
  3|4) SLOT_FILE="$SKILLS_DIR/slot3-4.md" ;;
  5|6) SLOT_FILE="$SKILLS_DIR/slot5-6.md" ;;
  *) echo "유효하지 않은 슬롯 번호: $SLOT"; exit 1 ;;
esac

# 시스템 프롬프트 조립: core + 해당 슬롯
SYSTEM_PROMPT=$(cat "$SKILLS_DIR/core.md" "$SLOT_FILE")

# 소재 이력 추출 (오늘 + 유효기간 내)
HISTORY_CONTEXT=$(python3 - <<EOF
import json, sys
from datetime import datetime

today = "$TODAY"
with open("$HISTORY_FILE") as f:
    data = json.load(f)

valid = []
for entry in data.get("entries", []):
    if entry["expires"] >= today:
        valid.extend(entry["items"])

if valid:
    print("## 금일 소재 블랙리스트 (사용 금지)")
    for item in valid:
        print(f"- {item}")
else:
    print("## 금일 소재 블랙리스트\n- (없음)")
EOF
)

# 최종 시스템 프롬프트에 이력 추가
FULL_SYSTEM="$SYSTEM_PROMPT

---
$HISTORY_CONTEXT"

# Claude Code 실행
echo "=== SLOT $SLOT 실행 ($(TZ='Asia/Seoul' date '+%Y-%m-%d %H:%M KST')) ==="
echo "로드: core.md + $SLOT_FILE + history.json"
echo ""

claude --system-prompt "$FULL_SYSTEM" \
  --model claude-sonnet-4-20250514 \
  "SLOT $SLOT 리서치를 진행해줘. 오늘 날짜: $TODAY KST"
