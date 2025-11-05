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
    """بارگذاری، پاکسازی و دسته‌بندی داده‌ها با کشینگ."""
    try:
        df = pd.read_csv("schools.csv", encoding="utf-8-sig")
        df = df.dropna(subset=['عرض_جغرافیایی', 'طول_جغرافیایی'])
        df['عرض_جغرافیایی'] = pd.to_numeric(df['عرض_جغرافیایی'], errors='coerce')
        df['طول_جغرافیایی'] = pd.to_numeric(df['طول_جغرافیایی'], errors='coerce')
        df['تعداد_دانش_آموز'] = pd.to_numeric(df['تعداد_دانش_آموز'], errors='coerce').fillna(0).astype(int)
        df['تعداد_معلم'] = pd.to_numeric(df['تعداد_معلم'], errors='coerce').fillna(0).astype(int)
        df = df.dropna(subset=['عرض_جغرافیایی', 'طول_جغرافیایی'])
        
        # --- تابع دسته‌بندی مقاطع برای رنگ بندی ---
        def categorize_grade(grade):
            if 'دبستان' in grade or 'پیش دبستانی' in grade:
                return 'ابتدایی/دبستان'
            elif 'متوسطه' in grade:
                return 'متوسطه'
            elif 'فنی و حرفه‌ای' in grade:
                return 'فنی و حرفه‌ای'
            elif 'مراکز' in grade:
                return 'مراکز/سایر'
            else:
                return 'نامشخص'

        df['دسته_مقطع'] = df['مقطع_تحصیلی'].apply(categorize_grade)
        # --------------------------------------------
        return df
    except Exception as e:
        st.error(f"خطا در خواندن فایل: {e}")
        return pd.DataFrame()

df = load_data()
if df.empty:
    st.warning("هیچ داده معتبری در فایل نیست.")
    st.stop()

# --- ۱. فیلترهای جانبی ---

st.sidebar.header("تنظیمات فیلتر")

grade_categories = df['دسته_مقطع'].unique()
selected_categories = st.sidebar.multiselect(
    "فیلتر بر اساس دسته مقطع تحصیلی:",
    options=grade_categories,
    default=grade_categories
)

genders = df['جنسیت'].unique()
selected_genders = st.sidebar.multiselect(
    "فیلتر بر اساس جنسیت:",
    options=genders,
    default=genders
)

filtered_df = df[
    df['دسته_مقطع'].isin(selected_categories) &
    df['جنسیت'].isin(selected_genders)
].copy()

if filtered_df.empty:
    st.warning("با تنظیمات فیلتر فعلی، هیچ مدرسه معتبری برای نمایش وجود ندارد.")
    st.stop()

st.info(f"تعداد کل مدارس نمایش داده شده: **{len(filtered_df)}** از **{len(df)}**")

# --- ۲. نقشه و لایه بندی با رنگ‌های جدید ---

if 'initial_map_location' not in st.session_state:
     st.session_state.initial_map_location = [35.6892, 51.3890]
     st.session_state.initial_map_zoom = 11

m = folium.Map(
    location=st.session_state.initial_map_location, 
    zoom_start=st.session_state.initial_map_zoom, 
    tiles="OpenStreetMap"
)

category_colors = {
    'ابتدایی/دبستان': '#28a745',    # سبز
    'متوسطه': '#007bff',            # آبی
    'فنی و حرفه‌ای': '#ffc107',     # زرد/نارنجی
    'مراکز/سایر': '#dc3545',        # قرمز 
    'نامشخص': '#6c757d'             # خاکستری
}

category_groups = {}
for category in grade_categories:
    color = category_colors.get(category, '#6c757d') 
    group = folium.FeatureGroup(name=f"دسته: {category}", show=True)
    category_groups[category] = {'group': group, 'color': color}
    group.add_to(m)


for _, row in filtered_df.iterrows():
    lat, lon = row['عرض_جغرافیایی'], row['طول_جغرافیایی']
    category = row['دسته_مقطع']
    
    group_data = category_groups.get(category)
    if not group_data: 
         continue

    group = group_data['group']
    color = group_data['color']
    
    tooltip = (
        f"<b>{row['نام_مدرسه']}</b><br>"
        f"مقطع: **{row['مقطع_تحصیلی']}** ({row['دسته_مقطع']})<br>"
        f"مدیر: {row['نام_مدیر']}<br>"
        f"دانش‌آموز: {row['تعداد_دانش_آموز']}<br>"
        f"معلم: {row['تعداد_معلم']}"
    )
    
    folium.CircleMarker(
        location=[lat, lon],
        radius=7,
        color=color,
        fill=True,
        fillColor=color,
        tooltip=folium.Tooltip(tooltip, sticky=True),
        popup=folium.Popup(tooltip.replace("<br>", "\n"), max_width=300)
    ).add_to(group)

