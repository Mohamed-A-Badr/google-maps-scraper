import csv
import os

import pandas as pd

from data_scraper import Scraper

os.makedirs("cleaned_data", exist_ok=True)
os.makedirs("cleaned_data/final_csv", exist_ok=True)

UNWANTED_CATEGORY = [
    # "أخصائي تخاطب",
    # "أخصائي علم نفس",
    # "أخصائي تغذية",
    "استوديو التصوير الفوتوغرافي",
    "استوديو تصوير فوتوغرافي",
    "النادي الاجتماعي",
    "محل بصريات",
    "محل صور",
    "محل نسخ المستندات",
    "مركز تدريب",
    "مركز تنظيم الأسرة",
    "مركز مؤتمرات",
    "مركز تأمين",
    "جمعية / منظمة",
    "محل طباعة",
    "مدرسة تعليم خاص",
    "مركز الفنون",
    "مركز تسوق",
    "مركز ثقافي",
    "مركز صيانة سيارات",
    "مصوّر",
    "ميكانيكي",
    "مؤسسة تعليمية",
    "ورشة إصلاح سيارات",
    "وكالة إعلانية",
    "وكالة تسويق",
    "مصرف",
    "مصمم رسومات",
    "مصور فوتوغرافي تجاري",
    "مطبعة",
    "معمل صور",
    "مقهى إنترنت",
    "خدمة الكتابة والطباعة",
    "تصليح سيارات",
    "تصوير",
    "خدمة تغيير الزيت",
    "خدمة كهرباء سيارات",
    "سوبرماركت",
    "صالة عرض",
    "صالون تجميل",
    "غرفة لياقة",
    "مبنى سكني",
    "متجر حيوانات أليفة",
    "مجمع سكني",
    "محام عام",
    "معلم/ة تربية خاصة",
    "Massage spa",
    "المركز التعليمي",
    "بنك ادخار",
    "جامعة",
    "حديقة",
    "حمام",
    "خدمة استكشاف الغاز والبترول",
    "خدمة التسويق عبر الإنترنت",
    "خدمة معاملات تجارية بين الشركات",
    "رعاية صحية في المنزل",
    "شركة أتمتة",
    "طابعة رقمية",
    "متجر أجهزة إلكترونية",
    "متجر أحذية",
    "متجر بقالة",
    "متجر للزي الموحد",
    "متجر مستلزمات الغاز",
    "مجمع عمارات",
    "متجر مستلزمات مكتبية",
    "محطة حافلات",
    "مركز المدارس",
    "مسجد",
    "مصنع كيماويات",
    "معرض صغير",
    "مغسلة",
    "مكتبة",
    "مهندس ميكانيكي",
    "مورد سيارات بي إم دبليو",
    "ميكانيكي هياكل السيارات",
    "ورشة إصلاح شاحنات",
    "وكالة تأجير معدات",
    "وكالة تجارة إلكترونية",
    "مقهى إنترنت",
    "ورشة إصلاح سيارات",
    "وكالة تسويق",
    "خدمة تصوير فوتوغرافي",
    "خدمة تغيير الزيت",
    "خدمة ضبط السيارات",
    "خدمة طباعة رقمية",
    "خدمة فقدان الوزن",
    "رياض أطفال",
    "ساحة إقلاع وهبوط طائرات الهليكوبتر",
    "سوبرماركت",
    "شركة إتصالات",
    "صالة رياضة",
    "صالة عرض",
    "غرفة لياقة",
    "فندق منتجع",
    "متجر إطارات",
    "متجر أثاث",
    "متجر أجهزة كمبيوتر",
    "متجر أدوات مكتبية",
    "متجر طعام صحي",
    "متجر الأجهزة المساعدة على السماع",
    "محطة فحص سيارات",
    "محل إصلاح كاميرات",
]


def remove_duplicate(csv_file):
    df = pd.read_csv(csv_file)
    df_cleaned = df.drop_duplicates(subset=["google_map_url"], keep="first")
    df_cleaned.to_csv(
        "cleaned_data/stage_1_no_duplicate.csv", index=False, encoding="utf-8-sig"
    )


def add_governorate_value(csv_file, governorate):
    df = pd.read_csv(csv_file)
    df["governorate"] = governorate
    df.to_csv("cleaned_data/stage_2_governorate.csv", index=False, encoding="utf-8-sig")


def rescrape_none_value_row(csv_file):
    scraper = Scraper()
    df = pd.read_csv(csv_file)

    empty_rows = True
    while empty_rows:
        empty_rows_url = []
        # get the url if the title is N/A or empty
        missing_title = df[
            (df["title"].isna()) | (df["title"] == "N/A") | (df["title"] == "")
        ]
        empty_rows_url = missing_title["google_map_url"].tolist()
        print(f"find {len(empty_rows_url)} empty rows")
        if len(empty_rows_url) == 0:
            empty_rows = False
        # remove the empty rows from the csv file
        df = df[~df["google_map_url"].isin(empty_rows_url)]
        df.to_csv(csv_file, index=False, encoding="utf-8-sig")

        missing_data = (
            scraper.scrape_results(url_list=empty_rows_url) if empty_rows_url else []
        )
        # write the missing data inside my csv_file
        if len(missing_data) > 0:
            with open(csv_file, "a", newline="", encoding="utf-8-sig") as f:
                writer = csv.DictWriter(f, fieldnames=missing_data[0].keys())
                writer.writerows(missing_data)


# remove location that not in governorate
def remove_location_not_in_governorate(csv_file, governorate):
    df = pd.read_csv(csv_file)
    # get the address
    df = df[
        df.apply(
            lambda row: any(
                keyword in str(row["address"])
                for keyword in [governorate, "المعادى", "المعادي", "Cairo"]
            ),
            axis=1,
        )
    ].reset_index(drop=True)
    df.to_csv(
        "cleaned_data/stage_3_location_cleaned.csv", index=False, encoding="utf-8-sig"
    )


# remove unwanted data
def remove_unwanted_data(csv_file):
    df = pd.read_csv(csv_file)
    df = df[~df["category"].isin(UNWANTED_CATEGORY)].reset_index(drop=True)
    df.to_csv(
        "cleaned_data/stage_4_unwanted_data_removed.csv",
        index=False,
        encoding="utf-8-sig",
    )


def clean_phone_number(csv_file, gov_name):
    df = pd.read_csv(csv_file)
    df["phone"] = df["phone"].apply(
        lambda x: x.replace("الهاتف:", "", 1).strip() if isinstance(x, str) else x
    )
    df.to_csv(
        f"cleaned_data/final_csv/{gov_name}_final.csv",
        index=False,
        encoding="utf-8-sig",
    )


if __name__ == "__main__":
    csv_file = "output/places_data_alex.csv"

    remove_duplicate(csv_file)
    print("Duplicated data removed!")

    rescrape_none_value_row("cleaned_data/stage_1_no_duplicate.csv")
    print("None value row rescraped!")

    add_governorate_value("cleaned_data/stage_1_no_duplicate.csv", "الإسكندرية")
    print("Governorate value added!")

    remove_location_not_in_governorate(
        "cleaned_data/stage_2_governorate.csv", "الإسكندرية"
    )
    print("Location not in governorate removed!")

    remove_unwanted_data("cleaned_data/stage_3_location_cleaned.csv")
    print("Unwanted data removed!")

    clean_phone_number("cleaned_data/stage_4_unwanted_data_removed.csv", "cairo")
    print("Phone number cleaned!")
