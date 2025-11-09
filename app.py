import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
from shapely.geometry import Polygon, Point, shape
from shapely.ops import unary_union
import requests
import json
import os


# =======================================================
# 🛰️ تنظیمات صفحه و مدیریت session_state
# =======================================================
st.set_page_config(page_title="ارزیابی خسارت مدارس", layout="wide")
st.title("🛰️ ارزیابی خسارت مدارس در بحران")

if "reset" not in st.session_state:
    st.session_state.reset = 0
if "geojson" not in st.session_state:
    st.session_state.geojson = None
if "map_center" not in st.session_state:
    st.session_state.map_center = [32.5, 53.0]   # مرکز ایران
if "map_zoom" not in st.session_state:
    st.session_state.map_zoom = 5


# =======================================================
# ۱) بارگذاری داده مدارس
# =======================================================
@st.cache_data
def load_data():
    df = pd.read_csv("schools.csv", encoding="utf-8-sig")

    df["عرض_جغرافیایی"] = pd.to_numeric(df["عرض_جغرافیایی"])
    df["طول_جغرافیایی"] = pd.to_numeric(df["طول_جغرافیایی"])

    def categorize(x):
        if "دبستان" in x or "پیش" in x:
            return "ابتدایی/دبستان"
        if "متوسطه" in x:
            return "متوسطه"
        if "فنی" in x:
            return "فنی و حرفه‌ای"
        return "سایر"

    df["دسته_مقطع"] = df["مقطع_تحصیلی"].apply(categorize)

    return df


if not os.path.exists("schools.csv"):
    st.error("❌ schools.csv یافت نشد.")
    st.stop()

df = load_data()


# =======================================================
# ۲) فیلترها + آپلود GeoJSON
# =======================================================
st.sidebar.header("فیلتر مدارس")

grade_filter = st.sidebar.multiselect(
    "مقطع تحصیلی", df["دسته_مقطع"].unique(), df["دسته_مقطع"].unique()
)

gender_filter = st.sidebar.multiselect(
    "جنسیت", df["جنسیت"].unique(), df["جنسیت"].unique()
)

filtered = df[
    df["دسته_مقطع"].isin(grade_filter) &
    df["جنسیت"].isin(gender_filter)
]

st.sidebar.header("📁 آپلود نقشه محدوده آسیب (GeoJSON)")
geojson_file = st.sidebar.file_uploader("آپلود فایل GeoJSON یا JSON", type=["json", "geojson"])

if geojson_file:
    st.session_state.geojson = json.load(geojson_file)

    # فوکوس روی محدوده
    shp = shape(st.session_state.geojson["features"][0]["geometry"])
    st.session_state.map_center = [shp.centroid.y, shp.centroid.x]
    st.session_state.map_zoom = 12

    st.sidebar.success("✅ محدوده بارگذاری شد و نقشه فوکوس شد.")


# دکمه ریست
if st.sidebar.button("♻️ ریست کامل"):
    st.session_state.geojson = None
    st.session_state.map_center = [32.5, 53.0]
    st.session_state.map_zoom = 5
    st.session_state.reset += 1
    st.rerun()


# =======================================================
# ۳) ساخت نقشه Folium + نمایش مدارس
# =======================================================
m = folium.Map(
    location=st.session_state.map_center,
    zoom_start=st.session_state.map_zoom,
    tiles="OpenStreetMap"
)

colors = {
    "ابتدایی/دبستان": "green",
    "متوسطه": "blue",
    "فنی و حرفه‌ای": "orange",
    "سایر": "red"
}

for _, r in filtered.iterrows():
    folium.CircleMarker(
        location=[r["عرض_جغرافیایی"], r["طول_جغرافیایی"]],
        radius=6,
        color=colors[r["دسته_مقطع"]],
        fill=True,
        fill_opacity=0.9,
        tooltip=(
            f"<b>{r['نام_مدرسه']}</b><br>"
            f"مقطع: {r['مقطع_تحصیلی']}<br>"
            f"دانش‌آموز: {r['تعداد_دانش_آموز']} | "
            f"معلم: {r['تعداد_معلم']}"
        )
    ).add_to(m)


# اگر GeoJSON آپلود شده نمایش آن روی نقشه
if st.session_state.geojson:
    folium.GeoJson(
        st.session_state.geojson,
        style_function=lambda x: {"fillColor": "red", "color": "red", "fillOpacity": 0.3},
        name="محدوده وارد شده (GeoJSON)"
    ).add_to(m)


# ابزار ترسیم پلی‌گون
from folium.plugins import Draw
Draw(
    draw_options={"polygon": True, "polyline": False, "marker": False, "circle": False},
    edit_options={"edit": True, "remove": True}
).add_to(m)

folium.LayerControl().add_to(m)

map_data = st_folium(m, width=1200, height=600, key=f"map_{st.session_state.reset}")


# =======================================================
# ۴) تحلیل محدوده و یافتن مدارس داخل Polygon
# =======================================================
polygons = []

# پلی‌گون دستی
if map_data and map_data.get("all_drawings"):
    for p in map_data["all_drawings"]:
        if p["geometry"]["type"] == "Polygon":
            coords = [(lon, lat) for lat, lon in p["geometry"]["coordinates"][0]]
            polygons.append(Polygon(coords))

# از فایل GeoJSON
if st.session_state.geojson:
    polygons.append(shape(st.session_state.geojson["features"][0]["geometry"]))

# اگر هیچ محدوده‌ای انتخاب نشده
if not polygons:
    st.info("برای شروع: روی نقشه پلی‌گون بکشید یا GeoJSON آپلود کنید.")
    st.stop()

merged = unary_union(polygons)

filtered["inside"] = filtered.apply(
    lambda r: merged.contains(Point(r["طول_جغرافیایی"], r["عرض_جغرافیایی"])),
    axis=1
)

result = filtered[filtered["inside"] == True]


# =======================================================
# ۵) نمایش نتیجه
# =======================================================
st.subheader("📊 نتایج ارزیابی")

if result.empty:
    st.warning("هیچ مدرسه‌ای در محدوده انتخابی یافت نشد.")
else:
    st.success(f"✅ تعداد مدارس آسیب‌دیده: **{len(result)}**")

    st.dataframe(result, use_container_width=True)

    csv = result.to_csv(index=False, encoding="utf-8-sig")
    st.download_button(
        "دانلود لیست مدارس آسیب‌دیده (CSV)",
        csv,
        "schools_affected.csv",
        "text/csv",
    )
