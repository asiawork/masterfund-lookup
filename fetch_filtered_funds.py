import csv
import json
import os
import time
from collections import Counter

import requests

# ---------------------------------------------------------------
# ตั้งค่า API ของ ก.ล.ต. (V2)
# ---------------------------------------------------------------
API_KEY = os.environ["SEC_API_KEY"]  # ต้องตรงกับชื่อตัวแปรใน env ของ workflow
URL = "https://api.sec.or.th/v2/fund/general-info/profiles"
HEADERS = {"Ocp-Apim-Subscription-Key": API_KEY}
PAGE_SIZE = 100

# ---------------------------------------------------------------
# เงื่อนไขกรอง — ถ้าผลกรองเป็น 0 ให้ดูค่าจริงใน log แล้วแก้ตรงนี้
# ---------------------------------------------------------------
WANTED_STATUS = {"registered", "ipo"}  # เทียบแบบไม่สนตัวพิมพ์เล็ก/ใหญ่
WANTED_STYLE = {"pm", "pn"}


def find_next_cursor(data):
    """หา next_cursor ในผลลัพธ์ ไม่ว่าจะอยู่ชั้นบนสุดหรือซ้อนอยู่หนึ่งชั้น"""
    if not isinstance(data, dict):
        return None
    if data.get("next_cursor"):
        return data["next_cursor"]
    for value in data.values():
        if isinstance(value, dict) and value.get("next_cursor"):
            return value["next_cursor"]
    return None


def get_with_retry(params, tries=5):
    for attempt in range(tries):
        resp = requests.get(URL, headers=HEADERS, params=params, timeout=60)
        if resp.status_code == 429:  # เรียกถี่เกินไป รอแล้วลองใหม่
            wait = int(resp.headers.get("Retry-After", 5 * (attempt + 1)))
            print(f"ถูกจำกัดความถี่ รอ {wait} วินาที")
            time.sleep(wait)
            continue
        resp.raise_for_status()
        return resp.json()
    raise RuntimeError("เรียก API ไม่สำเร็จหลังลองหลายครั้ง")


def fetch_all_items():
    items, cursor, page = [], None, 1
    while True:
        params = {"page_size": PAGE_SIZE}
        if cursor:
            params["next_cursor"] = cursor
        data = get_with_retry(params)

        page_items = data.get("items", []) if isinstance(data, dict) else data
        items.extend(page_items)
        print(f"หน้า {page}: ได้ {len(page_items)} รายการ (รวม {len(items)})")

        cursor = find_next_cursor(data)
        if not cursor or not page_items:
            break
        page += 1
        time.sleep(0.3)
    return items


def main():
    items = fetch_all_items()
    print(f"ดึงมาทั้งหมด {len(items)} กอง")

    # แสดงค่าที่มีจริงในข้อมูล เพื่อเช็กว่าเงื่อนไขกรองตรงหรือไม่
    print("fund_status ที่พบ:", dict(Counter(str(i.get("fund_status")) for i in items)))
    print("management_style ที่พบ:", dict(Counter(str(i.get("management_style")) for i in items)))

    filtered = [
        i for i in items
        if str(i.get("fund_status", "")).strip().lower() in WANTED_STATUS
        and str(i.get("management_style", "")).strip().lower() in WANTED_STYLE
    ]
    print(f"เหลือหลังกรอง {len(filtered)} กอง")

    with open("filtered_funds.json", "w", encoding="utf-8") as f:
        json.dump(filtered, f, ensure_ascii=False, indent=2)

    columns = sorted({k for row in filtered for k in row.keys()}) or ["proj_id"]
    # utf-8-sig เพื่อให้ Excel เปิดภาษาไทยได้ถูกต้อง
    with open("filtered_funds.csv", "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        for row in filtered:
            writer.writerow({
                k: json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v
                for k, v in row.items()
            })


if __name__ == "__main__":
    main()
