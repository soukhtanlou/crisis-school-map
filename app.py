import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
from shapely.geometry import Polygon, Point
from shapely.ops import unary_union
import requests
import os
import json


st.set_page_config(page_title="ارزیابی خسارت مدارس", layout="wide")
st.title("ارزیابی خسارت مدارس در بحران")


# ===========================
# 1) بارگذاری داده مدارس
# ===========================
@st.cache_data
def load_data():
    """بارگذاری و پاکسازی داده‌ها با اصلاح نام ستون مختصات."""
    try:
        if not os.path.exists("schools.csv"):
            return pd.DataFrame()
            
        df = pd.read_csv("schools.csv", encoding="utf-8-sig")

        df = df.dropna(subset=["عرض_جغرافیایی", "طول_جغرافیایی"])
        
        # 🚨 اصلاح خطای برنامه نویسی: 'عرض_گرافیایی' به 'عرض_جغرافیایی' تغییر کرد
        df["عرض_جغرافیایی"] = pd.to_numeric(df["عرض_جغرافیایی"], errors="coerce") 
        df["طول_جغرافیایی"] = pd.to_numeric(df["طول_جغرافیایی"], errors="coerce")
        
        df["تعداد_دانش_آموز"] = pd.to_numeric(df["تعداد_دانش_آموز"], errors="coerce").fillna(0).astype(int)
        df["تعداد_معلم"] = pd.to_numeric(df["تعداد_معلم"], errors="coerce").fillna(0).astype(int)
        df = df.dropna(subset=["عرض_جغرافیایی", "طول_جغرافیایی"]) # حذف نهایی سطر‌های فاقد مختصات معتبر

        def categorize_grade(grade):
            if "دبستان" in grade or "پیش دبستانی" in grade:
                return "ابتدایی/دبستان"
            elif "متوسطه" in grade:
                return "متوسطه"
            elif "فنی و حرفه‌ای" in grade:
                return "فنی و حرفه‌ای"
            elif "مراکز" in grade:
                return "مراکز/سایر"
            else:
                return "نامشخص"

        df["دسته_مقطع"] = df["مقطع_تحصیلی"].apply(categorize_grade)
        return df
    except Exception as e:
        st.error(f"خطا در خواندن فایل: {e}")
        return pd.DataFrame()


if not os.path.exists("schools.csv"):
    st.error("فایل schools.csv پیدا نشد!")
    st.stop()

df = load_data()
if df.empty:
    st.warning("هیچ داده معتبری در فایل نیست.")
    st.stop()

st.info(f"تعداد مدارس دارای مختصات معتبر: **{len(df)}**")


# ===========================
# 2) Sidebar فیلتر‌ها + انتخاب نوع محدوده آسیب
# ===========================
st.sidebar.header("تنظیمات")

damage_input_method = st.sidebar.radio(
    "روش تعیین محدوده خسارت:",
    ("ترسیم دستی روی نقشه", "آپلود لایه خسارت (GeoJSON)")
)

grade_categories = df["دسته_مقطع"].unique()
selected_categories = st.sidebar.multiselect(
    "فیلتر مقطع:",
    options=grade_categories,
    default=grade_categories
)

genders = df["جنسیت"].unique()
selected_genders = st.sidebar.multiselect(
    "فیلتر جنسیت:",
    options=genders,
    default=genders
)

filtered_df = df[
    df["دسته_مقطع"].isin(selected_categories) &
    df["جنسیت"].isin(selected_genders)
]

if filtered_df.empty:
    st.warning("با فیلترهای اعمال شده، هیچ مدرسه‌ای برای نمایش وجود ندارد.")
    st.stop()


# ===========================
# 3) نقشه
# ===========================
if "initial_map_location" not in st.session_state:
    st.session_state.initial_map_location = [35.6892, 51.3890]
    st.session_state.initial_map_zoom = 11

m = folium.Map(
    location=st.session_state.initial_map_location,
    zoom_start=st.session_state.initial_map_zoom,
    tiles="OpenStreetMap"
)


category_colors = {
    "ابتدایی/دبستان": "#28a745",
    "متوسطه": "#007bff",
    "فنی و حرفه‌ای": "#ffc107",
    "مراکز/سایر": "#dc3545",
    "نامشخص": "#6c757d",
}

category_groups = {}
for category in grade_categories:
    group = folium.FeatureGroup(name=f"دسته: {category}", show=True)
    category_groups[category] = group
    m.add_child(group)


# نقاط مدارس روی نقشه
for _, row in filtered_df.iterrows():
    lat, lon = row["عرض_جغرافیایی"], row["طول_جغرافیایی"]
    category = row["دسته_مقطع"]
    color = category_colors.get(category, "#444")

    tooltip = (
        f"<b>{row['نام_مدرسه']}</b><br>"
        f"مقطع: {row['مقطع_تحصیلی']}<br>"
        f"مدیر: {row['نام_مدیر']}<br>"
        f"دانش‌آموز: {row['تعداد_دانش_آموز']}<br>"
        f"معلم: {row['تعداد_معلم']}<br>"
    )

    folium.CircleMarker(
        location=[lat, lon],
        radius=7,
        color=color, fill=True, fillColor=color,
        tooltip=tooltip,
    ).add_to(category_groups[category])


