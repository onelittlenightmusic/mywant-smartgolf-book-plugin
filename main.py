import json
import os
import sys
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.expanduser("~/work/machine-readable-skills-browser"))
from mrs_browser import browser_run, xpath_literal  # noqa: E402

JST = timezone(timedelta(hours=9))

LOCATION_URLS = {
    "北新宿店": "https://smartgolf.stores.jp/reserve/smartgolf_kitashinjuku/3421038/book/course_type",
    "中野新橋店": "https://smartgolf.stores.jp/reserve/smartgolf_nakanoshimbashi/1459178/book/course_type",
    "新中野店": "https://smartgolf.stores.jp/reserve/smartgolf_shinnakano/4619269/book/course_type",
}


def report_progress(percentage, message=""):
    print(json.dumps({"_progress": percentage, "_message": message}, ensure_ascii=False), flush=True)


def error_out(message):
    print(json.dumps({"error": message}, ensure_ascii=False), flush=True)
    sys.exit(1)


def room_to_url(room_name):
    for store, url in LOCATION_URLS.items():
        if room_name.startswith(store):
            return url
    return None


def time_to_utc_value(date_str, time_str):
    """'2026-04-12', '20:00' → '2026-04-12T11:00:00.000Z'"""
    dt_jst = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M").replace(tzinfo=JST)
    dt_utc = dt_jst.astimezone(timezone.utc)
    return dt_utc.strftime("%Y-%m-%dT%H:%M:%S.000Z")


# room_li/next-week/next-section buttons are matched by their own text
# content, not a stable class name (the site has none) — CSS can't express
# that, so these use xpath: (see browser-run-interpreter.ts's resolveSingle).
# The site's UI language depends on login/account state (confirmed while
# debugging: logged out → Japanese, logged in → English) rather than being
# fixed, so both label sets are matched with xpath's `or`. 「予約確認」/
# "Next" only navigates to the confirmation screen — it does NOT finalize
# the reservation (the actual "Confirm Reservation" button on that screen
# is never clicked by this flow).
#
# room_xpath targets the <input> INSIDE the matching <li>, not the <li>
# itself: a programmatic .click() dispatches an event whose target is
# exactly the clicked element, which then only bubbles UP through
# ancestors — it never reaches a handler on a DESCENDANT. Playwright's
# click() instead simulates a real mouse click at the element's on-screen
# center, which in practice lands on whatever's actually rendered there
# (here, the input), so the original CDP-based script's `li.click()`
# worked by accident of coordinates, not because the <li> itself has a
# handler. Clicking the input directly (same pattern already proven by
# smartgolf-list's room-radio clicks) reaches the real handler regardless.
def build_booking_steps(room_name: str, utc_val: str) -> list:
    room_xpath = f"xpath://li[.//label[contains(., {xpath_literal(room_name)})]]//input"
    next_week_xpath = "xpath://button[contains(., 'Next week') or contains(., '次の一週間')]"
    next_section_xpath = (
        "xpath://button[(normalize-space(.)='Next' or normalize-space(.)='予約確認') and not(@disabled)]"
    )
    slot_selector = f'input[value="{utc_val}"]'

    # 予約確定直前の確認画面まで進めたら停止する（元実装同様、確定ボタンは
    # 押さない — ユーザーが目視確認してから手動で確定する想定）。
    confirm_steps = [
        {"type": "customStep", "name": "sleep", "parameters": {"ms": 1000}},
        {"type": "customStep", "name": "if", "parameters": {
            "condition": {"selector_exists": next_section_xpath},
            "then": [
                {"type": "click", "selectors": [[next_section_xpath]]},
                {"type": "customStep", "name": "sleep", "parameters": {"ms": 3000}},
                {"type": "customStep", "name": "read", "parameters": {
                    "selector": "body", "extract": "text", "as": "confirmation_text", "timeout_ms": 5000,
                }},
                {"type": "customStep", "name": "setResult", "parameters": {"key": "status", "value": "ready_to_confirm"}},
            ],
            "else": [
                {"type": "customStep", "name": "setResult", "parameters": {"key": "status", "value": "next_button_disabled"}},
            ],
        }},
    ]

    # 今週になければ最大8回「Next week」を押して探す（元実装のfor week in range(9)と同じ回数）。
    time_slot_steps = [
        {"type": "customStep", "name": "loop", "parameters": {
            "max_iterations": 8,
            "until": {"selector_exists": slot_selector},
            "body": [
                {"type": "click", "selectors": [[next_week_xpath]]},
                {"type": "customStep", "name": "sleep", "parameters": {"ms": 1500}},
            ],
        }},
        {"type": "customStep", "name": "if", "parameters": {
            "condition": {"selector_exists": slot_selector},
            "then": [
                {"type": "customStep", "name": "if", "parameters": {
                    # disabled属性の「値」ではなく「有無」で判定する（値は
                    # フレームワークにより ""/"true"/"disabled" など不定）。
                    "condition": {"selector": slot_selector, "extract": "attr", "attr": "disabled", "exists": True},
                    "then": [
                        {"type": "customStep", "name": "setResult", "parameters": {"key": "status", "value": "time_slot_disabled"}},
                    ],
                    "else": [
                        # XState駆動のUIで、ネイティブchange/inputイベントではなく
                        # Reactのcontrolled onChangeハンドラを直接叩く必要がある。
                        {"type": "customStep", "name": "reactChange", "parameters": {"selector": slot_selector}},
                        *confirm_steps,
                    ],
                }},
            ],
            "else": [
                {"type": "customStep", "name": "setResult", "parameters": {"key": "status", "value": "time_slot_not_found"}},
            ],
        }},
    ]

    return [
        {"type": "customStep", "name": "sleep", "parameters": {"ms": 3000}},
        {"type": "customStep", "name": "if", "parameters": {
            "condition": {"selector_exists": room_xpath},
            "then": [
                # クリックはXState INPUT_COURSE_CANONICAL_IDイベントを内部で発火させる
                {"type": "click", "selectors": [[room_xpath]]},
                # カレンダーAJAXの読み込みを待つ（固定sleepだけだと、time_slot_steps
                # のuntilチェックが未読み込み状態で走り、実際は今週に空きがあるのに
                # 誤って「Next week」を押して通り過ぎてしまう）。
                {"type": "waitForElement", "selectors": [['input[name="dateTimeSelection"]']], "timeout": 15000},
                *time_slot_steps,
            ],
            "else": [
                {"type": "customStep", "name": "setResult", "parameters": {"key": "status", "value": "room_not_found"}},
            ],
        }},
    ]


