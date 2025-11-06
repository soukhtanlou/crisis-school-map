import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
from shapely.geometry import Polygon, Point, shape
from shapely.ops import unary_union
import requests
import os
import json 
import io 
import numpy as np

# تنظیمات صفحه
st.set_page_config(page_title="ارزیابی خسارت مدارس", layout="wide")
st.title("ارزیابی خسارت مدارس در بحران")

# --- ۱. بارگذاری و آماده‌سازی داده‌های مدارس ---

# ایجاد یک فایل dummy برای اجرای اولیه در محیط‌های بدون دسترسی به فایل سیستم محلی (اگر schools.csv وجود نداشته باشد)
if not os.path.exists("schools.csv"):
    try:
        data = {
            'کد_مدرسه': [100013, 100014, 100015, 100016, 100017, 100018, 100019, 100020, 100021, 100022],
            'نام_مدرسه': ['دبستان شهدای گمنام', 'متوسطه اندیشه', 'فنی خوارزمی', 'دبستان آزادی', 'متوسطه فردوسی', 'پیش‌دبستانی شکوفه', 'مرکز مشاوران ۱', 'دبستان فجر', 'متوسطه الزهرا', 'دبستان هدف'],
            'نام_مدیر': ['م.رحیمی', 'ن.صادقی', 'ج.مرادی', 'ف.نظری', 'ع.حیدری', 'ز.مرادخانی', 'ا.اسدی', 'م.جعفری', 'س.کریمی', 'ج.نوری'],
            'مقطع_تحصیلی': ['دبستان دوره دوم', 'متوسطه اول', 'فنی و حرفه‌ای', 'دبستان دوره اول', 'متوسطه دوم', 'پیش دبستانی', 'مراکز مشاوره', 'دبستان دوره دوم', 'متوسطه دوم', 'دبستان دوره اول'],
            'تعداد_دانش_آموز': [415, 490, 280, 350, 520, 150, 0, 390, 470, 330],
            'تعداد_معلم': [29, 31, 30, 24, 34, 12, 18, 26, 30, 23],
            'جنسیت': ['مختلط', 'پسرانه', 'مختلط', 'دخترانه', 'پسرانه', 'دخترانه', 'مختلط', 'پسرانه', 'دخترانه', 'مختلط'],
            # مختصات‌های نزدیک گلستان برای تطبیق با GeoJSON
            'عرض_جغرافیایی': [37.3321, 37.3105, 37.2889, 37.3450, 37.2995, 37.3012, 37.3208, 37.3155, 37.2770, 37.3050],
            'طول_جغرافیایی': [54.5103, 54.4552, 54.5408, 54.4901, 54.4253, 54.5005, 54.4852, 54.5303, 54.4601, 54.4050]
        }
        dummy_df = pd.DataFrame(data)
        dummy_df.to_csv("schools.csv", index=False, encoding="utf-8-sig")
        st.warning("فایل `schools.csv` پیدا نشد. یک فایل آزمایشی با ۱۰ مدرسه ساخته شد.")
    except Exception as e:
        st.error(f"فایل `schools.csv` در ریشه ریپازیتوری پیدا نشد و ساخت فایل آزمایشی هم با خطا مواجه شد: {e}")
        st.stop()


