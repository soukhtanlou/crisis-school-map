import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
from shapely.geometry import Polygon, Point, shape, mapping
from shapely.ops import unary_union
import requests
import os
import json
import math

# ===========================
# Config / Defaults
# ===========================
DEFAULT_CENTER = [32.5, 53.0]  # مرکز تقریبی ایران (lat, lon)
DEFAULT_ZOOM = 5

st.set_page_config(page_title="ارزیابی خسارت مدارس", layout="wide")
st.title("ارزیابی خسارت مدارس در بحران")

# ===========================
# Session state initialization
# ===========================
if "map_center" not in st.session_state:
    st.session_state.map_center = DEFAULT_CENTER.copy()
if "map_zoom" not in st.session_state:
    st.session_state.map_zoom = DEFAULT_ZOOM
if "uploaded_geojson_data" not in st.session_state:
    st.session_state.uploaded_geojson_data = None
if "reset_counter" not in st.session_state:
    st.session_state.reset_counter = 0
if "last_analysis" not in st.session_state:
    st.session_state.last_analysis = None

# ===========================
# Utilities
# ===========================
def compute_center_and_zoom_from_bounds(bounds):
    """
    bounds: (minx, miny, maxx, maxy)  (lon_min, lat_min, lon_max, lat_max)
    return (center_lat, center_lon, zoom_estimate)
    Zoom heuristic: approximate based on max span degrees
    """
    minx, miny, maxx, maxy = bounds
    center_lon = (minx + maxx) / 2.0
    center_lat = (miny + maxy) / 2.0
    lon_span = abs(maxx - minx)
    lat_span = abs(maxy - miny)
    span = max(lon_span, lat_span)
    # heuristic mapping span -> zoom
    if span <= 0.02:
        zoom = 15
    elif span <= 0.1:
        zoom = 13
    elif span <= 0.5:
        zoom = 11
    elif span <= 2:
        zoom = 9
    elif span <= 6:
        zoom = 7
    elif span <= 20:
        zoom = 6
    else:
        zoom = 5
    return [center_lat, center_lon], zoom

def reset_app_state():
    """Reset relevant session state to initial conditions (map, uploaded layer, counters, last analysis)."""
    st.session_state.uploaded_geojson_data = None
    st.session_state.reset_counter += 1
    st.session_state.map_center = DEFAULT_CENTER.copy()
    st.session_state.map_zoom = DEFAULT_ZOOM
    st.session_state.last_analysis = None

# ===========================
# 1) Load schools.csv (with fallback dummy)
# ===========================
if not os.path.exists("schools.csv"):
    # create small dummy to allow app to run (same pattern as earlier)
    dummy = {
        'کد_مدرسه': [100013, 100014, 100015, 100016, 100017, 100018, 100019, 100020, 100021, 100022],
        'نام_مدرسه': ['دبستان شهدای گمنام', 'متوسطه اندیشه', 'فنی خوارزمی', 'دبستان آزادی', 'متوسطه فردوسی', 'پیش‌دبستانی شکوفه', 'مرکز مشاوران ۱', 'دبستان فجر', 'متوسطه الزهرا', 'دبستان هدف'],
        'نام_مدیر': ['م.رحیمی', 'ن.صادقی', 'ج.مرادی', 'ف.نظری', 'ع.حیدری', 'ز.مرادخانی', 'ا.اسدی', 'م.جعفری', 'س.کریمی', 'ج.نوری'],
        'مقطع_تحصیلی': ['دبستان دوره دوم', 'متوسطه اول', 'فنی و حرفه‌ای', 'دبستان دوره اول', 'متوسطه دوم', 'پیش دبستانی', 'مراکز مشاوره', 'دبستان دوره دوم', 'متوسطه دوم', 'دبستان دوره اول'],
        'تعداد_دانش_آموز': [415, 490, 280, 350, 520, 150, 0, 390, 470, 330],
        'تعداد_معلم': [29, 31, 30, 24, 34, 12, 18, 26, 30, 23],
        'جنسیت': ['مختلط', 'پسرانه', 'مختلط', 'دخترانه', 'پسرانه', 'دخترانه', 'مختلط', 'پسرانه', 'دخترانه', 'مختلط'],
        'عرض_جغرافیایی': [37.3321, 37.3105, 37.2889, 37.3450, 37.2995, 37.3012, 37.3208, 37.3155, 37.2770, 37.3050],
        'طول_جغرافیایی': [54.5103, 54.4552, 54.5408, 54.4901, 54.4253, 54.5005, 54.4852, 54.5303, 54.4601, 54.4050]
    }
    pd.DataFrame(dummy).to_csv("schools.csv", index=False, encoding="utf-8-sig")
    st.warning("فایل `schools.csv` پیدا نشد؛ یک فایل نمونه (dummy) ساخته شد برای تست اپ.")