def parse_confirmation(body_text):
    """Parse the confirmation page text to extract reservation details."""
    lines = [l.strip() for l in body_text.split('\n') if l.strip()]
    confirmation = {}

    for i, line in enumerate(lines):
        if line == "Reservation date and time" and i + 1 < len(lines):
            confirmation["reservation_datetime"] = lines[i + 1]
        if line == "service" and i + 1 < len(lines):
            # Next non-empty line that contains a Japanese store name
            candidate = lines[i + 1]
            if "店" in candidate or "Room" in candidate:
                confirmation["service"] = candidate
        if line == "Payment method" and i + 1 < len(lines):
            confirmation["payment"] = lines[i + 1]

    return confirmation


def main():
    # 引数からJSON入力を読み込む
    if len(sys.argv) > 1:
        try:
            booking = json.loads(sys.argv[1])
        except json.JSONDecodeError as e:
            error_out(f"Invalid JSON input: {e}")
    else:
        try:
            booking = json.load(sys.stdin)
        except json.JSONDecodeError as e:
            error_out(f"Invalid JSON from stdin: {e}")

    room_name = booking.get("room", "")
    date_str = booking.get("date", "")
    # time フィールドは文字列 "20:00" または辞書 {"time": "20:00"} のどちらでも受け付ける
    raw_time = booking.get("time", "")
    if isinstance(raw_time, dict):
        time_str = raw_time.get("time", "")
    else:
        time_str = str(raw_time)

    if not room_name or not date_str or not time_str:
        error_out("Missing required fields: room, date, time")

    url = room_to_url(room_name)
    if not url:
        error_out(f"Unknown store in room name: {room_name}")

    utc_val = time_to_utc_value(date_str, time_str)

    ERROR_MESSAGES = {
        "room_not_found": f"Room not found on page: {room_name}",
        "time_slot_not_found": f"Time slot not found or unavailable: {date_str} {time_str} (UTC: {utc_val})",
        "time_slot_disabled": f"Time slot not found or unavailable: {date_str} {time_str} (UTC: {utc_val})",
        "next_button_disabled": "Next button is still disabled after room and time slot selection",
    }

    try:
        report_progress(15, f"Navigating to booking page: {room_name}")
        # keep_open=True: 確認画面をブラウザに残す（元実装同様、確定ボタンは押さない）。
        # background=False: ユーザーが目視確認できるよう前面に表示する。
        result = browser_run(
            url, build_booking_steps(room_name, utc_val),
            keep_open=True, background=False, timeout_ms=150000,
        )
    except Exception as e:
        error_out(str(e))
        return

    status = result.get("status", "")
    if status in ERROR_MESSAGES:
        error_out(ERROR_MESSAGES[status])
    if status != "ready_to_confirm":
        error_out(f"Unexpected status from browser_run: {status or '(none — flow did not complete)'}")

    report_progress(90, "Reading confirmation screen")
    confirmation = parse_confirmation(result.get("confirmation_text") or "")

    reservation_dt = confirmation.get("reservation_datetime", f"{date_str} {time_str}")
    output = {
        "status": "ready_to_confirm",
        "room": room_name,
        "date": date_str,
        "time": time_str,
        "confirmation": confirmation,
        "summary": f"{room_name} {reservation_dt} - ready to confirm",
    }
    report_progress(100, "Done")
    print(json.dumps(output, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