# ===========================
# 4) اضافه کردن ابزار ترسیم دستی
# ===========================
from folium.plugins import Draw

if damage_input_method == "ترسیم دستی روی نقشه":
    # ابزارهای ترسیم (Polygon فعال) و ویرایش/حذف فعال هستند.
    Draw(
        draw_options={'polyline': False, 'marker': False, 'circlemarker': False, 'circle': False, 'rectangle': False},
        edit_options={'edit': True, 'remove': True},
    ).add_to(m)


# ===========================
# 5) آپلود GeoJSON برای لایه خسارت ماهواره‌ای
# ===========================

damage_polygons = None

if damage_input_method == "آپلود لایه خسارت (GeoJSON)":
    uploaded = st.sidebar.file_uploader("آپلود GeoJSON", type=["geojson"])

    if uploaded:
        try:
            geojson_data = json.load(uploaded)

            # استخراج مختصات پلی‌گون‌ها از GeoJSON
            polygon_features = [
                feature for feature in geojson_data.get("features", [])
                if feature["geometry"]["type"] == "Polygon"
            ]

            if polygon_features:
                # تبدیل به اشیاء Polygon از Shapely و ادغام آن‌ها به MultiPolygon
                shapely_polygons = [
                    Polygon(feature["geometry"]["coordinates"][0]) 
                    for feature in polygon_features
                ]
                damage_polygons = unary_union(shapely_polygons)

                # نمایش لایه GeoJSON روی نقشه
                folium.GeoJson(
                    geojson_data,
                    name="Damage Layer",
                    style_function=lambda x: {"fillColor": "#ff000077", "color": "#ff0000", "weight": 2},
                ).add_to(m)
            else:
                st.warning("فایل GeoJSON معتبر نیست یا حاوی Polygon نمی‌باشد.")

        except json.JSONDecodeError:
            st.error("خطا در خواندن فایل: مطمئن شوید که یک فایل GeoJSON معتبر آپلود کرده‌اید.")
        except Exception as e:
             st.error(f"خطا هنگام پردازش GeoJSON: {e}")


folium.LayerControl().add_to(m)


# ===========================
# 6) نمایش نقشه
# ===========================
st.markdown("### نقشه مدارس و محدوده آسیب")
map_data = st_folium(m, width=1200, height=600, key="folium_map")


# ===========================
# 7) تحلیل مدارس داخل محدوده آسیب
# ===========================
inside = []

# حالت 1: محدوده GeoJSON آپلود شده
if damage_polygons is not None:
    inside = [
        row for _, row in filtered_df.iterrows()
        if damage_polygons.contains(Point(row["طول_جغرافیایی"], row["عرض_جغرافیایی"]))
    ]

# حالت 2: محدوده دستی ترسیم شده
elif damage_input_method == "ترسیم دستی روی نقشه" and map_data and map_data.get("all_drawings"):
    polys = [
        Polygon(d["geometry"]["coordinates"][0])
        for d in map_data["all_drawings"]
        if d["geometry"]["type"] == "Polygon"
    ]
    if polys:
        multi_poly = unary_union(polys)
        inside = [
            row for _, row in filtered_df.iterrows()
            if multi_poly.contains(Point(row["طول_جغرافیایی"], row["عرض_جغرافیایی"]))
        ]


# ===========================
# 8) نمایش نتایج و خروجی CSV
# ===========================
if inside:
    result = pd.DataFrame(inside)

    st.success(f"✅ تعداد مدارس داخل محدوده آسیب: **{len(result)}**")

    # --- نمایش گزارش تفصیلی ---
    st.markdown("---")
    st.markdown("### گزارش تفصیلی محدوده‌های آسیب‌دیده")

    col_report1, col_report2 = st.columns(2)

    with col_report1:
        st.subheader("تعداد مدارس به تفکیک مقطع")
        category_counts = result.groupby('دسته_مقطع').size().reset_index(name='تعداد مدارس')
        category_counts.columns = ['دسته مقطع', 'تعداد مدارس']
        st.dataframe(category_counts, width='stretch', hide_index=True)

    with col_report2:
        st.subheader("تعداد دانش‌آموزان به تفکیک جنسیت")
        gender_student_counts = result.groupby('جنسیت')['تعداد_دانش_آموز'].sum().reset_index(name='تعداد دانش‌آموز')
        gender_student_counts.columns = ['جنسیت', 'تعداد دانش‌آموز']
        st.dataframe(gender_student_counts, width='stretch', hide_index=True)
    
    st.markdown("---")
    st.subheader("لیست مدارس")

    st.dataframe(
        result[["نام_مدرسه", "دسته_مقطع", "جنسیت", "تعداد_دانش_آموز", "تعداد_معلم"]],
        width='stretch',
        hide_index=True
    )

    csv = result.to_csv(index=False, encoding="utf-8-sig").encode()
    st.download_button("دانلود لیست مدارس آسیب دیده (CSV)", csv, "damaged_schools.csv", "text/csv")

else:
    st.warning("هیچ مدرسه‌ای داخل محدوده آسیب یافت نشد.")
