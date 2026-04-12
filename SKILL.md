---
name: mywant-smartgolf-book-plugin
description: 北新宿・中野新橋・新中野スマートゴルフの指定部屋・日付・時間帯の予約確認画面まで進める。最終確認ボタン（Confirm Reservation）は押さずに停止する。予約の最終確認前の状態確認に使用する。
compatibility:
  python: ">=3.10"
  requires:
    - playwright (sync_api)
    - Chrome with remote debugging on port 9222
metadata:
  output-format: json
  json-schema: see "出力JSON形式" section below
---

## 使い方

```bash
python3 "${CLAUDE_SKILL_DIR}/main.py" '<JSON>'
```

JSON引数（またはstdinで渡す）:

```bash
python3 "${CLAUDE_SKILL_DIR}/main.py" '{"room": "中野新橋店/打席予約(Room02)", "date": "2026-04-12", "time": "20:00"}'
```

### パラメータ

| フィールド | 型 | 必須 | 説明 |
|---|---|---|---|
| `room` | string | ✓ | 部屋名（例: "中野新橋店/打席予約(Room02)"） |
| `date` | string | ✓ | 日付（YYYY-MM-DD形式） |
| `time` | string | ✓ | 時刻（HH:MM形式、JST） |

## 出力JSON形式

```json
{
  "status": "ready_to_confirm",
  "room": "中野新橋店/打席予約(Room02)",
  "date": "2026-04-12",
  "time": "20:00",
  "confirmation": {
    "reservation_datetime": "2026-04-12 20:00",
    "service": "中野新橋店",
    "payment": "クレジットカード"
  }
}
```

### フィールド説明

| フィールド | 型 | 説明 |
|---|---|---|
| `status` | string | 常に `"ready_to_confirm"`（確認画面到達時） |
| `room` | string | 予約しようとした部屋名 |
| `date` | string | 予約日付 |
| `time` | string | 予約時刻 |
| `confirmation` | object | 確認画面から取得した予約詳細 |
| `confirmation.reservation_datetime` | string | 予約日時テキスト |
| `confirmation.service` | string | 店舗名 |
| `confirmation.payment` | string | 支払い方法 |

### エラー時

```json
{ "error": "Time slot not found: 2026-04-12 20:00 (UTC: 2026-04-12T11:00:00.000Z)" }
```