@st.cache_data
def load_data():
    try:
        df = pd.read_csv("schools.csv", encoding="utf-8-sig")
    except Exception as e:
        st.error(f"خطا در خواندن schools.csv: {e}")
        return pd.DataFrame()

    # numeric conversions (fix typo from earlier)
    df['عرض_جغرافیایی'] = pd.to_numeric(df.get('عرض_جغرافیایی'), errors='coerce')
    df['طول_جغرافیایی'] = pd.to_numeric(df.get('طول_جغرافیایی'), errors='coerce')
    df['تعداد_دانش_آموز'] = pd.to_numeric(df.get('تعداد_دانش_آموز'), errors='coerce').fillna(0).astype(int)
    df['تعداد_معلم'] = pd.to_numeric(df.get('تعداد_معلم'), errors='coerce').fillna(0).astype(int)

    # drop invalid coords
    df = df.dropna(subset=['عرض_جغرافیایی', 'طول_جغرافیایی'])

    # categorize grade
    def categorize_grade(grade):
        grade = str(grade)
        if 'پیش' in grade or 'دبستان' in grade:
            return 'ابتدایی/دبستان'
        elif 'متوسطه' in grade:
            return 'متوسطه'
        elif 'فنی' in grade or 'کار' in grade:
            return 'فنی و حرفه‌ای'
        else:
            return 'مراکز/سایر'

    df['دسته_مقطع'] = df['مقطع_تحصیلی'].apply(categorize_grade)
    return df

df = load_data()
if df.empty:
    st.error("دادهٔ مدارس خالی است. لطفاً فایل schools.csv را تهیه کنید.")
    st.stop()

# ===========================
# 2) Sidebar filters and upload
# ===========================
st.sidebar.header("تنظیمات فیلتر و لایه خسارت")

grade_categories = sorted(df['دسته_مقطع'].unique().tolist())
selected_categories = st.sidebar.multiselect(
    "فیلتر بر اساس مقطع تحصیلی:",
    options=grade_categories,
    default=grade_categories
)

genders = sorted(df['جنسیت'].unique().tolist())
selected_genders = st.sidebar.multiselect(
    "فیلتر بر اساس جنسیت:",
    options=genders,
    default=genders
)

# upload GeoJSON (optional)
st.sidebar.markdown("---")
st.sidebar.header("آپلود لایه خسارت")
geojson_file = st.sidebar.file_uploader("آپلود GeoJSON (Polygon/MultiPolygon)", type=["geojson", "json"])

# reset button
st.sidebar.markdown("---")
if st.sidebar.button("پاک کردن محدوده‌ها و ریست نقشه"):
    reset_app_state()
    st.experimental_rerun()

# ===========================
# 3) Apply filters
# ===========================
filtered_df = df[
    df['دسته_مقطع'].isin(selected_categories) &
    df['جنسیت'].isin(selected_genders)
].copy()

if filtered_df.empty:
    st.warning("با فیلترهای فعلی هیچ مدرسه‌ای برای نمایش وجود ندارد.")
    st.stop()

st.info(f"مدارس نمایش داده شده: {len(filtered_df)} / {len(df)}")

# ===========================
# 4) Handle geojson upload (store in session and auto-zoom)
# ===========================
if geojson_file:
    try:
        geojson_file.seek(0)
        geojson_obj = json.load(geojson_file)
        st.session_state.uploaded_geojson_data = geojson_obj
        st.sidebar.success("GeoJSON با موفقیت بارگذاری شد.")
        # compute bounds and set center/zoom
        try:
            # aggregate shapes to get overall bounds
            feats = []
            if geojson_obj.get('type') == 'FeatureCollection':
                feats = geojson_obj.get('features', [])
            elif geojson_obj.get('type') == 'Feature':
                feats = [geojson_obj]
            elif geojson_obj.get('type') in ('Polygon','MultiPolygon'):
                feats = [{'geometry': geojson_obj}]
            all_shapes = []
            for f in feats:
                geom = f.get('geometry')
                if geom:
                    s = shape(geom)
                    all_shapes.append(s)
            if all_shapes:
                unioned = unary_union(all_shapes)
                bounds = unioned.bounds  # (minx, miny, maxx, maxy) -> (lon_min, lat_min, lon_max, lat_max)
                center, zoom = compute_center_and_zoom_from_bounds(bounds)
                st.session_state.map_center = center
                st.session_state.map_zoom = zoom
                # rerun to re-render map centered on uploaded layer (safe)
                st.experimental_rerun()
        except Exception:
            # if computing bounds failed, we still keep the uploaded data but don't auto-zoom
            pass
    except Exception as e:
        st.sidebar.error(f"خطا در خواندن GeoJSON: {e}")
        st.session_state.uploaded_geojson_data = None

