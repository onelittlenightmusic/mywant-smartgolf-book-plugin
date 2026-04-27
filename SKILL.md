---
name: mywant-smartgolf-book-plugin
description: |
  北新宿・中野新橋・新中野スマートゴルフの指定部屋・日付・時間帯の予約確認画面まで進める。
  最終確認ボタン（Confirm Reservation）は押さずに停止する。

compatibility:
  python: ">=3.10"
  requires:
    - playwright (sync_api)
    - Chrome with remote debugging on port 9222

metadata:
  type-name: smartgolf_book
  category: smartgolf
  final-result-field: summary
---

## 実行特性

| 項目 | 値 | 説明 |
|---|---|---|
| 実行モデル | `foreground` | トリガーされて1回実行し完了する |

## パラメータ

| フィールド | 型 | 必須 | デフォルト | 説明 |
|---|---|---|---|---|
| `room` | string | ✓ | — | 部屋名（例: 中野新橋店/打席予約(Room02)） |
| `date` | string | ✓ | — | 日付（YYYY-MM-DD形式、JST） |
| `time` | string | — | (グローバルパラメータ from: time_global_param) | 時刻（HH:MM形式、JST） |
| `time_global_param` | string | — | `selected_slot` | time のデフォルト参照先となるグローバルパラメータキー |

## 出力フィールド

| フィールド名 | 型 | JSONパス | 永続化 | 説明 |
|---|---|---|---|---|
| `reservation_datetime` | string | `confirmation.reservation_datetime` | true | 予約日時テキスト |
| `service`              | string | `confirmation.service`              | true | 店舗名 |
| `payment`              | string | `confirmation.payment`              | true | 支払い方法 |

## 使用例

### 基本: 日時指定で予約確認画面へ

```bash
python3 "${CLAUDE_SKILL_DIR}/main.py" '{"room": "中野新橋店/打席予約(Room02)", "date": "2026-04-13", "time": "20:00"}'
```

出力:

```json
{
  "status": "ready_to_confirm",
  "room": "中野新橋店/打席予約(Room02)",
  "date": "2026-04-13",
  "time": "20:00",
  "confirmation": {
    "reservation_datetime": "2026-04-13 20:00",
    "service": "中野新橋店",
    "payment": "クレジットカード"
  }
}
```

## エラー

```json
{ "error": "Time slot not found: 2026-04-12 20:00 (UTC: 2026-04-12T11:00:00.000Z)" }
```