from folium.plugins import Draw
Draw(
    draw_options={'polyline':False,'rectangle':False,'circle':False,'marker':False,'circlemarker':False},
    edit_options={'edit':True, 'remove':True}
).add_to(m)

folium.LayerControl().add_to(m)


# --- ۳. جستجوی مکان و نمایش نقشه ---

@st.cache_data(ttl=3600)
def geocode_search(query):
    """کش کردن نتایج جستجوی Nominatim."""
    try:
        r = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params={'q': query, 'format': 'json', 'limit': 1},
            headers={'User-Agent': 'IranCrisisMap/1.0'}
        ).json()
        if r:
            return float(r[0]["lat"]), float(r[0]["lon"]), r[0]['display_name'].split(',')[0]
        return None, None, None
    except Exception:
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
        st.session_state.initial_map_location = [lat, lon]
        st.session_state.initial_map_zoom = 13
        st.success(f"رفت به: {name}")
    else:
        st.error("جستجو نشد یا نتیجه‌ای برای آن مکان یافت نشد.")

st.markdown("### نقشه مدارس (ماوس روی نقاط → مشخصات)")
map_data = st_folium(m, width=1200, height=600, key="folium_map")

# --- ۴. تحلیل پلی‌گون و نمایش گزارش تفصیلی ---

if map_data and map_data.get("last_active_drawing"):
    drawing = map_data["last_active_drawing"]
    if drawing["geometry"]["type"] == "Polygon":
        coords = drawing["geometry"]["coordinates"][0]
        poly = Polygon(coords)
        
        inside = [
            row for _, row in filtered_df.iterrows()
            if poly.contains(Point(row["طول_جغرافیایی"], row["عرض_جغرافیایی"]))
        ]
        
        if inside:
            result = pd.DataFrame(inside)
            
            # --- گزارش خلاصه کلی ---
            total_schools = len(inside)
            total_students = result['تعداد_دانش_آموز'].sum()
            total_teachers = result['تعداد_معلم'].sum()
            
            st.success(f"مدارس در محدوده: **{total_schools}**")
            st.info(f"جمع کل دانش‌آموزان: **{total_students}** | جمع کل معلمان: **{total_teachers}**")
            
            st.markdown("---")
            st.markdown("### گزارش تفصیلی محدوده آسیب‌دیده")

            # --- گزارش تفکیک شده در دو ستون (درخواست شما) ---
            col_report1, col_report2 = st.columns(2)

            with col_report1:
                st.subheader("تعداد مدارس به تفکیک مقطع")
                # محاسبه تعداد مدارس به تفکیک دسته مقطع
                category_counts = result.groupby('دسته_مقطع').size().reset_index(name='تعداد مدارس')
                category_counts.columns = ['دسته مقطع', 'تعداد مدارس']
                st.dataframe(category_counts, use_container_width=True, hide_index=True)

            with col_report2:
                st.subheader("تعداد دانش‌آموزان به تفکیک جنسیت")
                # محاسبه مجموع دانش‌آموزان به تفکیک جنسیت
                gender_student_counts = result.groupby('جنسیت')['تعداد_دانش_آموز'].sum().reset_index(name='تعداد دانش‌آموز')
                gender_student_counts.columns = ['جنسیت', 'تعداد دانش‌آموز']
                st.dataframe(gender_student_counts, use_container_width=True, hide_index=True)
            
            st.markdown("---")
            st.subheader("لیست مدارس")
            st.dataframe(
                result[["نام_مدرسه", "دسته_مقطع", "تعداد_دانش_آموز", "تعداد_معلم", "جنسیت"]],
                width='stretch',
                hide_index=True
            )
            csv = result.to_csv(index=False, encoding="utf-8-sig").encode()
            st.download_button("دانلود لیست (CSV)", csv, "مدارس_آسیب_دیده.csv", "text/csv")
        else:
            st.warning("هیچ مدرسه‌ای در محدوده نیست.")
