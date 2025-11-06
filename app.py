import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
from shapely.geometry import Polygon, Point, mapping, shape
from shapely.ops import unary_union
import requests
import os
import json 
import io 

# تنظیمات صفحه
st.set_page_config(page_title="ارزیابی خسارت مدارس", layout="wide")
st.title("ارزیابی خسارت مدارس در بحران")

# --- چک کردن فایل و بارگذاری داده‌ها ---

# فرض می‌کنیم schools.csv وجود دارد. اگر نه، پیام خطا نمایش داده می‌شود.
if not os.path.exists("schools.csv"):
    # ایجاد یک فایل dummy برای اجرای اولیه در محیط‌های بدون دسترسی به فایل سیستم محلی
    try:
        # استفاده از داده‌های فارسی‌ای که کاربر قبلاً درخواست کرده بود
        data = {
            'کد_مدرسه': [100013, 100014, 100015, 100016, 100017, 100018, 100019, 100020, 100021, 100022],
            'نام_مدرسه': ['دبستان شهدای گمنام', 'متوسطه اندیشه', 'فنی خوارزمی', 'دبستان آزادی', 'متوسطه فردوسی', 'پیش‌دبستانی شکوفه', 'مرکز مشاوران ۱', 'دبستان فجر', 'متوسطه الزهرا', 'دبستان هدف'],
            'نام_مدیر': ['م.رحیمی', 'ن.صادقی', 'ج.مرادی', 'ف.نظری', 'ع.حیدری', 'ز.مرادخانی', 'ا.اسدی', 'م.جعفری', 'س.کریمی', 'ج.نوری'],
            'مقطع_تحصیلی': ['دبستان دوره دوم', 'متوسطه اول', 'فنی و حرفه‌ای', 'دبستان دوره اول', 'متوسطه دوم', 'پیش دبستانی', 'مراکز مشاوره', 'دبستان دوره دوم', 'متوسطه دوم', 'دبستان دوره اول'],
            'تعداد_دانش_آموز': [415, 490, 280, 350, 520, 150, 0, 390, 470, 330],
            'تعداد_معلم': [29, 31, 30, 24, 34, 12, 18, 26, 30, 23],
            'جنسیت': ['مختلط', 'پسرانه', 'مختلط', 'دخترانه', 'پسرانه', 'دخترانه', 'مختلط', 'پسرانه', 'دخترانه', 'مختلط'],
            # مختصات‌های نزدیک گلستان
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

        df['دسته_مقطع'] = df['مقطع_تحصیلی'].astype(str).apply(categorize_grade)
        return df
    except Exception as e:
        st.error(f"خطا در خواندن فایل: {e}")
        return pd.DataFrame()

df = load_data()
if df.empty:
    st.warning("هیچ داده معتبری در فایل نیست.")
    st.stop()

# --- ۱. فیلترهای جانبی (Sidebar) ---

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

# --- NEW: آپلود GeoJSON برای محدوده آسیب ---
st.sidebar.markdown("---")
st.sidebar.header("تعیین محدوده آسیب (GeoJSON)")
geojson_file = st.sidebar.file_uploader(
    "آپلود فایل GeoJSON (Polygon/MultiPolygon)",
    type=["geojson", "json"],
    help="برای مشخص کردن محدوده آسیب‌دیده از طریق فایل."
)
st.sidebar.caption("محدوده آسیب می‌تواند همزمان از طریق فایل و ترسیم دستی روی نقشه مشخص شود.")


if filtered_df.empty:
    st.warning("با تنظیمات فیلتر فعلی، هیچ مدرسه معتبری برای نمایش وجود ندارد.")
    st.stop()

st.info(f"تعداد کل مدارس نمایش داده شده: **{len(filtered_df)}** از **{len(df)}**")

# --- ۲. نقشه و لایه بندی ---

if 'initial_map_location' not in st.session_state:
    # تغییر مختصات اولیه به گلستان (گرگان) برای همخوانی با GeoJSON سیل
    st.session_state.initial_map_location = [37.3000, 54.4600] 
    st.session_state.initial_map_zoom = 11

m = folium.Map(
    location=st.session_state.initial_map_location, 
    zoom_start=st.session_state.initial_map_zoom, 
    tiles="OpenStreetMap"
)

category_colors = {
    'ابتدایی/دبستان': '#28a745',       # سبز
    'متوسطه': '#007bff',              # آبی
    'فنی و حرفه‌ای': '#ffc107',       # زرد/نارنجی
    'مراکز/سایر': '#dc3545',          # قرمز 
    'نامشخص': '#6c757d'              # خاکستری
}

# گروه لایه‌های مدارس
school_layer_group = folium.FeatureGroup(name="نقاط مدارس", show=True).add_to(m)

# اضافه کردن نقاط مدارس به نقشه
for _, row in filtered_df.iterrows():
    lat, lon = row['عرض_جغرافیایی'], row['طول_جغرافیایی']
    category = row['دسته_مقطع']
    
    color = category_colors.get(category, '#6c757d')
    
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
    ).add_to(school_layer_group) # اضافه کردن به گروه مدارس

