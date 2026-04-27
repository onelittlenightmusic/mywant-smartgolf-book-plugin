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
    time_info = booking.get("time", {})
    time_str = time_info.get("time", "") if isinstance(time_info, dict) else str(time_info)

    if not room_name or not date_str or not time_str:
        error_out("Missing required fields: room, date, time.time")

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

            # 予約ページへ遷移
            report_progress(15, f"Navigating to booking page: {room_name}")
            page.goto(url, wait_until="domcontentloaded")
            time.sleep(3)

            # 部屋を選択
            report_progress(30, "Selecting room")
            select_btn = page.query_selector('[class*="CourseSelectModal"]')
            if not select_btn:
                error_out("Service select button not found")

            page.evaluate('btn => btn.click()', select_btn)
            time.sleep(1)

            modal = page.query_selector('[class*="RSModal_content"]')
            if not modal:
                error_out("Service selection modal not found")

            radio_inputs = modal.query_selector_all('input[type="radio"]')
            target_radio = None
            for inp in radio_inputs:
                label = inp.evaluate_handle('el => el.closest("label")')
                bold = label.query_selector('.font-bold')
                name = bold.inner_text().strip() if bold else ""
                if name == room_name:
                    target_radio = inp
                    break

            if not target_radio:
                error_out(f"Room not found in modal: {room_name}")

            page.evaluate('inp => inp.closest("label").click()', target_radio)
            time.sleep(0.3)
            page.evaluate('btn => btn.click()', modal.query_selector('button:has-text("OK")'))
            time.sleep(2)

            # 時間スロットを React onChange で選択
            report_progress(55, f"Selecting time slot: {date_str} {time_str}")
            target_inp = page.query_selector(f'input[value="{utc_val}"]')
            if not target_inp:
                error_out(f"Time slot not found: {date_str} {time_str} (UTC: {utc_val})")

            page.evaluate('''inp => {
                const pk = Object.keys(inp).find(k => k.startsWith("__reactProps"));
                if (pk) inp[pk].onChange({ target: inp, currentTarget: inp });
            }''', target_inp)
            time.sleep(0.5)

            # Next ボタンが有効になっているか確認
            next_btn = page.query_selector('button.jsx-144b82315487c652')
            if not next_btn or next_btn.is_disabled():
                error_out("Next button is still disabled after time slot selection")

            page.evaluate('btn => btn.click()', next_btn)
            time.sleep(2)

            # 確認画面のテキストを取得（予約ボタンは押さない）
            report_progress(80, "Reading confirmation screen")
            confirmation = {}
            lines = [l.strip() for l in page.inner_text('body').split('\n') if l.strip()]

            for i, line in enumerate(lines):
                if "Reservation date and time" in line and i + 1 < len(lines):
                    confirmation["reservation_datetime"] = lines[i + 1]
                if line == "service" and i + 1 < len(lines) and "店" in lines[i + 1]:
                    confirmation["service"] = lines[i + 1]
                if "Payment method" in line and i + 1 < len(lines):
                    confirmation["payment"] = lines[i + 1]

            page.close()

            result = {
                "status": "ready_to_confirm",
                "room": room_name,
                "date": date_str,
                "time": time_str,
                "confirmation": confirmation,
            }
            report_progress(100, "Done")
            print(json.dumps(result, ensure_ascii=False), flush=True)

    except SystemExit:
        raise
    except Exception as e:
        error_out(str(e))


if __name__ == "__main__":
    main()
