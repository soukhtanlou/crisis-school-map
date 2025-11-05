import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
from shapely.geometry import Polygon, Point
import requests

# تنظیمات صفحه
st.set_page_config(page_title="ارزیابی خسارت مدارس", layout="wide")
st.title("ارزیابی خسارت مدارس در بحران")
st.markdown("---")

# خواندن دیتاست
@st.cache_data
def load_data():
    try:
        df = pd.read_csv("schools.csv", encoding="utf-8-sig")
        return df
    except Exception as e:
        st.error(f"خطا در خواندن فایل: {e}")
        return pd.DataFrame()

df = load_data()

if df.empty:
    st.stop()

# ساخت نقشه
m = folium.Map(location=[35.6892, 51.3890], zoom_start=11, tiles="OpenStreetMap")

# اضافه کردن مارکرها با تولتیپ
for idx, row in df.iterrows():
    tooltip = (
        f"<b>{row['نام_مدرسه']}</b><br>"
        f"مدیر: {row['نام_مدیر']}<br>"
        f"مقطع: {row['مقطع_تحصیلی']}<br>"
        f"دانش‌آموز: {row['تعداد_دانش_آموز']} | معلم: {row['تعداد_معلم']}<br>"
        f"جنسیت: {row['جنسیت']}"
    )
    
    folium.CircleMarker(
        location=[row['عرض_جغرافیایی'], row['طول_جغرافیایی']],
        radius=7,
        popup=folium.Popup(tooltip.replace("<br>", "\n"), max_width=300),
        tooltip=folium.Tooltip(tooltip, sticky=True),
        color="#3388ff",
        fill=True,
        fillColor="#3388ff",
        fillOpacity=0.8
    ).add_to(m)

# ابزار کشیدن پلی‌گون
from folium.plugins import Draw
draw = Draw(
    draw_options={
        'polyline': False,
        'rectangle': False,
        'circle': False,
        'marker': False,
        'circlemarker': False
    },
    edit_options={'remove': True}
)
draw.add_to(m)

# سرچ‌بار
col1, col2 = st.columns([3, 1])
with col1:
    search = st.text_input("جستجوی مکان (مثلاً: تجریش، شهرک غرب، ورامین)", "")
with col2:
    st.markdown("<br>", unsafe_allow_html=True)
    search_btn = st.button("برو به مکان")

if search_btn and search:
    try:
        url = f"https://nominatim.openstreetmap.org/search"
        params = {
            'q': f"{search}, تهران, ایران",
            'format': 'json',
            'limit': 1
        }
        headers = {'User-Agent': 'CrisisSchoolMap/1.0'}
        response = requests.get(url, params=params, headers=headers).json()
        if response:
            lat = float(response[0]["lat"])
            lon = float(response[0]["lon"])
            m.location = [lat, lon]
            m.zoom_start = 14
            st.success(f"مکان یافت شد: {response[0]['display_name'].split(',')[0]}")
        else:
            st.error("مکان یافت نشد.")
    except:
        st.error("خطا در جستجو.")

# نمایش نقشه
st.markdown("### نقشه مدارس (ماوس روی نقاط → مشخصات)")
map_data = st_folium(m, width=1200, height=600, key="map")

# پردازش پلی‌گون
if map_data and map_data.get("last_active_drawing"):
    drawing = map_data["last_active_drawing"]
    if drawing["geometry"]["type"] == "Polygon":
        coords = drawing["geometry"]["coordinates"][0]
        poly = Polygon([(lon, lat) for lon, lat in coords])
        
        inside = []
        for _, row in df.iterrows():
            point = Point(row["طول_جغرافیایی"], row["عرض_جغرافیایی"])
            if poly.contains(point):
                inside.append(row.to_dict())
        
        if inside:
            st.success(f"تعداد مدارس در محدوده: **{len(inside)}**")
            result_df = pd.DataFrame(inside)
            st.dataframe(
                result_df[["نام_مدرسه", "نام_مدیر", "مقطع_تحصیلی", "تعداد_دانش_آموز", "تعداد_معلم", "جنسیت"]],
                use_container_width=True
            )
            csv = result_df.to_csv(index=False, encoding="utf-8-sig").encode()
            st.download_button("دانلود CSV", csv, "مدارس_آسیب_دیده.csv", "text/csv")
        else:
            st.warning("هیچ مدرسه‌ای در محدوده نیست.")

# راهنما
with st.expander("راهنما"):
    st.markdown("""
    1. ماوس روی نقاط → مشخصات مدرسه  
    2. جستجو → رفتن به مکان  
    3. ابزار پلی‌گون → کشیدن محدوده  
    4. نتیجه → جدول + دانلود
    """)
