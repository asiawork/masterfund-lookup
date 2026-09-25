import os
import requests
import pandas as pd
import re

# 1. รับ API Key จาก GitHub Secrets
API_KEY = os.getenv("SEC_API_KEY")

if not API_KEY:
    raise ValueError("ไม่พบ SEC_API_KEY กรุณาตั้งค่าใน GitHub Secrets ก่อน")

BASE_URL = "https://api.sec.or.th/v2/fund/general-info/profiles"
HEADERS = {
    "Ocp-Apim-Subscription-Key": API_KEY
}

# 2. วนดึงข้อมูลทุกหน้าด้วย cursor
all_items = []
cursor = None
page_count = 1

print("กำลังเริ่มต้นดึงข้อมูลจาก SEC Open API...")

while True:
    params = {"page_size": "100"}
    if cursor:
        params["next_cursor"] = cursor
        
    response = requests.get(BASE_URL, headers=HEADERS, params=params)
    
    if response.status_code != 200:
        print(f"เกิดข้อผิดพลาดในการดึงข้อมูลหน้า {page_count}: HTTP {response.status_code}")
        break
        
    data = response.json()
    items = data.get("items", [])
    if not items:
        break
        
    all_items.extend(items)
    print(f"ดึงข้อมูลหน้า {page_count} สำเร็จ (สะสม {len(all_items)} รายการ)")
    
    cursor = data.get("next_cursor")
    if not cursor:
        break
        
    page_count += 1

print(f"ดึงข้อมูลดิบทั้งหมดเสร็จสิ้น: รวม {len(all_items)} รายการ")

# แปลงเป็น Pandas DataFrame
df = pd.DataFrame(all_items)

if not df.empty:
    # 3. กรองเฉพาะกองทุนที่ยัง Active (cancel_date ว่าง และสถานะ Registered หรือ IPO)
    if "cancel_date" in df.columns and "fund_status" in df.columns:
        df = df[df["cancel_date"].isna() | (df["cancel_date"].astype(str).str.strip() == "")]
        df = df[df["fund_status"].astype(str).str.strip().isin(["Registered", "IPO"])]
        print(f"หลังกรอง Active Funds (Registered/IPO): เหลือ {len(df)} รายการ")

    # 4. ทำคอลัมน์ Search_Name (ถ้า fund_class_name ว่างหรือเป็น main ให้ใช้ proj_abbr_name)
    def get_search_name(row):
        class_name = str(row.get("fund_class_name", "")).strip()
        if not class_name or class_name.lower() in ["none", "nan", "main", ""]:
            return row.get("proj_abbr_name", "")
        return class_name

    df["Search_Name"] = df.apply(get_search_name, axis=1)

    # 5. เอาเฉพาะ Feeder Fund ที่ลงทุนต่างประเทศ
    if "feederfund_master_fund" in df.columns:
        df = df[df["feederfund_master_fund"].notna()]
        df = df[~df["feederfund_master_fund"].astype(str).str.strip().isin(["", "None", "nan"])]
        
        if "feederfund_country" in df.columns:
            df = df[df["feederfund_country"].astype(str).str.strip() != "ไทย"]
            
        print(f"หลังกรอง Feeder Fund ต่างประเทศ: เหลือ {len(df)} รายการ")

    # 6. คลีนชื่อ Master Fund (ตัดคำนำหน้าภาษาไทย และตัด Class ทุกรูปแบบ)
    def clean_master_fund_name(val):
        if not val or pd.isna(val):
            return ""
        text = str(val).strip()

        # แทนที่ en-dash ด้วย hyphen ปกติ
        text = text.replace("–", "-")

        # ตัดคำนำหน้าภาษาไทย
        prefix_pattern = r"^(ชื่อกองทุน\s*:\s*|กองทุนหลัก\s*:\s*|กองทุนเปิด\s+|กองทุน\s+)"
        text = re.sub(prefix_pattern, "", text, flags=re.IGNORECASE)

        # ตัดข้อความตั้งแต่ Class เป็นต้นไป เช่น (Class...), , Class..., - Class..., Class...
        class_pattern = r"(\s*\(\s*Class.*|,\s*Class.*|-+\s*Class.*|\s+Class.*)"
        text = re.sub(class_pattern, "", text, flags=re.IGNORECASE)

        # เก็บกวาดเครื่องหมายตกค้างหน้า-หลังข้อความ
        text = text.strip(" :-–,()")

        return text.strip()

    df["Master_Fund_Search"] = df["feederfund_master_fund"].apply(clean_master_fund_name)

    # 7. จัดการคอลัมน์และบันทึก
    desired_cols = [
        "unique_id", "comp_name_th", "comp_name_en", "proj_id", "regis_id", 
        , "regis_date", "proj_name_th", "proj_name_en", 
        "proj_abbr_name", "fund_status", "policy_desc", "investment_policy_desc", "management_style", 
        "feederfund_master_fund", "Master_Fund_Search", "exchange_rate_protection_policy", "fund_class_name", "fund_class_detail", 
        "fund_class_description", "fund_class_tax_incentive_type", 
        "fund_class_isin_code", "last_upd_date", "Search_Name"
    ]
    
    final_cols = [col for col in desired_cols if col in df.columns]
    remaining_cols = [col for col in df.columns if col not in final_cols]
    result_df = df[final_cols + remaining_cols]

    # บันทึกเป็น JSON เท่านั้นสำหรับเว็บ
    output_filename = "funds_data.json"
    result_df.to_json(output_filename, orient="records", force_ascii=False)
    print(f"บันทึกไฟล์สำเร็จ: {output_filename} (จำนวน {len(result_df)} รายการ)")

else:
    print("ไม่พบข้อมูลที่จะประมวลผล")
