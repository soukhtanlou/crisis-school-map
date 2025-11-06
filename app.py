import streamlit as st
import pandas as pd
import folium
from folium.plugins import Draw, Fullscreen
from streamlit_folium import st_folium
import json
from shapely.geometry import shape, Point

# --- Configuration and Initialization ---

# تنظیمات صفحه Streamlit
st.set_page_config(
    page_title="تحلیل آسیب‌پذیری مدارس در برابر سیلاب",
    layout="wide",
    initial_sidebar_state="expanded"
)

# تعریف متغیرهای سراسری برای شناسایی برنامه و تنظیمات پایگاه داده
appId = 'flood-impact-analysis'
# فرض می‌کنیم متغیرهای __app_id, __firebase_config, __initial_auth_token در محیط وجود دارند.
# برای اجرای مستقل، مقادیر پیش‌فرض را تنظیم می‌کنیم.

# تنظیمات رنگ‌بندی برای دسته‌بندی مدارس (برای نقشه)
category_colors = {
    'ابتدایی/دبستان': '#28a745', # سبز
    'متوسطه': '#007bff',        # آبی
    'فنی و حرفه‌ای': '#ffc107',  # زرد
    'مراکز/سایر': '#dc3545',     # قرمز
}

# --- Utility Functions ---

def load_data():
    """بارگذاری داده‌های مدارس و داده‌های سیلاب"""
    
    # 1. بارگذاری داده‌های مدارس (مدل‌سازی شده): فرض بر وجود فایل schools.csv
    try:
        # ساخت یک DataFrame ساختگی برای شبیه‌سازی داده‌های واقعی
        school_data = {
            'Name': ['مدرسه الف', 'مدرسه ب', 'مدرسه ج', 'مدرسه د', 'مدرسه ه'],
            'Lat': [37.34, 37.31, 37.33, 37.35, 37.32],
            'Lon': [54.53, 54.40, 54.16, 54.45, 54.25],
            'Category': ['ابتدایی/دبستان', 'متوسطه', 'ابتدایی/دبستان', 'فنی و حرفه‌ای', 'متوسطه'],
            'Students': [250, 400, 180, 50, 320]
        }
        df_schools = pd.DataFrame(school_data)
        # تنظیم ستون‌ها به فارسی
        df_schools.columns = ['نام مدرسه', 'عرض جغرافیایی', 'طول جغرافیایی', 'مقطع تحصیلی', 'تعداد دانش‌آموزان']
        
    except Exception as e:
        st.error(f"خطا در بارگذاری داده‌های مدارس: {e}")
        df_schools = pd.DataFrame()

    # 2. بارگذاری داده‌های GeoJSON سیلاب (با استفاده از فایل آپلود شده)
    try:
        with open("ST20190329_Golestan_Flood_Water.json", 'r', encoding='utf-8') as f:
            flood_geojson = json.load(f)
        
        # تبدیل عوارض GeoJSON به اشیاء Shapely برای تحلیل فضایی سریع
        flood_shapes = [shape(feature['geometry']) for feature in flood_geojson['features']]
        
    except Exception as e:
        st.error(f"خطا در بارگذاری GeoJSON سیلاب: {e}")
        flood_shapes = []
        
    return df_schools, flood_shapes, flood_geojson

# --- Core Analysis Logic ---

def check_for_impact(df_schools, flood_shapes, selected_categories):
    """
    بررسی می‌کند که آیا هر مدرسه در محدوده‌های سیلاب قرار دارد و فیلترهای مقطع تحصیلی را اعمال می‌کند.
    """
    impacted_schools = []
    
    # فیلتر کردن مدارس بر اساس مقاطع تحصیلی انتخاب شده توسط کاربر
    df_filtered = df_schools[df_schools['مقطع تحصیلی'].isin(selected_categories)]
    
    for index, row in df_filtered.iterrows():
        # ساختن نقطه Shapely از مختصات مدرسه
        school_point = Point(row['طول جغرافیایی'], row['عرض جغرافیایی'])
        
        is_impacted = False
        # بررسی برخورد نقطه مدرسه با هر یک از عوارض سیلاب (چندضلعی‌های Shapely)
        for flood_area in flood_shapes:
            if flood_area.contains(school_point):
                is_impacted = True
                break
        
        if is_impacted:
            impacted_schools.append(row.to_dict())
            
    return impacted_schools

# --- Map Generation ---