@st.cache_data
def load_data():
    """بارگذاری، پاکسازی و دسته‌بندی داده‌ها با کشینگ."""
    try:
        # استفاده از encoding="utf-8-sig" برای سازگاری با فایل‌های تولید شده توسط Excel
        df = pd.read_csv("schools.csv", encoding="utf-8-sig")
        
        # تبدیل به عدد و پر کردن مقادیر خالی با 0
        df['عرض_جغرافیایی'] = pd.to_numeric(df['عرض_جغرافیایی'], errors='coerce')
        df['طول_جغرافیایی'] = pd.to_numeric(df['طول_جغرافیایی'], errors='coerce')
        df['تعداد_دانش_آموز'] = pd.to_numeric(df['تعداد_دانش_آموز'], errors='coerce').fillna(0).astype(int)
        df['تعداد_معلم'] = pd.to_numeric(df['تعداد_معلم'], errors='coerce').fillna(0).astype(int)
        
        # حذف سطرهای بدون مختصات جغرافیایی معتبر
        df = df.dropna(subset=['عرض_جغرافیایی', 'طول_جغرافیایی'])
        
        # --- تابع دسته‌بندی مقاطع برای رنگ بندی ---
        def categorize_grade(grade):
            grade = str(grade)
            if 'دبستان' in grade or 'پیش دبستانی' in grade:
                return 'ابتدایی/دبستان'
            elif 'متوسطه' in grade:
                return 'متوسطه'
            elif 'فنی' in grade or 'کار و دانش' in grade:
                return 'فنی و حرفه‌ای'
            else:
                return 'مراکز/سایر'

        df['دسته_مقطع'] = df['مقطع_تحصیلی'].apply(categorize_grade)
        return df
    except Exception as e:
        st.error(f"خطا در خواندن فایل مدارس: {e}")
        return pd.DataFrame()

df = load_data()
if df.empty:
    st.warning("هیچ داده معتبری از مدارس بارگذاری نشد.")
    st.stop()


# --- ۲. فیلترهای جانبی و آپلود GeoJSON ---

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

# --- آپلود GeoJSON برای محدوده آسیب (اصلاح شده) ---
st.sidebar.markdown("---")
st.sidebar.header("تعیین محدوده آسیب (GeoJSON)")
geojson_file = st.sidebar.file_uploader(
    "آپلود فایل GeoJSON (Polygon/MultiPolygon)",
    type=["geojson", "json"],
    help="برای مشخص کردن محدوده آسیب‌دیده از طریق فایل."
)

uploaded_geojson_data = None
if geojson_file:
    # *** رفع خطای "I/O operation on closed file" با خواندن مستقیم JSON ***
    try:
        uploaded_geojson_data = json.load(geojson_file)
        st.sidebar.success("فایل GeoJSON با موفقیت بارگذاری شد.")
    except Exception as e:
        st.sidebar.error(f"خطا در خواندن محتوای GeoJSON: {e}")
        uploaded_geojson_data = None

if filtered_df.empty:
    st.warning("با تنظیمات فیلتر فعلی، هیچ مدرسه معتبری برای نمایش وجود ندارد.")
    st.stop()

st.info(f"تعداد کل مدارس نمایش داده شده: **{len(filtered_df)}** از **{len(df)}**")


# --- ۳. ساخت نقشه فولیم (Folium Map) ---

# تنظیمات اولیه نقشه
if 'initial_map_location' not in st.session_state:
    st.session_state.initial_map_location = [df['عرض_جغرافیایی'].mean(), df['طول_جغرافیایی'].mean()] 
    st.session_state.initial_map_zoom = 11

m = folium.Map(
    location=st.session_state.initial_map_location, 
    zoom_start=st.session_state.initial_map_zoom, 
    tiles="OpenStreetMap"
)

# تعریف رنگ‌ها بر اساس دسته مقطع
category_colors = {
    'ابتدایی/دبستان': '#28a745',       # سبز
    'متوسطه': '#007bff',              # آبی
    'فنی و حرفه‌ای': '#ffc107',       # زرد/نارنجی
    'مراکز/سایر': '#dc3545',          # قرمز 
}

# --- اضافه کردن لایه مدارس به نقشه ---
school_layer_group = folium.FeatureGroup(name="نقاط مدارس (بر اساس فیلتر)", show=True).add_to(m)

for _, row in filtered_df.iterrows():
    lat, lon = row['عرض_جغرافیایی'], row['طول_جغرافیایی']
    category = row['دسته_مقطع']
    
    color = category_colors.get(category, '#6c757d') # رنگ خاکستری برای نامشخص
    
    tooltip = (
        f"<b>{row.get('نام_مدرسه', 'نامشخص')}</b><br>"
        f"مقطع: **{row.get('مقطع_تحصیلی', 'نامشخص')}**<br>"
        f"دانش‌آموز: {row.get('تعداد_دانش_آموز', 0)} | معلم: {row.get('تعداد_معلم', 0)}"
    )
    
    folium.CircleMarker(
        location=[lat, lon],
        radius=7,
        color=color,
        fill=True,
        fillColor=color,
        tooltip=folium.Tooltip(tooltip, sticky=True),
    ).add_to(school_layer_group)


