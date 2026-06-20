import json
import sys
import time
from datetime import datetime, timezone, timedelta
try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print(json.dumps({
        "error": "playwright module not found. Install with: pip3 install playwright && playwright install chromium"
    }, ensure_ascii=False))
    sys.exit(1)

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


def find_section_next_button(page):
    """Find the section-progression Next button (not 'Next week' or 'Previous week')."""
    return page.evaluate("""() => {
        const btns = document.querySelectorAll('button');
        for (const btn of btns) {
            if (btn.innerText.trim() === 'Next' && !btn.disabled) return true;
        }
        return false;
    }""")


def click_section_next_button(page):
    """Click the section-progression Next button."""
    page.evaluate("""() => {
        const btns = document.querySelectorAll('button');
        for (const btn of btns) {
            if (btn.innerText.trim() === 'Next' && !btn.disabled) {
                btn.click();
                return;
            }
        }
    }""")


def select_room(page, room_name):
    """Select room by clicking the LI containing the room name label.
    The click triggers the XState INPUT_COURSE_CANONICAL_ID event internally.
    """
    # Click the LI that contains a label with the room name
    xpath = f"//li[.//label[contains(., '{room_name}')]]"
    room_li = page.query_selector(f"xpath={xpath}")
    if not room_li:
        return False
    room_li.click()
    return True


def select_time_slot(page, utc_val):
    """Find the time slot radio input and trigger its React onChange handler.
    Navigates forward through weeks to find the target date/time.
    Returns True if found and selected.
    """
    # Try current week first, then advance up to 8 weeks
    for week in range(9):
        target_inp = page.query_selector(f'input[value="{utc_val}"]')
        if target_inp:
            if target_inp.is_disabled():
                return False  # Time slot exists but unavailable
            # Trigger the XState INPUT_DATE_TIME event via React onChange
            page.evaluate("""inp => {
                const pk = Object.keys(inp).find(k => k.startsWith('__reactProps'));
                if (pk && inp[pk].onChange) {
                    inp[pk].onChange({ target: inp, currentTarget: inp });
                }
            }""", target_inp)
            return True

        if week < 8:
            # Advance to next week
            next_week_btn = page.query_selector('button:has-text("Next week")')
            if not next_week_btn:
                break
            next_week_btn.evaluate("b => b.click()")
            time.sleep(1.5)

    return False


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

    try:
        with sync_playwright() as p:
            report_progress(5, "Connecting to browser")
            browser = p.chromium.connect_over_cdp("http://localhost:9222")
            context = browser.contexts[0]
            page = context.new_page()
            page.set_viewport_size({"width": 390, "height": 844})

            # 予約ページへ遷移
            report_progress(15, f"Navigating to booking page: {room_name}")
            page.goto(url, wait_until="domcontentloaded")
            time.sleep(3)

            # 部屋を選択 (XState INPUT_COURSE_CANONICAL_ID event)
            report_progress(30, f"Selecting room: {room_name}")
            if not select_room(page, room_name):
                error_out(f"Room not found on page: {room_name}")

            # 予約情報をロードするまで待機
            time.sleep(2)

            # 時間スロットを選択 (XState INPUT_DATE_TIME event via React onChange)
            report_progress(50, f"Selecting time slot: {date_str} {time_str}")
            if not select_time_slot(page, utc_val):
                error_out(f"Time slot not found or unavailable: {date_str} {time_str} (UTC: {utc_val})")

            # Next ボタンが有効になるまで待機
            time.sleep(1)

            # Next ボタンが有効か確認
            if not find_section_next_button(page):
                error_out("Next button is still disabled after room and time slot selection")

            # Next ボタンをクリック (確認画面へ)
            report_progress(75, "Navigating to confirmation screen")
            click_section_next_button(page)
            time.sleep(3)

            # 確認画面のテキストを取得（予約ボタンは押さない）
            report_progress(90, "Reading confirmation screen")
            body_text = page.inner_text('body')
            confirmation = parse_confirmation(body_text)

            # page.close() は呼ばない — 確認画面をブラウザに残す

            reservation_dt = confirmation.get("reservation_datetime", f"{date_str} {time_str}")
            result = {
                "status": "ready_to_confirm",
                "room": room_name,
                "date": date_str,
                "time": time_str,
                "confirmation": confirmation,
                "summary": f"{room_name} {reservation_dt} - ready to confirm",
            }
            report_progress(100, "Done")
            print(json.dumps(result, ensure_ascii=False), flush=True)

    except SystemExit:
        raise
    except Exception as e:
        error_out(str(e))


if __name__ == "__main__":
    main()