# ===========================
# 5) Build folium map
# ===========================
m = folium.Map(location=st.session_state.map_center, zoom_start=st.session_state.map_zoom, tiles="OpenStreetMap")

# category layers
category_colors = {
    'ابتدایی/دبستان': '#28a745',
    'متوسطه': '#007bff',
    'فنی و حرفه‌ای': '#ffc107',
    'مراکز/سایر': '#dc3545'
}
category_layers = {}
for cat in grade_categories:
    layer = folium.FeatureGroup(name=f"دسته: {cat}", show=True)
    category_layers[cat] = layer
    m.add_child(layer)

# add markers
for _, r in filtered_df.iterrows():
    lat, lon = r['عرض_جغرافیایی'], r['طول_جغرافیایی']
    cat = r['دسته_مقطع']
    color = category_colors.get(cat, '#6c757d')
    tooltip = (
        f"<b>{r.get('نام_مدرسه','-')}</b><br>"
        f"مقطع: {r.get('مقطع_تحصیلی','-')}<br>"
        f"مدیر: {r.get('نام_مدیر','-')}<br>"
        f"دانش‌آموز: {r.get('تعداد_دانش_آموز',0)} | معلم: {r.get('تعداد_معلم',0)}"
    )
    folium.CircleMarker(location=[lat, lon], radius=6, color=color, fill=True, fillColor=color, tooltip=tooltip).add_to(category_layers[cat])

# add uploaded geojson (if any)
if st.session_state.uploaded_geojson_data:
    folium.GeoJson(
        st.session_state.uploaded_geojson_data,
        name='لایهٔ بارگذاری‌شده (GeoJSON)',
        style_function=lambda feat: {
            'fillColor': '#ff000077',
            'color': '#ff0000',
            'weight': 2,
            'fillOpacity': 0.35
        },
        tooltip=folium.GeoJsonTooltip(fields=[], aliases=[], labels=False),
    ).add_to(m)

# always enable Draw plugin so user can draw multiple polygons (regardless of upload)
from folium.plugins import Draw
Draw(
    draw_options={
        'polyline': False,
        'rectangle': False,
        'circle': False,
        'marker': False,
        'circlemarker': False,
    },
    edit_options={'edit': True, 'remove': True}
).add_to(m)

folium.LayerControl().add_to(m)

# display map with a key that includes reset_counter to force re-render on reset
map_key = f"map_{st.session_state.reset_counter}"
st.markdown("### نقشه مدارس و محدوده‌های آسیب — (می‌توانید چند محدوده ترسیم کنید یا GeoJSON آپلود کنید)")
map_data = st_folium(m, width=1200, height=600, key=map_key)

# ===========================
# 6) Process polygons (manual drawings + uploaded geojson)
# ===========================
all_polygons = []

# manual drawings from folium Draw (map_data["all_drawings"]) - may be lat/lon pairs
if map_data and map_data.get("all_drawings"):
    drawings = map_data["all_drawings"]
    for d in drawings:
        geom = d.get("geometry")
        if not geom:
            continue
        if geom.get("type") == "Polygon":
            coords_latlon = geom.get("coordinates")[0]  # list of [lat, lon] pairs from draw plugin
            # convert to (lon, lat)
            try:
                coords_lonlat = [[pt[1], pt[0]] for pt in coords_latlon]
                poly = Polygon(coords_lonlat)
                if poly.is_valid and poly.area > 0:
                    all_polygons.append(poly)
            except Exception:
                continue
        elif geom.get("type") == "MultiPolygon":
            for poly_coords in geom.get("coordinates"):
                coords_latlon = poly_coords[0]
                coords_lonlat = [[pt[1], pt[0]] for pt in coords_latlon]
                try:
                    poly = Polygon(coords_lonlat)
                    if poly.is_valid and poly.area > 0:
                        all_polygons.append(poly)
                except Exception:
                    continue

