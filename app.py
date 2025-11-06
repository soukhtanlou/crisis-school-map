import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
import json
import io
import os
from shapely.geometry import Point, shape
from io import BytesIO

# --- تنظیمات صفحه ---
st.set_page_config(page_title="ارزیابی خسارت مدارس", layout="wide")
st.title("ارزیابی خسارت مدارس در بحران")

# --- متغیرهای سراسری و ثابت‌ها ---
# لیست مقاطع تحصیلی به زبان فارسی برای استفاده در فیلترها و گزارش
EDUCATION_LEVELS = ["ابتدایی", "متوسطه اول", "متوسطه دوم", "فنی و حرفه‌ای"]

# --- توابع کمکی ---

# تابع برای تحلیل مکانی: بررسی اینکه آیا نقطه (مدرسه) داخل پلی‌گون (محدوده آسیب) است.
@st.cache_data
def check_for_overlap(df_schools, damage_polygons):
    """
    بررسی می‌کند کدام مدارس (نقاط) در داخل پلی‌گون‌های آسیب‌دیده قرار دارند.
    از shapely برای محاسبات هندسی استفاده می‌شود.
    """
    
    # اطمینان از تعریف ستون damage_status قبل از استفاده
    df_schools['damage_status'] = 'سالم' 

    # اگر هیچ پلی‌گونی تعریف نشده باشد، همه مدارس سالم هستند.
    if not damage_polygons:
        return df_schools
    
    # ساختن اشیاء Point برای مدارس
    schools_points = [
        Point(row['longitude'], row['latitude'])
        for index, row in df_schools.iterrows()
    ]
    
    # تعریف ستون جدید برای وضعیت خسارت
    is_damaged = [False] * len(df_schools)

    # بررسی برای هر مدرسه که آیا داخل هر یک از پلی‌گون‌های آسیب‌دیده هست یا خیر
    for i, school_point in enumerate(schools_points):
        for damage_polygon in damage_polygons:
            if school_point.within(damage_polygon):
                is_damaged[i] = True
                break  # اگر در یک محدوده آسیب بود، دیگر نیازی به بررسی بقیه نیست

    # به‌روزرسانی ستون damage_status در DataFrame
    df_schools['damage_status'] = ['آسیب‌دیده' if damaged else 'سالم' for damaged in is_damaged]

    return df_schools

# تابع برای تبدیل GeoJSON به لیست آبجکت‌های Shapely Polygon
def extract_shapely_polygons(geojson_data):
    """
    فایل GeoJSON یا JSON ترسیمی را می‌گیرد و آن را به لیست اشیاء Shapely Polygon تبدیل می‌کند.
    """
    polygons = []
    
    # اگر داده از Draw Tool باشد
    if isinstance(geojson_data, dict) and 'all_drawings' in geojson_data:
        features = geojson_data['all_drawings']
    # اگر داده یک فایل GeoJSON آپلود شده باشد
    elif isinstance(geojson_data, dict) and 'features' in geojson_data:
        features = geojson_data['features']
    else:
        return []

    for feature in features:
        if feature['geometry']['type'] in ['Polygon', 'MultiPolygon']:
            try:
                # استفاده از shapely.geometry.shape برای ساخت شیء هندسی
                geom = shape(feature['geometry'])
                if geom.geom_type == 'Polygon':
                    polygons.append(geom)
                elif geom.geom_type == 'MultiPolygon':
                    polygons.extend(list(geom.geoms))
            except Exception as e:
                st.error(f"خطا در پردازش GeoJSON: {e}")
                
    return polygons

# تابع برای ایجاد فایل CSV قابل دانلود
def to_excel(df):
    """تبدیل DataFrame به فایل اکسل در حافظه (BytesIO)"""
    output = BytesIO()
    writer = pd.ExcelWriter(output, engine='xlsxwriter')
    df.to_excel(writer, index=False, sheet_name='مدارس آسیب‌دیده')
    writer.close()
    processed_data = output.getvalue()
    return processed_data