# --- اضافه کردن GeoJSON آپلود شده به نقشه ---
if uploaded_geojson_data:
    folium.GeoJson(
        uploaded_geojson_data,
        name='محدوده آسیب (GeoJSON)',
        style_function=lambda x: {
            'fillColor': '#dc3545', 
            'color': '#dc3545',
            'weight': 3, 
            'fillOpacity': 0.3
        },
        tooltip=folium.Tooltip("محدوده آسیب بارگذاری شده از GeoJSON"),
        popup=folium.Popup("این محدوده توسط فایل GeoJSON مشخص شده است.")
    ).add_to(m)


# --- ابزار ترسیم (Draw Plugin) ---
from folium.plugins import Draw
Draw(
    draw_options={
        'polyline':False,
        'rectangle':False,
        'circle':False,
        'marker':False,
        'circlemarker':False,
    }, 
    edit_options={'edit':True, 'remove':True}
).add_to(m)

folium.LayerControl().add_to(m)


# --- ۴. جستجوی مکان و نمایش نقشه ---

@st.cache_data(ttl=3600)
def geocode_search(query):
    """جستجوی مختصات با Nominatim."""
    try:
        r = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params={'q': query, 'format': 'json', 'limit': 1},
            headers={'User-Agent': 'SchoolDamageAssessmentTool/1.0'}
        ).json()
        if r:
            return float(r[0]["lat"]), float(r[0]["lon"]), r[0]['display_name'].split(',')[0]
        return None, None, None
    except Exception:
        return None, None, None

col1, col2 = st.columns([3,1])
with col1:
    search = st.text_input("جستجوی شهر/منطقه", placeholder="مثلاً: گرگان، تهران، مشهد")
with col2:
    st.markdown("<br>", unsafe_allow_html=True)
    go = st.button("برو به مکان")

if go and search:
    lat, lon, name = geocode_search(search)
    if lat and lon:
        st.session_state.initial_map_location = [lat, lon]
        st.session_state.initial_map_zoom = 13
        st.success(f"نقشه به: {name} جابجا شد.")
        # Streamlit باید کل برنامه را اجرا کند تا نقشه رندر مجدد شود
        st.rerun() 
    else:
        st.error("جستجو نشد یا نتیجه‌ای برای آن مکان یافت نشد.")

st.markdown("### نقشه مدارس و محدوده‌های آسیب")

# نمایش نقشه و دریافت ورودی‌های ترسیم شده
map_data = st_folium(m, width=1200, height=600, key="folium_map_final")


# --- ۵. تحلیل نقاط داخل پلی‌گون‌های ترسیم شده و GeoJSON ---

all_shapely_polygons = []
multi_poly = None

# --- الف: پردازش پلی‌گون‌های دستی ترسیم شده (Manual Drawings) ---
if map_data and map_data.get("all_drawings"):
    polygons_coords = [
        drawing["geometry"]["coordinates"][0]
        for drawing in map_data["all_drawings"]
        if drawing["geometry"]["type"] == "Polygon"
    ]
    
    if polygons_coords:
        try:
            # ایجاد Shapely Polygons از مختصات (Lon, Lat)
            manual_polygons = [Polygon(coords) for coords in polygons_coords]
            all_shapely_polygons.extend(manual_polygons)
        except Exception:
            st.warning("اشکالی در ایجاد هندسه پلی‌گون‌های دستی وجود دارد. لطفاً شکل‌های ترسیمی را بررسی کنید.")


