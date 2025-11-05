import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
from shapely.geometry import Polygon, Point
import requests
import os

st.set_page_config(page_title="ارزیابی خسارت مدارس", layout="wide")
st.title("ارزیابی خسارت مدارس در بحران")

# چک کردن فایل
if not os.path.exists("schools.csv"):
    st.error("فایل `schools.csv` در ریشه ریپازیتوری پیدا نشد!")
    st.stop()

@st.cache_data
def load_data():
    try:
        df = pd.read_csv("schools.csv", encoding="utf-8-sig")
        df = df.dropna(subset=['عرض_جغرافیایی', 'طول_جغرافیایی'])
        return df
    except Exception as e:
        st.error(f"خطا در خواندن فایل: {e}")
        return pd.DataFrame()

df = load_data()
if df.empty:
    st.warning("هیچ داده‌ای در فایل نیست.")
    st.stop()

# نقشه — فقط یک بار ساخته بشه
if 'map_obj' not in st.session_state:
    st.session_state.map_obj = folium.Map(location=[35.6892, 51.3890], zoom_start=11, tiles="OpenStreetMap")

m = st.session_state.map_obj

# مارکرها — فقط یک بار اضافه بشن
if not hasattr(m, 'markers_added'):
    for _, row in df.iterrows():
        lat, lon = row['عرض_جغرافیایی'], row['طول_جغرافیایی']
        if pd.isna(lat) or pd.isna(lon):
            continue
        tooltip = (
            f"<b>{row['نام_مدرسه']}</b><br>"
            f"مدیر: {row['نام_مدیر']}<br>"
            f"مقطع: {row['مقطع_تحصیلی']}<br>"
            f"دانش‌آموز: {row['تعداد_دانش_آموز']}<br>"
            f"معلم: {row['تعداد_معلم']}<br>"
            f"جنسیت: {row['جنسیت']}"
        )
        folium.CircleMarker(
            location=[lat, lon],
            radius=7,
            color="#007bff",
            fill=True,
            fillColor="#007bff",
            tooltip=folium.Tooltip(tooltip, sticky=True, delay=0),
            popup=folium.Popup(tooltip.replace("<br>", "\n"), max_width=300)
        ).add_to(m)
    m.markers_added = True

# ابزار کشیدن — فقط یک بار
if not hasattr(m, 'draw_added'):
    from folium.plugins import Draw
    Draw(
        draw_options={'polyline': False, 'rectangle': False, 'circle': False, 'marker': False, 'circlemarker': False},
        edit_options={'edit': True, 'remove': True}
    ).add_to(m)
    m.draw_added = True

# سرچ
col1, col2 = st.columns([3, 1])
with col1:
    search = st.text_input("جستجوی شهر/منطقه", placeholder="مثلاً: مشهد، شیراز، تجریش")
with col2:
    st.markdown("<br>", unsafe_allow_html=True)
    go = st.button("برو")

if go and search:
    try:
        r = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params={'q': search, 'format': 'json', 'limit': 1},
            headers={'User-Agent': 'IranCrisisMap/1.0'}
        ).json()
        if r:
            lat, lon = float(r[0]["lat"]), float(r[0]["lon"])
            m.location = [lat, lon]
            m.zoom_start = 13
            st.success(f"رفت به: {r[0]['display_name'].split(',')[0]}")
    except:
        st.error("جستجو نشد.")

# نمایش نقشه
st.markdown("### نقشه مدارس (ماوس روی نقاط → مشخصات)")
map_data = st_folium(m, width=1200, height=600, key="folium_map")

# پلی‌گون
if map_data and map_data.get("last_active_drawing"):
    drawing = map_data["last_active_drawing"]
    if drawing["geometry"]["type"] == "Polygon":
        coords = drawing["geometry"]["coordinates"][0]
        poly = Polygon(coords)
        inside = [
            row for _, row in df.iterrows()
            if poly.contains(Point(row["طول_جغرافیایی"], row["عرض_جغرافیایی"]))
        ]
        if inside:
            result = pd.DataFrame(inside)
            st.success(f"مدارس در محدوده: **{len(inside)}**")
            st.dataframe(
                result[["نام_مدرسه", "نام_مدیر", "مقطع_تحصیلی", "تعداد_دانش_آموز", "تعداد_معلم", "جنسیت"]],
                use_container_width=True
            )
            csv = result.to_csv(index=False, encoding="utf-8-sig").encode()
            st.download_button("دانلود لیست (CSV)", csv, "مدارس_آسیب_دیده.csv", "text/csv")
        else:
            st.warning("هیچ مدرسه‌ای در محدوده نیست.")