# --- بارگذاری داده‌های ورودی ---
def load_data():
    """تلاش برای بارگذاری فایل اکسل/CSV اطلاعات مدارس."""
    # اگر داده در حالت سشن ذخیره نشده، از یک فایل نمونه استفاده شود (برای اجرا بدون آپلود)
    if 'school_data' not in st.session_state:
        st.info("لطفاً فایل Excel/CSV حاوی اطلاعات مدارس را آپلود کنید.")
        
        # ساخت یک DataFrame نمونه (Mock Data) برای نمایش اولیه
        mock_data = {
            'school_code': [1001, 1002, 1003, 1004, 1005],
            'name': ['مدرسه الف', 'مدرسه ب', 'مدرسه ج', 'مدرسه د', 'مدرسه ه'],
            'latitude': [35.70, 35.71, 35.75, 35.80, 35.78],
            'longitude': [51.40, 51.45, 51.35, 51.50, 51.42],
            'level': ["ابتدایی", "متوسطه اول", "متوسطه دوم", "ابتدایی", "متوسطه اول"],
            'type': ["پسرانه", "دخترانه", "پسرانه", "دخترانه", "پسرانه"],
            'students_boys': [150, 0, 180, 0, 120],
            'students_girls': [0, 160, 0, 170, 0],
            'teachers': [12, 10, 15, 11, 8],
        }
        st.session_state['school_data'] = pd.DataFrame(mock_data)

    return st.session_state['school_data']

# --- UI و فیلترها ---

def setup_sidebar(df):
    """تنظیم فیلترهای نوار کناری."""
    st.sidebar.header("تنظیمات و فیلترها")

    # آپلود فایل
    uploaded_file = st.sidebar.file_uploader(
        "بارگذاری فایل اطلاعات مدارس (Excel/CSV)", 
        type=['csv', 'xlsx'], 
        key='file_uploader'
    )
    
    if uploaded_file is not None:
        try:
            if uploaded_file.name.endswith('.csv'):
                df = pd.read_csv(uploaded_file)
            elif uploaded_file.name.endswith('.xlsx'):
                df = pd.read_excel(uploaded_file)
                
            st.session_state['school_data'] = df
            st.sidebar.success("داده‌ها با موفقیت بارگذاری شدند.")
        except Exception as e:
            st.sidebar.error(f"خطا در خواندن فایل: {e}")
            
    # فیلترهای نمایش
    st.sidebar.markdown("---")
    selected_levels = st.sidebar.multiselect(
        "فیلتر مقطع تحصیلی",
        options=df['level'].unique().tolist() if 'level' in df.columns else EDUCATION_LEVELS,
        default=df['level'].unique().tolist() if 'level' in df.columns else EDUCATION_LEVELS
    )

    selected_types = st.sidebar.multiselect(
        "فیلتر جنسیت",
        options=df['type'].unique().tolist() if 'type' in df.columns else ["پسرانه", "دخترانه", "مختلط"],
        default=df['type'].unique().tolist() if 'type' in df.columns else ["پسرانه", "دخترانه", "مختلط"]
    )
    
    st.session_state['selected_levels'] = selected_levels
    st.session_state['selected_types'] = selected_types

    # فیلتر کردن DataFrame
    if 'level' in df.columns and 'type' in df.columns:
        filtered_df = df[
            (df['level'].isin(selected_levels)) & 
            (df['type'].isin(selected_types))
        ].copy()
    else:
        filtered_df = df.copy() # نمایش همه اگر ستون‌ها موجود نباشد

    return filtered_df

# --- منطق اصلی نقشه و نمایش ---