# ----------------------------------------------------
# --- نمایش GeoJSON آپلود شده روی نقشه (محل اعمال تغییرات) ---
# ----------------------------------------------------

uploaded_geojson_data = None
if geojson_file:
    # بازگرداندن نشانگر فایل به ابتدای آن برای استفاده مجدد 
    geojson_file.seek(0)
    
    try:
        # GeoJSON را به صورت متنی می‌خوانیم و بارگذاری می‌کنیم
        geojson_data_str = io.TextIOWrapper(geojson_file, encoding='utf-8').read()
        uploaded_geojson_data = json.loads(geojson_data_str)
        geojson_file.seek(0) # بازگرداندن نشانگر برای استفاده مجدد در بخش تحلیل
    except Exception as e:
        st.error(f"خطا در خواندن محتوای GeoJSON: {e}")
        uploaded_geojson_data = None
    
    if uploaded_geojson_data:
        # **اضافه کردن GeoJSON به نقشه به عنوان یک لایه Folium**
        folium.GeoJson(
            uploaded_geojson_data,
            name='محدوده آسیب (GeoJSON)',
            style_function=lambda x: {
                'fillColor': '#dc3545',  # قرمز
                'color': '#dc3545',
                'weight': 3, # ضخامت بیشتر برای بهتر دیده شدن
                'fillOpacity': 0.3
            }
        ).add_to(m)
        
        # تنظیم مرکز نقشه برای زوم روی محدوده آسیب
        try:
            geo_shape_obj = shape(uploaded_geojson_data)
            if geo_shape_obj.bounds:
                centroid = geo_shape_obj.centroid
                st.session_state.initial_map_location = [centroid.y, centroid.x]
                st.session_state.initial_map_zoom = 11
                m.location = st.session_state.initial_map_location
                m.zoom_start = st.session_state.initial_map_zoom
        except Exception:
            pass

# ----------------------------------------------------

# ابزار کشیدن (Draw) با فعال بودن ویرایش
from folium.plugins import Draw
Draw(
    draw_options={
        'polyline':False,
        'rectangle':False,
        'circle':False,
        'marker':False,
        'circlemarker':False,
    }, 
    edit_options={'edit':True, 'remove':True} # ویرایش و حذف فعال است
).add_to(m)

folium.LayerControl().add_to(m)


# --- ۳. جستجوی مکان (برای جابجایی نقشه) ---

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

st.markdown("### نقشه مدارس (ترسیم محدوده آسیب و ابزارها)")

map_data = st_folium(m, width=1200, height=600, key="folium_map_v3") # تغییر کلید برای رندر مجدد نقشه


# --- ۴. تحلیل تمامی پلی‌گون‌های ترسیم شده و GeoJSON آپلود شده ---

# لیست برای ذخیره تمام اشیاء Shapely Polygon از هر دو منبع
all_shapely_polygons = []

# --- الف: پردازش پلی‌گون‌های دستی ترسیم شده (Manual Drawings) ---
if map_data and map_data.get("all_drawings"):
    
    # فیلتر کردن تنها پلی‌گون‌ها از ابزار ترسیم
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


