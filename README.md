# @hee_lhm X 계정 운영 — Claude Code 슬롯 시스템

## 파일 구조
```
hee_lhm/
├── skills/
│   ├── core.md        ← 공통 (계정정책·문체·블랙리스트 절차)
│   ├── slot1.md       ← SLOT 1 전용 (조간)
│   ├── slot2.md       ← SLOT 2 전용 (정부브리핑)
│   ├── slot3-4.md     ← SLOT 3·4 공용 (커뮤니티)
│   └── slot5-6.md     ← SLOT 5·6 공용 (유튜브·비주류)
├── history/
│   └── history.json   ← 소재 이력 (7일 보존)
├── run_slot.sh        ← 슬롯 실행기
├── update_history.py  ← 이력 관리
└── README.md
```

## 슬롯 실행
```bash
chmod +x run_slot.sh
./run_slot.sh 1   # 07:00 조간
./run_slot.sh 2   # 09:30 정부브리핑
./run_slot.sh 3   # 12:00 커뮤니티
./run_slot.sh 4   # 15:00 커뮤니티 심화
./run_slot.sh 5   # 17:30 유튜브+비주류
./run_slot.sh 6   # 19:00 유튜브 클립
```

## 소재 이력 관리
```bash
# 오늘 사용한 소재 추가
python3 update_history.py add "소재키워드1" "소재키워드2"

# 만료 항목 정리
python3 update_history.py clean

# 전체 이력 조회
python3 update_history.py list
```

## 슬롯 실행 흐름
```
run_slot.sh N
  └── core.md + slotN.md 조립 (system prompt)
  └── history.json 유효 이력 추출 → 블랙리스트 주입
  └── claude --system-prompt "조립된 프롬프트" 실행
```