def main_map_and_analysis(filtered_df):
    """
    نمایش نقشه، ابزارهای ترسیم و اجرای تحلیل مکانی.
    """
    
    if filtered_df.empty:
        st.warning("داده‌ای برای نمایش با فیلترهای انتخابی وجود ندارد.")
        return

    # میانگین مختصات برای مرکز نقشه (در صورت وجود ستون‌ها)
    if 'latitude' in filtered_df.columns and 'longitude' in filtered_df.columns:
        center_lat = filtered_df['latitude'].mean()
        center_lon = filtered_df['longitude'].mean()
    else:
        st.error("ستون‌های 'latitude' و 'longitude' در داده‌های مدارس پیدا نشدند.")
        # مختصات پیش‌فرض (تهران)
        center_lat = 35.70
        center_lon = 51.40


    # --- ساخت نقشه Folium ---
    m = folium.Map(location=[center_lat, center_lon], zoom_start=11)

    # افزودن لایه Draw برای ترسیم محدوده آسیب
    from folium.plugins import Draw
    draw = Draw(
        export=True, 
        filename='damage_area.geojson',
        position='topleft', 
        draw_options={
            'polygon': {'shapeOptions': {'color': '#FF0000', 'fillColor': '#FF0000', 'fillOpacity': 0.3}},
            'marker': False,
            'circlemarker': False,
            'polyline': False,
            'rectangle': False,
            'circle': False
        },
        edit_options={'edit': True, 'remove': True}
    )
    draw.add_to(m)

    # افزودن نقاط مدارس به نقشه
    for index, row in filtered_df.iterrows():
        popup_html = f"""
        <b>نام:</b> {row.get('name', 'N/A')}<br>
        <b>کد:</b> {row.get('school_code', 'N/A')}<br>
        <b>مقطع:</b> {row.get('level', 'N/A')}<br>
        <b>جنسیت:</b> {row.get('type', 'N/A')}<br>
        <b>دانش‌آموزان:</b> {row.get('students_boys', 0) + row.get('students_girls', 0)}
        """
        
        folium.CircleMarker(
            location=[row['latitude'], row['longitude']],
            radius=5,
            color='blue',
            fill=True,
            fill_color='blue',
            fill_opacity=0.7,
            popup=popup_html
        ).add_to(m)

    st.subheader("نقشه تعاملی مدارس و محدوده آسیب")
    
    # --- ابزار آپلود GeoJSON در ستون کناری ---
    with st.sidebar.expander("آپلود محدوده آسیب (GeoJSON)"):
        geojson_upload = st.file_uploader(
            "فایل GeoJSON حاوی پلی‌گون‌های آسیب را آپلود کنید",
            type=['geojson']
        )
        
        if geojson_upload:
            try:
                geojson_data = json.load(geojson_upload)
                st.session_state['damage_geojson'] = geojson_data
                st.sidebar.success("فایل GeoJSON با موفقیت بارگذاری شد.")
            except Exception as e:
                st.sidebar.error(f"خطا در خواندن GeoJSON: {e}")

    # نمایش نقشه Streamlit-Folium و دریافت داده‌های ترسیم شده
    map_result = st_folium(
        m, 
        # استفاده از 'stretch' به جای use_container_width=True برای رفع هشدار منسوخ شدن
        width="stretch", 
        height=500, 
        key="school_map"
    )

    # --- تحلیل مکانی ---

    # 1. استخراج پلی‌گون‌ها از داده‌های ترسیم شده
    drawn_polygons_geojson = map_result.get("all_drawings")
    
    # 2. استخراج پلی‌گون‌ها از فایل آپلود شده (اگر وجود دارد)
    uploaded_geojson = st.session_state.get('damage_geojson', None)

    # ترکیب و تبدیل به Shapely Polygons
    all_polygons_shapely = []
    
    if drawn_polygons_geojson:
        all_polygons_shapely.extend(extract_shapely_polygons(drawn_polygons_geojson))
        
    if uploaded_geojson:
        # اگر کاربر هم ترسیم کرده و هم آپلود، فقط از ترسیمی استفاده می‌کنیم مگر اینکه واضح باشد
        # در اینجا، اگر فایل آپلود شده باشد، آن را به لیست پلی‌گون‌ها اضافه می‌کنیم
        all_polygons_shapely.extend(extract_shapely_polygons(uploaded_geojson))
        
    if all_polygons_shapely:
        # اگر پلی‌گونی وجود داشت، تحلیل مکانی را انجام دهید
        df_analyzed = check_for_overlap(filtered_df, all_polygons_shapely)
        
        # نمایش پلی‌گون‌های آسیب‌دیده روی نقشه
        for polygon in all_polygons_shapely:
             # تبدیل shapely polygon به GeoJSON برای نمایش در Folium
            geojson_to_add = folium.GeoJson(polygon.wkt, style_function=lambda x: {
                'fillColor': '#FF0000', 
                'color': '#FF0000', 
                'weight': 3, 
                'fillOpacity': 0.3
            })
            geojson_to_add.add_to(m)
            
        # باید نقشه را دوباره نمایش دهیم تا پلی‌گون‌ها ظاهر شوند
        st.subheader("نقشه نهایی (با محدوده آسیب)")
        st_folium(m, width="stretch", height=500, key="final_map")
        
        return df_analyzed
    
    else:
        st.info("لطفاً محدوده آسیب‌دیده را روی نقشه ترسیم کنید یا فایل GeoJSON آن را آپلود نمایید.")
        # اگر پلی‌گونی وجود نداشت، وضعیت خسارت را به حالت پیش‌فرض (سالم) برگردانید
        filtered_df['damage_status'] = 'سالم'
        return filtered_df
    