# --- ب: پردازش فایل GeoJSON آپلود شده (GeoJSON Upload) ---
if geojson_file:
    # از داده‌هایی که در بخش ۲ خوانده و در uploaded_geojson_data ذخیره شد، استفاده می‌کنیم
    if uploaded_geojson_data:
        geojson_data = uploaded_geojson_data
        
        # هندل کردن FeatureCollection، Feature، و Geometry
        features = []
        if geojson_data.get('type') == 'FeatureCollection':
            features = geojson_data.get('features', [])
        elif geojson_data.get('type') == 'Feature':
            features = [geojson_data]
        elif geojson_data.get('type') in ['Polygon', 'MultiPolygon']:
            # اگر خود Geometry object باشد
            features = [{'geometry': geojson_data}]
            
        
        polygons_from_file_count = 0
        for feature in features:
            geometry = feature.get('geometry')
            if geometry and geometry.get('type') in ['Polygon', 'MultiPolygon']:
                
                # برای Polygon: مختصات یک آرایه از حلقه‌ها است (ما حلقه بیرونی را می‌خواهیم)
                if geometry['type'] == 'Polygon':
                    # Polygon coordinates are [exterior_ring, interior_ring1, ...]
                    coords = geometry['coordinates'][0] # فقط حلقه بیرونی را می‌گیریم
                    all_shapely_polygons.append(Polygon(coords))
                    polygons_from_file_count += 1
                
                # برای MultiPolygon: آرایه‌ای از مختصات پلی‌گون‌ها است
                elif geometry['type'] == 'MultiPolygon':
                    for poly_coords in geometry['coordinates']:
                        # MultiPolygon coordinates: [[[ext_ring, int_ring, ...], ...], ...]
                        coords = poly_coords[0] # حلقه بیرونی هر پلی‌گون را می‌گیریم
                        all_shapely_polygons.append(Polygon(coords))
                        polygons_from_file_count += 1
                        
        
        if polygons_from_file_count > 0:
            st.success(f"فایل GeoJSON با موفقیت بارگذاری شد و شامل {polygons_from_file_count} پلی‌گون برای تحلیل است.")
              
    else:
        # اگر GeoJSON آپلود شده ولی خوانده نشده
        st.error("محتوای GeoJSON معتبر نیست و برای تحلیل قابل استفاده نیست.")


# --- ج: محاسبه و نمایش نتایج نهایی ---

if all_shapely_polygons:
    try:
        # ادغام تمام پلی‌گون‌ها (دستی و GeoJSON) برای ایجاد یک هندسه واحد
        multi_poly = unary_union(all_shapely_polygons)
    except Exception as e:
        st.warning(f"اشکالی در ایجاد هندسه نهایی (ادغام پلی‌گون‌ها) وجود دارد: {e}. لطفاً شکل‌ها را بررسی کنید.")
        st.stop()
        
    # محاسبه نقاط داخل هندسه (MultiPolygon)
    inside = []
    # Shapely از ترتیب (Lon, Lat) استفاده می‌کند: Point(طول_جغرافیایی, عرض_جغرافیایی)
    for index, row in filtered_df.iterrows():
        point = Point(row["طول_جغرافیایی"], row["عرض_جغرافیایی"])
        if multi_poly.contains(point):
            # اضافه کردن یک ستون جدید برای مشخص کردن مدارس آسیب دیده
            row['آسیب_دیده'] = True 
            inside.append(row)
        else:
            row['آسیب_دیده'] = False

    # برای نمایش مدارس روی نقشه بعد از تحلیل، dataframe اصلی را به روز می‌کنیم
    # این قسمت در حال حاضر فقط برای پر کردن ستون 'آسیب_دیده' است که در تحلیل نهایی استفاده نشد
    # اما اگر لازم باشد، می‌توان برای فیلتر یا رنگ‌آمیزی دوباره مدارس استفاده کرد.
    filtered_df['آسیب_دیده'] = filtered_df.apply(
        lambda row: multi_poly.contains(Point(row["طول_جغرافیایی"], row["عرض_جغرافیایی"])) 
        if multi_poly else False, 
        axis=1
    )


    if inside:
        result = pd.DataFrame(inside)
        
        # --- گزارش خلاصه کلی ---
        total_schools = len(inside)
        total_students = result['تعداد_دانش_آموز'].sum()
        total_teachers = result['تعداد_معلم'].sum()
        
        st.success(f"مدارس در محدوده‌های انتخابی: **{total_schools}**")
        st.info(f"جمع کل دانش‌آموزان: **{total_students}** | جمع کل معلمان: **{total_teachers}**")
        
        st.markdown("---")
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
        csv = result.to_csv(index=False, encoding="utf-8-sig").encode()
        st.download_button("دانلود لیست (CSV)", csv, "مدارس_آسیب_دیده.csv", "text/csv")
    else:
        st.warning("هیچ مدرسه‌ای در محدوده‌های انتخابی (اعم از دستی یا GeoJSON) نیست.")
else:
    st.warning("لطفاً یک یا چند پلی‌گون روی نقشه ترسیم کنید یا فایل GeoJSON آپلود نمایید.")