# uploaded GeoJSON polygons
if st.session_state.uploaded_geojson_data:
    geojson_obj = st.session_state.uploaded_geojson_data
    feats = []
    if geojson_obj.get('type') == 'FeatureCollection':
        feats = geojson_obj.get('features', [])
    elif geojson_obj.get('type') == 'Feature':
        feats = [geojson_obj]
    elif geojson_obj.get('type') in ('Polygon','MultiPolygon'):
        feats = [{'geometry': geojson_obj}]
    for f in feats:
        geom = f.get('geometry')
        if not geom:
            continue
        try:
            s = shape(geom)  # shape gives correct lon/lat ordering
            if s.geom_type == 'Polygon':
                all_polygons.append(s)
            elif s.geom_type == 'MultiPolygon':
                for g in s.geoms:
                    all_polygons.append(g)
        except Exception:
            continue

# if we have polygons, union them into multi_poly for point-in-polygon tests
multi_poly = None
if all_polygons:
    try:
        multi_poly = unary_union(all_polygons)
    except Exception as e:
        st.warning(f"خطا در ادغام هندسه‌ها: {e}")
        multi_poly = None

# ===========================
# 7) Analysis: find schools inside polygons
# ===========================
if multi_poly is not None:
    # ensure no SettingWithCopyWarning: use .loc
    if 'is_inside' in filtered_df.columns:
        filtered_df = filtered_df.drop(columns=['is_inside'])
    filtered_df.loc[:, 'is_inside'] = filtered_df.apply(
        lambda row: bool(multi_poly.contains(Point(row['طول_جغرافیایی'], row['عرض_جغرافیایی']))),
        axis=1
    )
    result = filtered_df[filtered_df['is_inside']].copy()
    st.session_state.last_analysis = {'count': len(result), 'df': result}
else:
    result = pd.DataFrame()  # empty

# ===========================
# 8) Output: summary metrics, tables, download
# ===========================

if multi_poly is not None:
    if not result.empty:
        total_schools = len(result)
        total_students = int(result['تعداد_دانش_آموز'].sum())
        total_teachers = int(result['تعداد_معلم'].sum())

        st.markdown("---")
        st.subheader("نتایج تحلیل محدوده(ها)")

        col1, col2, col3 = st.columns(3)
        col1.metric("مدارس داخل محدوده", total_schools)
        col2.metric("کل دانش‌آموزان تحت تأثیر", total_students)
        col3.metric("کل معلمان تحت تأثیر", total_teachers)

        st.warning("⚠️ توجه: نتایج مبتنی بر همپوشانی مکانی هستند و نیاز به تأیید میدانی دارند.")

        st.markdown("### گزارش تفصیلی")

        c1, c2 = st.columns(2)
        with c1:
            cat_counts = result.groupby('دسته_مقطع').size().reset_index(name='تعداد مدارس')
            st.dataframe(cat_counts, use_container_width=True, hide_index=True)

        with c2:
            gender_students = result.groupby('جنسیت')['تعداد_دانش_آموز'].sum().reset_index(name='تعداد دانش‌آموز')
            st.dataframe(gender_students, use_container_width=True, hide_index=True)

        st.markdown("---")
        st.subheader("لیست مدارس آسیب‌دیده")

        st.dataframe(
            result[["کد_مدرسه","نام_مدرسه","دسته_مقطع","جنسیت","تعداد_دانش_آموز","تعداد_معلم","عرض_جغرافیایی","طول_جغرافیایی"]],
            use_container_width=True,
            hide_index=True
        )

        csv = result.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")
        st.download_button(
            "دانلود CSV لیست مدارس آسیب‌دیده",
            csv,
            "مدارس_آسیب_دیده.csv",
            "text/csv;charset=utf-8-sig"
        )

    else:  # ← وقتی هیچ مدرسه‌ای در محدوده نبوده
        st.warning("هیچ مدرسه‌ای در محدوده‌های انتخابی یافت نشد.")

else:  # ← وقتی هیچ محدوده (پلی‌گون یا GeoJSON) وجود ندارد
    st.session_state.last_analysis = None
    st.info("برای تولید گزارش: یک یا چند محدوده روی نقشه ترسیم کنید یا یک فایل GeoJSON آپلود نمایید.")

# EOF