# --- بخش گزارش‌گیری و نمایش نتایج ---

def display_results(df_analyzed):
    """
    نمایش خلاصه آمار مدارس آسیب‌دیده.
    """
    
    st.markdown("---")
    st.subheader("📊 خلاصه گزارش ارزیابی خسارت")

    df_damaged = df_analyzed[df_analyzed['damage_status'] == 'آسیب‌دیده']
    total_damaged_schools = len(df_damaged)

    # نمایش آمار کلی
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric(
            label="تعداد کل مدارس در محدوده", 
            value=f"{len(df_analyzed)} مدرسه"
        )
    with col2:
        st.metric(
            label="مدارس آسیب‌دیده (در محدوده خسارت)", 
            value=f"{total_damaged_schools} مدرسه",
            delta_color="inverse"
        )
    with col3:
        total_students_damaged = df_damaged['students_boys'].sum() + df_damaged['students_girls'].sum()
        st.metric(
            label="کل دانش‌آموزان تحت تأثیر", 
            value=f"{total_students_damaged} نفر"
        )

    if total_damaged_schools > 0:
        st.markdown("#### آمار تفکیکی مدارس آسیب‌دیده:")
        
        # آمار بر اساس مقطع
        damage_by_level = df_damaged.groupby('level')['school_code'].count().reset_index(name='تعداد مدارس')
        damage_by_level = damage_by_level.rename(columns={'level': 'مقطع تحصیلی'})
        
        # آمار دانش‌آموزان
        students_by_type = pd.DataFrame({
            'جنسیت': ['پسر', 'دختر'],
            'تعداد دانش‌آموزان': [df_damaged['students_boys'].sum(), df_damaged['students_girls'].sum()]
        })

        # نمایش در دو ستون
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("##### تعداد مدارس آسیب‌دیده بر اساس مقطع")
            st.dataframe(damage_by_level, hide_index=True, use_container_width=True)

        with c2:
            st.markdown("##### تعداد کل دانش‌آموزان آسیب‌دیده بر اساس جنسیت")
            st.dataframe(students_by_type, hide_index=True, use_container_width=True)

        # جدول جزئیات مدارس آسیب‌دیده
        st.markdown("#### جزئیات کامل مدارس آسیب‌دیده")
        st.dataframe(
            df_damaged[['name', 'level', 'type', 'students_boys', 'students_girls', 'teachers', 'latitude', 'longitude']],
            hide_index=True,
            use_container_width=True
        )

        # دکمه دانلود گزارش
        df_export = df_damaged.rename(columns={
            'name': 'نام مدرسه', 
            'level': 'مقطع',
            'type': 'نوع (جنسیت)',
            'students_boys': 'دانش‌آموزان پسر',
            'students_girls': 'دانش‌آموزان دختر',
            'teachers': 'تعداد معلمین'
        })
        
        # ایجاد فایل اکسل در حافظه
        excel_data = to_excel(df_export)
        
        st.download_button(
            label="📥 دانلود گزارش کامل مدارس آسیب‌دیده (Excel)",
            data=excel_data,
            file_name='schools_damage_report.xlsx',
            mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        
    else:
        st.success("🎉 هیچ مدرسه‌ای در محدوده آسیب‌دیده قرار ندارد. (طبق فیلترهای انتخابی)")

# --- اجرای برنامه ---

if __name__ == "__main__":
    
    # 1. بارگذاری یا ایجاد داده‌های نمونه
    df_schools = load_data()
    
    # 2. تنظیم فیلترها و فیلتر کردن داده‌ها
    df_filtered = setup_sidebar(df_schools)
    
    # 3. نمایش نقشه، دریافت ورودی آسیب و اجرای تحلیل
    df_analyzed_with_damage = main_map_and_analysis(df_filtered)
    
    # 4. نمایش نتایج
    if df_analyzed_with_damage is not None:
        display_results(df_analyzed_with_damage)
