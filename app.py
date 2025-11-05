import streamlit as st
import pandas as pd
import leafmap.foliumap as leafmap
from streamlit_folium import st_folium
import json

# تنظیمات صفحه
st.set_page_config(page_title="ارزیابی خسارت مدارس", layout="wide")
st.title("ارزیابی خسارت مدارس در بحران")
st.markdown("---")

# خواندن دیتاست
@st.cache_data
def load_data():
    df = pd.read_csv("schools.csv", encoding="utf-8")
    return df

df = load_data()

# تبدیل به GeoJSON برای نقشه
def df_to_geojson(df):
    features = []
    for _, row in df.iterrows():
        feature = {
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [row["طول_جغرافیایی"], row["عرض_جغرافیایی"]]
            },
            "properties": {
                "نام_مدرسه": row["نام_مدرسه"],
                "نام_مدیر": row["نام_مدیر"],
                "مقطع_تحصیلی": row["مقطع_تحصیلی"],
                "تعداد_دانش_آموز": row["تعداد_دانش_آموز"],
                "تعداد_معلم": row["تعداد_معلم"],
                "جنسیت": row["جنسیت"],
                "tooltip": (
                    f"<b>{row['نام_مدرسه']}</b><br>"
                    f"مدیر: {row['نام_مدیر']}<br>"
                    f"مقطع: {row['مقطع_تحصیلی']}<br>"
                    f"دانش‌آموز: {row['تعداد_دانش_آموز']} | معلم: {row['تعداد_معلم']}<br>"
                    f"جنسیت: {row['جنسیت']}"
                )
            }
        }
        features.append(feature)
    return {"type": "FeatureCollection", "features": features}

geojson_data = df_to_geojson(df)

# ساخت نقشه
m = leafmap.Map(
    center=[35.6892, 51.3890],
    zoom=11,
    tiles="OpenStreetMap"
)

# اضافه کردن مارکرها با تولتیپ
for feature in geojson_data["features"]:
    coords = feature["geometry"]["coordinates"]
    props = feature["properties"]
    m.add_circle_marker(
        location=[coords[1], coords[0]],
        radius=6,
        color="blue",
        fill_color="lightblue",
        fill_opacity=0.8,
        tooltip=props["tooltip"],
        popup=props["tooltip"].replace("<br>", "\n")
    )

# ابزار کشیدن پلی‌گون
m.add_draw_control()

# سرچ‌بار
col1, col2 = st.columns([3, 1])
with col1:
    search = st.text_input("جستجوی مکان (مثلاً: تجریش، شهرک غرب، ورامین)", "")
with col2:
    st.markdown("<br>", unsafe_allow_html=True)
    search_btn = st.button("برو به مکان")

if search_btn and search:
    try:
        # استفاده از Nominatim برای سرچ
        import requests
        url = f"https://nominatim.openstreetmap.org/search?format=json&q={search}+تهران"
        headers = {'User-Agent': 'CrisisApp/1.0'}
        response = requests.get(url, headers=headers).json()
        if response:
            lat = float(response[0]["lat"])
            lon = float(response[0]["lon"])
            m.set_center(lon, lat, zoom=14)
            st.success(f"مکان یافت شد: {response[0]['display_name'].split(',')[0]}")
        else:
            st.error("مکان یافت نشد.")
    except:
        st.error("خطا در جستجو.")

# نمایش نقشه
st.write("### نقشه مدارس (ماوس روی نقاط → مشخصات)")
output = st_folium(m, width=1200, height=600, key="map")

# پردازش پلی‌گون
if output and output.get("last_active_drawing"):
    drawing = output["last_active_drawing"]
    if drawing["geometry"]["type"] == "Polygon":
        coords = drawing["geometry"]["coordinates"][0]
        from shapely.geometry import Polygon, Point
        
        poly = Polygon([(p[0], p[1]) for p in coords])
        inside = []
        for _, row in df.iterrows():
            point = Point(row["طول_جغرافیایی"], row["عرض_جغرافیایی"])
            if poly.contains(point):
                inside.append(row)
        
        if inside:
            st.success(f"تعداد مدارس در محدوده: **{len(inside)}**")
            result_df = pd.DataFrame(inside)
            st.dataframe(
                result_df[["نام_مدرسه", "نام_مدیر", "مقطع_تحصیلی", "تعداد_دانش_آموز", "تعداد_معلم", "جنسیت"]],
                use_container_width=True
            )
            csv = result_df.to_csv(index=False, encoding="utf-8-sig").encode('utf-8-sig')
            st.download_button(
                "دانلود لیست (CSV)",
                csv,
                "مدارس_آسیب_دیده.csv",
                "text/csv"
            )
        else:
            st.warning("هیچ مدرسه‌ای در محدوده نیست.")