def create_folium_map(df_schools, flood_geojson, impacted_schools):
    """ایجاد نقشه Folium و افزودن لایه‌های سیلاب و مدارس"""
    
    # تعیین مرکز نقشه (تقریباً گلستان)
    m = folium.Map(location=[37.2, 54.4], zoom_start=9, tiles="cartodbpositron", control_scale=True)
    
    # 1. افزودن لایه سیلاب (با رنگ آبی شفاف)
    if flood_geojson:
        folium.GeoJson(
            flood_geojson,
            name='محدوده سیلاب (Sentinel-1 - 2019)',
            style_function=lambda x: {
                'fillColor': '#00bfff',
                'color': '#00bfff',
                'weight': 1,
                'fillOpacity': 0.4
            }
        ).add_to(m)

    # 2. افزودن لایه مدارس
    school_group = folium.FeatureGroup(name="مدارس").add_to(m)
    
    # استخراج نام‌های مدارس آسیب‌دیده برای برجسته‌سازی
    impacted_names = {school['نام مدرسه'] for school in impacted_schools}
    
    for index, row in df_schools.iterrows():
        is_impacted = row['نام مدرسه'] in impacted_names
        
        # تعیین رنگ بر اساس مقطع تحصیلی
        color_code = category_colors.get(row['مقطع تحصیلی'], '#808080') # خاکستری برای مقاطع نامشخص
        
        # تعیین اندازه آیکون برای برجسته‌سازی مدارس آسیب‌دیده
        icon_size = 14 if is_impacted else 10
        
        # ساخت متن پاپ‌آپ
        popup_html = f"""
            <div style='font-family: Tahoma; text-align: right; direction: rtl;'>
                <b>نام:</b> {row['نام مدرسه']}<br>
                <b>مقطع:</b> {row['مقطع تحصیلی']}<br>
                <b>دانش‌آموزان:</b> {row['تعداد دانش‌آموزان']}<br>
                {f"<b style='color: red;'>وضعیت: آسیب‌دیده</b>" if is_impacted else "<b style='color: green;'>وضعیت: در امان</b>"}
            </div>
        """
        
        # افزودن مارکر به نقشه
        folium.CircleMarker(
            location=[row['عرض جغرافیایی'], row['طول جغرافیایی']],
            radius=icon_size,
            color=color_code,
            fill=True,
            fill_color=color_code,
            fill_opacity=0.8,
            popup=folium.Popup(popup_html, max_width=300)
        ).add_to(school_group)

    # افزودن ابزارهای نقشه
    folium.LayerControl().add_to(m)
    Fullscreen().add_to(m)
    
    # افزودن ابزار ترسیم (Draw Tool)
    Draw(
        export=False,
        filename='data.geojson',
        position='topleft',
        draw_options={
            'polyline': False,
            'marker': False,
            'circlemarker': False,
            'circle': False
        },
        edit_options={'edit': True, 'remove': True}
    ).add_to(m)
    
    return m


# --- Streamlit App Layout ---

def main():
    """تابع اصلی برنامه Streamlit"""
    st.title("تحلیل آسیب‌پذیری مدارس در برابر سیلاب")
    st.markdown("این ابزار مناطق سیلاب‌زده را با موقعیت مکانی مدارس (ساختگی) در استان گلستان مقایسه می‌کند.")

    # 1. بارگذاری داده‌ها
    df_schools, flood_shapes, flood_geojson = load_data()

    if df_schools.empty or not flood_shapes:
        st.stop()

    st.sidebar.header("تنظیمات و فیلترها")

    # 2. فیلتر بر اساس مقطع تحصیلی (نوار کناری)
    all_categories = list(category_colors.keys())
    selected_categories = st.sidebar.multiselect(
        "فیلتر بر اساس دسته مقطع تحصیلی:",
        options=all_categories,
        default=all_categories
    )
    
    # 3. اجرای تحلیل
    impacted_schools = check_for_impact(df_schools, flood_shapes, selected_categories)
    
    # 4. نمایش نقشه Folium
    
    st.subheader("نقشه تعاملی تحلیل آسیب‌پذیری")
    st.info("نقطه آبی نشان‌دهنده آب گرفتگی و دایره‌ها موقعیت مدارس هستند. می‌توانید با ابزار سمت چپ، منطقه جدیدی را رسم کنید.")
    
    # ساخت نقشه
    m = create_folium_map(df_schools, flood_geojson, impacted_schools)
    
    # نمایش نقشه در Streamlit و گرفتن خروجی (اگر چیزی روی آن رسم شود)
    output = st_folium(m, width=1000, height=600)
    
    # 5. نمایش نتایج تحلیل (این بخش را اصلاح می‌کنیم)
    st.markdown("---")
    st.subheader("نتایج تحلیل آسیب‌پذیری")

    if not impacted_schools:
        st.info("هیچ مدرسه‌ای در مقاطع انتخابی در محدوده سیلاب شناسایی نشد.")
    else:
        total_schools = len(impacted_schools)
        total_students = sum(school['تعداد دانش‌آموزان'] for school in impacted_schools)
        
        # --- اصلاح بخش نهایی گزارش برای رفع مشکل رنگ سبز ---
        
        # استفاده از st.metric برای نمایش آمار آسیب‌دیده با رنگ خنثی/هشدار
        col1, col2 = st.columns(2)
        
        with col1:
            # تغییر از st.success (سبز) به st.metric (خنثی/اطلاعاتی)
            st.metric(
                label="تعداد مدارس آسیب‌دیده در محدوده‌های انتخابی", 
                value=total_schools,
                delta="توجه: نیاز به ارزیابی میدانی",
                delta_color="off" # استفاده از رنگ خنثی برای Delta
            )
            
        with col2:
            # استفاده از st.metric برای نمایش تعداد دانش‌آموزان تحت تاثیر
            st.metric(
                label="جمع کل دانش‌آموزان در مدارس آسیب‌دیده", 
                value=total_students
            )

        st.warning("⚠️ نتایج بالا صرفاً بر اساس همپوشانی مکانی است و نیاز به تأیید میدانی دارد.")
        
        # نمایش جدول جزئیات
        st.markdown("---")
        st.markdown("##### جزئیات مدارس آسیب‌دیده:")
        
        # تبدیل لیست دیکشنری به دیتافریم برای نمایش
        df_impacted = pd.DataFrame(impacted_schools)
        df_impacted.rename(columns={'نام مدرسه': 'نام', 'مقطع تحصیلی': 'مقطع', 'تعداد دانش‌آموزان': 'دانش‌آموزان', 
                                    'عرض جغرافیایی': 'Lat', 'طول جغرافیایی': 'Lon'}, inplace=True)
        
        st.dataframe(df_impacted[['نام', 'مقطع', 'دانش‌آموزان']], use_container_width=True)

    st.markdown("---")
    st.caption("داده‌های مدارس ساختگی بوده و GeoJSON سیلاب مربوط به یک رویداد تاریخی است.")


if __name__ == "__main__":
    main()
