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
    """بارگذاری و پاکسازی داده‌ها با کشینگ."""
    try:
        df = pd.read_csv("schools.csv", encoding="utf-8-sig")
        df = df.dropna(subset=['عرض_جغرافیایی', 'طول_جغرافیایی'])
        df['عرض_جغرافیایی'] = pd.to_numeric(df['عرض_جغرافیایی'], errors='coerce')
        df['طول_جغرافیایی'] = pd.to_numeric(df['طول_جغرافیایی'], errors='coerce')
        df['تعداد_دانش_آموز'] = pd.to_numeric(df['تعداد_دانش_آموز'], errors='coerce').fillna(0).astype(int)
        df['تعداد_معلم'] = pd.to_numeric(df['تعداد_معلم'], errors='coerce').fillna(0).astype(int)
        df = df.dropna(subset=['عرض_جغرافیایی', 'طول_جغرافیایی'])
        return df
    except Exception as e:
        st.error(f"خطا در خواندن فایل: {e}")
        return pd.DataFrame()

df = load_data()
if df.empty:
    st.warning("هیچ داده معتبری در فایل نیست.")
    st.stop()

# --- ۱. فیلترهای جانبی (Suggestions 2, 4) و ۳. نمایش تعداد کل مدارس (Suggestion 3) ---

st.sidebar.header("تنظیمات فیلتر")

# فیلتر مقطع تحصیلی
grade_levels = df['مقطع_تحصیلی'].unique()
selected_grades = st.sidebar.multiselect(
    "فیلتر بر اساس مقطع تحصیلی:",
    options=grade_levels,
    default=grade_levels
)

# فیلتر جنسیت
genders = df['جنسیت'].unique()
selected_genders = st.sidebar.multiselect(
    "فیلتر بر اساس جنسیت:",
    options=genders,
    default=genders
)

filtered_df = df[
    df['مقطع_تحصیلی'].isin(selected_grades) &
    df['جنسیت'].isin(selected_genders)
].copy()

# نمایش پیام در صورت خالی بودن داده فیلتر شده (Suggestion 4)
if filtered_df.empty:
    st.warning("با تنظیمات فیلتر فعلی، هیچ مدرسه معتبری برای نمایش وجود ندارد.")
    st.stop()

# نمایش تعداد کل مدارس نمایش داده شده (Suggestion 3)
st.info(f"تعداد کل مدارس نمایش داده شده: **{len(filtered_df)}** از **{len(df)}**")


# --- ۲. نقشه و لایه بندی (Suggestion 8) ---

# حفظ موقعیت اولیه نقشه در Session State
if 'initial_map_location' not in st.session_state:
     st.session_state.initial_map_location = [35.6892, 51.3890]
     st.session_state.initial_map_zoom = 11

m = folium.Map(
    location=st.session_state.initial_map_location, 
    zoom_start=st.session_state.initial_map_zoom, 
    tiles="OpenStreetMap"
)

# تعریف رنگ‌ها و FeatureGroup برای لایه‌بندی
grade_colors = {
    'ابتدایی': '#28a745', 
    'متوسطه اول': '#ffc107', 
    'متوسطه دوم': '#dc3545', 
}

grade_groups = {}
for grade in grade_levels:
    color = grade_colors.get(grade, '#007bff')
    # FeatureGroup به عنوان لایه برای LayerControl (Suggestion 8)
    group = folium.FeatureGroup(name=f"مقطع: {grade}", show=True)
    grade_groups[grade] = {'group': group, 'color': color}
    group.add_to(m)


# اضافه کردن مارکرها به FeatureGroup های مربوطه
for _, row in filtered_df.iterrows():
    lat, lon = row['عرض_جغرافیایی'], row['طول_جغرافیایی']
    grade = row['مقطع_تحصیلی']
    
    # اطمینان از وجود مقطع در دیکشنری
    group_data = grade_groups.get(grade, grade_groups.get(grade_levels[0], {'group': folium.FeatureGroup(name="سایر"), 'color': '#007bff'}))
    group = group_data['group']
    color = group_data['color']
    
    tooltip = (
        f"<b>{row['نام_مدرسه']}</b><br>"
        f"مدیر: {row['نام_مدیر']}<br>"
        f"مقطع: {grade}<br>"
        f"دانش‌آموز: {row['تعداد_دانش_آموز']}<br>"
        f"معلم: {row['تعداد_معلم']}<br>"
        f"جنسیت: {row['جنسیت']}"
    )
    
    folium.CircleMarker(
        location=[lat, lon],
        radius=7,
        color=color,
        fill=True,
        fillColor=color,
        tooltip=folium.Tooltip(tooltip, sticky=True),
        popup=folium.Popup(tooltip.replace("<br>", "\n"), max_width=300)
    ).add_to(group) # اضافه به گروه، نه مستقیم به نقشه