# --- ب: پردازش فایل GeoJSON آپلود شده ---
if uploaded_geojson_data:
    geojson_data = uploaded_geojson_data
    
    features = []
    if geojson_data.get('type') == 'FeatureCollection':
        features = geojson_data.get('features', [])
    elif geojson_data.get('type') == 'Feature':
        features = [geojson_data]
    elif geojson_data.get('type') in ['Polygon', 'MultiPolygon']:
        features = [{'geometry': geojson_data}]
        
    for feature in features:
        geometry = feature.get('geometry')
        if geometry:
            try:
                # استفاده از shape() برای تبدیل GeoJSON به Shapely object
                geo_obj = shape(geometry)
                
                # اگر MultiPolygon بود، هر پلی‌گون را جداگانه به لیست اضافه کن
                if geo_obj.geom_type == 'MultiPolygon':
                    for poly in geo_obj.geoms:
                        all_shapely_polygons.append(poly)
                # اگر Polygon بود، مستقیم به لیست اضافه کن
                elif geo_obj.geom_type == 'Polygon':
                    all_shapely_polygons.append(geo_obj)
            except Exception as e:
                st.warning(f"هندسه GeoJSON نامعتبر است یا قابل تحلیل نیست: {e}")
                continue


# --- ج: محاسبه مدارس آسیب‌دیده ---
if all_shapely_polygons:
    try:
        # ادغام تمام پلی‌گون‌ها (دستی و GeoJSON)
        multi_poly = unary_union(all_shapely_polygons)
    except Exception as e:
        st.error(f"خطا در ادغام هندسه‌ها: {e}. اشکال GeoJSON یا ترسیمی را بررسی کنید.")
        multi_poly = None

if multi_poly:
    # تعیین مدارس داخل محدوده
    inside = []
    
    # استفاده از Shapely: Point(Lon, Lat)
    # اضافه کردن یک ستون موقت برای محاسبه
    filtered_df['is_inside'] = filtered_df.apply(
        lambda row: multi_poly.contains(Point(row["طول_جغرافیایی"], row["عرض_جغرافیایی"])),
        axis=1
    )
    
    result = filtered_df[filtered_df['is_inside'] == True].copy()
    
    if not result.empty:
        
        # --- گزارش خلاصه کلی ---
        total_schools = len(result)
        total_students = result['تعداد_دانش_آموز'].sum()
        total_teachers = result['تعداد_معلم'].sum()
        
        st.markdown("---")
        st.success(f"تعداد مدارس آسیب‌دیده در محدوده‌های انتخابی: **{total_schools}**")
        st.info(f"جمع کل دانش‌آموزان: **{total_students}** نفر | جمع کل معلمان: **{total_teachers}** نفر")
        
        st.markdown("### گزارش تفصیلی محدوده‌های آسیب‌دیده")

        col_report1, col_report2 = st.columns(2)

        with col_report1:
            st.subheader("تعداد مدارس به تفکیک مقطع")
            category_counts = result.groupby('دسته_مقطع').size().reset_index(name='تعداد مدارس')
            category_counts.columns = ['دسته مقطع', 'تعداد مدارس']
            st.dataframe(category_counts, use_container_width=True, hide_index=True)

        with col_report2:
            st.subheader("تعداد دانش‌آموزان به تفکیک جنسیت")
            gender_student_counts = result.groupby('جنسیت')['تعداد_دانش_آموز'].sum().reset_index(name='تعداد دانش‌آموز')
            gender_student_counts.columns = ['جنسیت', 'تعداد دانش‌آموز']
            st.dataframe(gender_student_counts, use_container_width=True, hide_index=True)
        
        st.markdown("---")
        st.subheader("لیست مدارس آسیب‌دیده")
        st.dataframe(
            result[["نام_مدرسه", "دسته_مقطع", "تعداد_دانش_آموز", "تعداد_معلم", "جنسیت", "عرض_جغرافیایی", "طول_جغرافیایی"]],
            width='stretch',
            hide_index=True
        )
        csv = result.to_csv(index=False, encoding="utf-8-sig").encode('utf-8-sig')
        st.download_button(
            "دانلود لیست (CSV)", 
            csv, 
            "مدارس_آسیب_دیده.csv", 
            "text/csv;charset=utf-8-sig"
        )
    else:
        st.warning("هیچ مدرسه‌ای در محدوده‌های انتخابی (دستی یا GeoJSON) یافت نشد.")
else:
    st.warning("لطفاً محدوده آسیب را روی نقشه ترسیم کنید یا فایل GeoJSON معتبری آپلود نمایید.")
