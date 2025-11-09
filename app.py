import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
from shapely.geometry import Polygon, Point, shape
from shapely.ops import unary_union
import requests
import json
import os
import geopandas as gpd   # برای SHP
from folium.plugins import Draw


# -------------------------------
# 0) تنظیمات اولیه اپ
# -------------------------------

st.set_page_config(page_title="ارزیابی خسارت مدارس", layout="wide")
st.title("ارزیابی خسارت مدارس در بحران‌")


# مدیریت state
if "initial_map_location" not in st.session_state:
    st.session_state.initial_map_location = [32.5, 53.0]  # مرکز ایران
if "initial_map_zoom" not in st.session_state:
    st.session_state.initial_map_zoom = 5
if "uploaded_geojson_data" not in st.session_state:
    st.session_state.uploaded_geojson_data = None
if "reset" not in st.session_state:
    st.session_state.reset = 0


# -------------------------------
# 1) بارگذاری داده مدارس
# -------------------------------

@st.cache_data
def load_schools():
    df = pd.read_csv("schools.csv", encoding="utf-8-sig")

    df["عرض_جغرافیایی"] = pd.to_numeric(df["عرض_جغرافیایی"], errors="coerce")
    df["طول_جغرافیایی"] = pd.to_numeric(df["طول_جغرافیایی"], errors="coerce")

    df = df.dropna(subset=["عرض_جغرافیایی", "طول_جغرافیایی"])

    def cat(grade):
        if "دبستان" in grade or "پیش" in grade:
            return "ابتدایی / دبستان"
        if "متوسطه" in grade:
            return "متوسطه"
        if "فنی" in grade:
            return "فنی و حرفه‌ای"
        return "سایر"

    df["دسته_مقطع"] = df["مقطع_تحصیلی"].apply(cat)
    return df


if not os.path.exists("schools.csv"):
    st.error("❌ فایل schools.csv پیدا نشد.")
    st.stop()

df = load_schools()


# -------------------------------
# 2) فیلترهای کاربر
# -------------------------------

st.sidebar.header("فیلتر اطلاعات")

grade_filters = st.sidebar.multiselect("مقطع تحصیلی", options=df["دسته_مقطع"].unique(),
                                       default=df["دسته_مقطع"].unique())

gender_filters = st.sidebar.multiselect("جنسیت", options=df["جنسیت"].unique(),
                                        default=df["جنسیت"].unique())

filtered_df = df[(df["دسته_مقطع"].isin(grade_filters)) &
                 (df["جنسیت"].isin(gender_filters))]


# -------------------------------
# 3) آپلود نقشه (GeoJSON یا SHP)
# -------------------------------

st.sidebar.markdown("---")
st.sidebar.subheader("بارگذاری محدوده آسیب")

uploaded = st.sidebar.file_uploader("آپلود GeoJSON یا SHP (.zip)", type=["geojson", "json", "zip"])

if uploaded:
    try:
        if uploaded.name.endswith(".zip"):
            gdf = gpd.read_file(uploaded)
            geojson = json.loads(gdf.to_json())
            st.session_state.uploaded_geojson_data = geojson

            bounds = gdf.total_bounds
            st.session_state.initial_map_location = [(bounds[1] + bounds[3]) / 2, (bounds[0] + bounds[2]) / 2]
            st.session_state.initial_map_zoom = 10

            st.success("✅ فایل SHP با موفقیت بارگذاری شد.")

        else:
            geojson = json.load(uploaded)
            st.session_state.uploaded_geojson_data = geojson

            shp = shape(geojson["features"][0]["geometry"])
            st.session_state.initial_map_location = [shp.centroid.y, shp.centroid.x]
            st.session_state.initial_map_zoom = 11

            st.success("✅ GeoJSON با موفقیت بارگذاری شد.")

    except Exception as e:
        st.error(f"⚠️ خطا در خواندن فایل: {e}")


# دکمه ریست
if st.sidebar.button("♻️ ریست نقشه و پاک کردن محدوده"):
    st.session_state.uploaded_geojson_data = None
    st.session_state.initial_map_location = [32.5, 53.0]
    st.session_state.initial_map_zoom = 5
    st.session_state.reset += 1
    st.rerun()


# -------------------------------
# 4) ساخت نقشه
# -------------------------------

m = folium.Map(
    location=st.session_state.initial_map_location,
    zoom_start=st.session_state.initial_map_zoom,
    tiles="OpenStreetMap"
)

draw = Draw(draw_options={"polygon": True})
draw.add_to(m)

school_layer = folium.FeatureGroup(name="مدارس").add_to(m)

colors = {"ابتدایی / دبستان": "green", "متوسطه": "blue", "فنی و حرفه‌ای": "orange", "سایر": "gray"}

for _, row in filtered_df.iterrows():
    folium.CircleMarker(
        location=[row["عرض_جغرافیایی"], row["طول_جغرافیایی"]],
        radius=6,
        color=colors[row["دسته_مقطع"]],
        fill=True,
        fill_opacity=.8,
        tooltip=f"{row['نام_مدرسه']}",
    ).add_to(school_layer)

# اضافه کردن GeoJSON (اگر آپلود شده باشد)
if st.session_state.uploaded_geojson_data:
    folium.GeoJson(
        st.session_state.uploaded_geojson_data,
        name="محدوده آسیب",
        style_function=lambda x: {"fillColor": "#ff0000", "color": "#ff0000", "fillOpacity": 0.35},
    ).add_to(m)

folium.LayerControl().add_to(m)

map_data = st_folium(m, height=600, width=1200, key=f"map_{st.session_state.reset}")


# -------------------------------
# 5) تحلیل محدوده‌ها
# -------------------------------

polys = []

# پلی‌گون‌های دستی
if map_data and map_data.get("all_drawings"):
    for p in map_data["all_drawings"]:
        coords = p["geometry"]["coordinates"][0]
        polys.append(Polygon([(lon, lat) for lat, lon in coords]))


# پلی‌گون از GeoJSON
if st.session_state.uploaded_geojson_data:
    shp = shape(st.session_state.uploaded_geojson_data["features"][0]["geometry"])
    if shp.geom_type == "Polygon":
        polys.append(shp)
    elif shp.geom_type == "MultiPolygon":
        polys.extend(list(shp.geoms))


if polys:
    multi = unary_union(polys)

    filtered_df["inside"] = filtered_df.apply(
        lambda r: multi.contains(Point(r["طول_جغرافیایی"], r["عرض_جغرافیایی"])), axis=1
    )

    result = filtered_df[filtered_df["inside"] == True]

    st.markdown("---")
    st.subheader("📌 گزارش محدوده انتخاب شده")

    col1, col2, col3 = st.columns(3)
    col1.metric("✅ تعداد مدارس", len(result))
    col2.metric("👩‍🎓 دانش‌آموزان", int(result["تعداد_دانش_آموز"].sum()))
    col3.metric("👩‍🏫 معلمین", int(result["تعداد_معلم"].sum()))

    st.dataframe(result, hide_index=True, use_container_width=True)

    csv = result.to_csv(index=False, encoding="utf-8-sig")
    st.download_button("⬇️ دانلود CSV", data=csv, file_name="schools_damage.csv")

else:
    st.info("برای تحلیل: یک محدوده ترسیم کنید یا فایل نقشه آپلود کنید.")