# ابزار کشیدن (Draw)
from folium.plugins import Draw
Draw(
    draw_options={'polyline':False,'rectangle':False,'circle':False,'marker':False,'circlemarker':False},
    edit_options={'edit':True, 'remove':True}
).add_to(m)

# کنترل لایه‌ها (LayerControl) (Suggestion 8)
folium.LayerControl().add_to(m)


# --- ۴. کش کردن جستجو (Suggestion 5) ---

@st.cache_data(ttl=3600)
def geocode_search(query):
    """کش کردن نتایج جستجوی Nominatim (Suggestion 5)."""
    try:
        r = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params={'q': query, 'format': 'json', 'limit': 1},
            headers={'User-Agent': 'IranCrisisMap/1.0'}
        ).json()
        if r:
            return float(r[0]["lat"]), float(r[0]["lon"]), r[0]['display_name'].split(',')[0]
        return None, None, None
    except Exception as e:
        st.error(f"خطا در جستجوی موقعیت جغرافیایی: {e}")
        return None, None, None

col1, col2 = st.columns([3,1])
with col1:
    search = st.text_input("جستجوی شهر/منطقه", placeholder="مثلاً: مشهد، شیراز، تجریش")
with col2:
    st.markdown("<br>", unsafe_allow_html=True)
    go = st.button("برو")

if go and search:
    lat, lon, name = geocode_search(search)
    if lat and lon:
        # به‌روزرسانی وضعیت نقشه برای حفظ موقعیت جدید
        st.session_state.initial_map_location = [lat, lon]
        st.session_state.initial_map_zoom = 13
        st.success(f"رفت به: {name}")
    else:
        st.error("جستجو نشد یا نتیجه‌ای برای آن مکان یافت نشد.")

# نمایش نقشه
st.markdown("### نقشه مدارس (ماوس روی نقاط → مشخصات)")
# نقشه هر بار با فیلتر جدید و موقعیت‌های ذخیره شده (session_state) مجددا رندر می‌شود.
map_data = st_folium(m, width=1200, height=600, key="folium_map")

# --- ۵. تحلیل پلی‌گون و نمایش آمار خلاصه (Suggestion 1 و 6) ---

if map_data and map_data.get("last_active_drawing"):
    drawing = map_data["last_active_drawing"]
    if drawing["geometry"]["type"] == "Polygon":
        coords = drawing["geometry"]["coordinates"][0]
        poly = Polygon(coords)
        
        # Shapely از ترتیب (Lon, Lat) استفاده می‌کند: Point(طول_جغرافیایی, عرض_جغرافیایی) (Suggestion 6)
        inside = [
            row for _, row in filtered_df.iterrows()
            if poly.contains(Point(row["طول_جغرافیایی"], row["عرض_جغرافیایی"]))
        ]
        
        if inside:
            result = pd.DataFrame(inside)
            
            # نمایش آمار خلاصه (Suggestion 1)
            total_students = result['تعداد_دانش_آموز'].sum()
            total_teachers = result['تعداد_معلم'].sum()
            
            st.success(f"مدارس در محدوده: **{len(inside)}**")
            st.info(f"جمع کل دانش‌آموزان: **{total_students}** | جمع کل معلمان: **{total_teachers}**")

            st.dataframe(
                result[["نام_مدرسه", "نام_مدیر", "مقطع_تحصیلی", "تعداد_دانش_آموز", "تعداد_معلم", "جنسیت"]],
                width='stretch'
            )
            csv = result.to_csv(index=False, encoding="utf-8-sig").encode()
            st.download_button("دانلود لیست (CSV)", csv, "مدارس_آسیب_دیده.csv", "text/csv")
        else:
            st.warning("هیچ مدرسه‌ای در محدوده نیست.")
