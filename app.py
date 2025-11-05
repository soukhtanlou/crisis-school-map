import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
import json
from shapely.geometry import Polygon, Point
import requests

# تنظیمات صفحه
st.set_page_config(page_title="ارزیابی خسارت مدارس", layout="wide")
st.title("🛡️ ارزیابی خسارت مدارس در بحران")
st.markdown("---")

# خواندن دیتاست
@st.cache_data
def load_data():
    df = pd.read_csv("schools.csv", encoding="utf-8")
    return df

df = load_data()

# ساخت نقشه
m = folium.Map(location=[35.6892, 51.3890], zoom_start=11, tiles="OpenStreetMap")

# اضافه کردن مارکرهای مدارس با تولتیپ
for idx, row in df.iterrows():
    tooltip_html = (
        f"<b>{row['نام_مدرسه']}</b><br>"
        f"مدیر: {row['نام_مدیر']}<br>"
        f"مقطع: {row['مقطع_تحصیلی']}<br>"
        f"دانش‌آموز: {row['تعداد_دانش_آموز']} | معلم: {row['تعداد_معلم']}<br>"
        f"جنسیت: {row['جنسیت']}"
    )
    
    folium.CircleMarker(
        location=[row['عرض_جغرافیایی'], row['طول_جغرافیایی']],
        radius=6,
        popup=tooltip_html.replace("<br>", "\n"),
        tooltip=folium.Tooltip(tooltip_html, sticky=True, permanent=False),
        color="blue",
        fill=True,
        fillColor="lightblue",
        fillOpacity=0.8,
        weight=2
    ).add_to(m)

# اضافه کردن ابزار کشیدن پلی‌گون
from folium.plugins import Draw
draw = Draw(
    draw_options={'polyline': False, 'rectangle': False, 'circle': False, 'marker': False, 'circlemarker': False},
    edit_options={'remove': True}
)
draw.add_to(m)

# سرچ‌بار
col1, col2 = st.columns([3, 1])
with col1:
    search = st.text_input("🔍 جستجوی مکان (مثلاً: تجریش، شهرک غرب، ورامین)", placeholder="نام شهر/روستا را وارد کنید...")
with col2:
    search_btn = st.button("برو به مکان", use_container_width=True)

if search_btn and search:
    try:
        # استفاده از Nominatim (OSM) برای سرچ
        url = f"https://nominatim.openstreetmap.org/search?format=json&q={search}+تهران&limit=1"
        headers = {'User-Agent': 'CrisisSchoolApp/1.0 (contact@example.com)'}
        response = requests.get(url, headers=headers).json()
        if response:
            lat = float(response[0]["lat"])
            lon = float(response[0]["lon"])
            m.location = [lat, lon]
            m.zoom_start = 14
            st.success(f"✅ مکان یافت شد: {response[0].get('display_name', '').split(',')[0]}")
        else:
            st.error("❌ مکان یافت نشد. نام را دقیق‌تر وارد کنید.")
    except Exception as e:
        st.error(f"❌ خطا در جستجو: {str(e)}")

# نمایش نقشه
st.markdown("### 🗺️ نقشه مدارس (ماوس روی نقاط → مشخصات مدرسه)")
map_output = st_folium(m, width=1200, height=600, key="map")

# پردازش پلی‌گون (وقتی کاربر محدوده می‌کشه)
if map_output and 'last_active_drawing' in map_output:
    drawing = map_output['last_active_drawing']
    if drawing and drawing.get('geometry', {}).get('type') == 'Polygon':
        coords = drawing['geometry']['coordinates'][0]
        poly_coords = [(p[0], p[1]) for p in coords]  # lon, lat to (x,y)
        poly = Polygon(poly_coords)
        
        inside_schools = []
        for _, row in df.iterrows():
            school_point = Point(row['طول_جغرافیایی'], row['عرض_جغرافیایی'])
            if poly.contains(school_point):
                inside_schools.append(row)
        
        if inside_schools:
            st.success(f"✅ **{len(inside_schools)}** مدرسه در محدوده آسیب‌دیده شناسایی شد!")
            result_df = pd.DataFrame(inside_schools)
            st.dataframe(
                result_df[["نام_مدرسه", "نام_مدیر", "مقطع_تحصیلی", "تعداد_دانش_آموز", "تعداد_معلم", "جنسیت"]],
                use_container_width=True,
                hide_index=True,
                column_config={
                    "تعداد_دانش_آموز": st.column_config.NumberColumn("تعداد دانش‌آموز", format="%d"),
                    "تعداد_معلم": st.column_config.NumberColumn("تعداد معلم", format="%d")
                }
            )
            
            # دکمه دانلود CSV
            csv_data = result_df.to_csv(index=False, encoding="utf-8-sig")
            st.download_button(
                label="📥 دانلود لیست مدارس آسیب‌دیده (CSV)",
                data=csv_data.encode('utf-8-sig'),
                file_name="مدارس_آسیب_دیده.csv",
                mime="text/csv"
            )
        else:
            st.warning("⚠️ هیچ مدرسه‌ای در محدوده مشخص‌شده نیست. محدوده را بزرگ‌تر کنید.")

# راهنما
with st.expander("📖 راهنما استفاده"):
    st.markdown("""
    1. **نقشه را ببینید**: نقاط آبی مدارس هستند. ماوس روی آن‌ها → مشخصات نمایش داده می‌شود.
    2. **جستجو کنید**: نام مکان (مثل "تجریش") را وارد و دکمه بزنید → نقشه به آنجا می‌رود.
    3. **محدوده بکشید**: از نوار ابزار بالا سمت چپ نقشه، ابزار **Polygon** را انتخاب کنید و محدوده آسیب را بکشید.
    4. **نتیجه را ببینید**: بعد از کشیدن، جدول مدارس داخل محدوده ظاهر می‌شود + دانلود CSV.
    """)

st.markdown("---")
st.caption("💡 ساخته‌شده با Streamlit | داده‌ها: نمونه تهران | تماس: your-email@example.com")
