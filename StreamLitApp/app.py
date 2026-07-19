import streamlit as st
import requests
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
from datetime import date, timedelta, datetime
import numpy as np

# ── Config ────────────────────────────────────────────────────────────────────
WEATHER_BASE = "https://doubleislandweather01.lukas-deisenrieder.workers.dev"
WAVE_BASE    = "https://wavebuoy.lukas-deisenrieder.workers.dev"

st.set_page_config(
    page_title="Double Island Point — Weather & Ocean",
    page_icon="🌊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Styling ───────────────────────────────────────────────────────────────────
st.markdown("""
<style>
    .metric-card {
        background: #1e2130;
        border-radius: 10px;
        padding: 16px 20px;
        margin: 6px 0;
    }
    .metric-label { color: #888; font-size: 0.78rem; text-transform: uppercase; letter-spacing: 0.08em; }
    .metric-value { color: #fff; font-size: 1.6rem; font-weight: 700; }
    .metric-sub   { color: #aaa; font-size: 0.82rem; margin-top: 2px; }
    .section-header {
        font-size: 1.1rem; font-weight: 600; color: #ccc;
        border-bottom: 1px solid #333; padding-bottom: 6px; margin: 20px 0 12px 0;
    }
</style>
""", unsafe_allow_html=True)

# ── Data fetching ─────────────────────────────────────────────────────────────
@st.cache_data(ttl=300)
def fetch_available_dates():
    import re
    date_re = re.compile(r"^\d{4}-\d{2}-\d{2}$")

    def extract(keys, prefix):
        result = set()
        for key in keys:
            d = key.replace(prefix, "").replace(".json", "").strip()
            if date_re.match(d):
                result.add(d)
        return result

    weather_dates, wave_dates, tide_dates = set(), set(), set()
    try:
        r = requests.get(f"{WEATHER_BASE}/list", timeout=10)
        if r.ok:
            weather_dates = extract(r.json(), "WeatherStation/")
    except Exception: pass
    try:
        r = requests.get(f"{WAVE_BASE}/list/waves", timeout=10)
        if r.ok:
            wave_dates = extract(r.json(), "WaveBuoy/")
    except Exception: pass
    try:
        r = requests.get(f"{WAVE_BASE}/list/tides", timeout=10)
        if r.ok:
            tide_dates = extract(r.json(), "Tides/")
    except Exception: pass
    all_dates = sorted(weather_dates | wave_dates | tide_dates, reverse=True)
    return all_dates, weather_dates, wave_dates, tide_dates

@st.cache_data(ttl=300)
def fetch_weather(date_str):
    try:
        r = requests.get(f"{WEATHER_BASE}/data/{date_str}", timeout=10)
        if r.ok:
            df = pd.DataFrame(r.json())
            df["dt"] = pd.to_datetime(df["local_date_time"], format="%Y%m%d%H%M%S")
            df = df.sort_values("dt").reset_index(drop=True)
            return df
    except Exception: pass
    return pd.DataFrame()

@st.cache_data(ttl=300)
def fetch_waves(date_str):
    try:
        r = requests.get(f"{WAVE_BASE}/waves/{date_str}", timeout=10)
        if r.ok:
            df = pd.DataFrame(r.json())
            df["dt"] = pd.to_datetime(df["local_date_time"])
            df = df.sort_values("dt").reset_index(drop=True)
            return df
    except Exception: pass
    return pd.DataFrame()

@st.cache_data(ttl=300)
def fetch_tides(date_str):
    try:
        r = requests.get(f"{WAVE_BASE}/tides/{date_str}", timeout=10)
        if r.ok:
            df = pd.DataFrame(r.json())
            df["dt"] = pd.to_datetime(df["datetime_aest"])
            df = df.sort_values("dt").reset_index(drop=True)
            return df
    except Exception: pass
    return pd.DataFrame()

def fetch_range(date_list, fetch_fn):
    frames = [fetch_fn(d) for d in date_list]
    frames = [f for f in frames if not f.empty]
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()

# ── Helpers ───────────────────────────────────────────────────────────────────
PLOT_LAYOUT = dict(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="#0e1117",
    font_color="#ccc",
    margin=dict(l=10, r=10, t=30, b=10),
    legend=dict(bgcolor="rgba(0,0,0,0)"),
    xaxis=dict(gridcolor="#2a2a3a", showgrid=True),
    yaxis=dict(gridcolor="#2a2a3a", showgrid=True),
)

def metric_card(label, value, sub=""):
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-label">{label}</div>
        <div class="metric-value">{value}</div>
        {"<div class='metric-sub'>" + sub + "</div>" if sub else ""}
    </div>""", unsafe_allow_html=True)

def fmt(val, unit="", decimals=1):
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return "—"
    return f"{val:.{decimals}f}{unit}"

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("🌊 DIP Observer")
    st.caption("Double Island Point · Wide Bay")
    st.divider()

    all_dates, weather_dates, wave_dates, tide_dates = fetch_available_dates()

    if not all_dates:
        st.error("Could not reach workers. Check your connection.")
        st.stop()

    mode = st.radio("View mode", ["Single day", "Date range", "Calendar overview"], index=0)

    date_objs = [date.fromisoformat(d) for d in all_dates]
    min_date, max_date = min(date_objs), max(date_objs)

    if mode == "Single day":
        selected_date = st.date_input("Date", value=max_date, min_value=min_date, max_value=max_date)
        date_list = [selected_date.isoformat()]

    elif mode == "Date range":
        col1, col2 = st.columns(2)
        with col1:
            range_start = st.date_input("From", value=max_date - timedelta(days=6), min_value=min_date, max_value=max_date)
        with col2:
            range_end   = st.date_input("To",   value=max_date, min_value=min_date, max_value=max_date)
        if range_start > range_end:
            st.error("Start must be before end")
            st.stop()
        date_list = [(range_start + timedelta(days=i)).isoformat()
                     for i in range((range_end - range_start).days + 1)
                     if (range_start + timedelta(days=i)).isoformat() in all_dates]

    else:
        date_list = all_dates  # for calendar view

    st.divider()
    show_weather = st.toggle("Weather station", value=True)
    show_waves   = st.toggle("Wave buoy", value=True)
    show_tides   = st.toggle("Tides", value=True)

    st.divider()
    st.caption(f"📅 {len(all_dates)} days archived")
    st.caption(f"🌤 {len(weather_dates)} weather · 🌊 {len(wave_dates)} wave · 🌊 {len(tide_dates)} tide")

# ── Load data ─────────────────────────────────────────────────────────────────
if mode == "Calendar overview":
    # ── CALENDAR HEATMAP VIEW ─────────────────────────────────────────────────
    st.title("📅 Calendar Overview")

    cal_weather, cal_waves = pd.DataFrame(), pd.DataFrame()
    if show_weather and weather_dates:
        cal_weather = fetch_range(sorted(weather_dates), fetch_weather)
    if show_waves and wave_dates:
        cal_waves = fetch_range(sorted(wave_dates), fetch_waves)

    if not cal_weather.empty:
        cal_weather["date"] = cal_weather["dt"].dt.date
        daily_w = cal_weather.groupby("date").agg(
            avg_temp=("temp_c", "mean"),
            max_gust=("wind_gust_kmh", "max"),
            total_rain=("rainfall_mm", lambda x: pd.to_numeric(x, errors="coerce").sum()),
        ).reset_index()

        st.markdown('<div class="section-header">Average Temperature by Day</div>', unsafe_allow_html=True)
        fig = px.density_heatmap(
            daily_w, x=daily_w["date"].apply(lambda d: d.strftime("%b %d")),
            y=daily_w["date"].apply(lambda d: d.strftime("%Y")),
            z="avg_temp", color_continuous_scale="RdYlBu_r",
        )
        fig.update_layout(**PLOT_LAYOUT, height=200)
        st.plotly_chart(fig, use_container_width=True)

    if not cal_waves.empty:
        cal_waves["date"] = cal_waves["dt"].dt.date
        daily_wv = cal_waves.groupby("date").agg(
            avg_hs=("hs_m", "mean"),
            max_hs=("hs_m", "max"),
            avg_tp=("tp_s", "mean"),
        ).reset_index()

        st.markdown('<div class="section-header">Significant Wave Height (Hs) — Daily Average</div>', unsafe_allow_html=True)

        fig = go.Figure(go.Bar(
            x=daily_wv["date"].astype(str),
            y=daily_wv["avg_hs"],
            marker_color=daily_wv["avg_hs"],
            marker_colorscale="Blues",
            text=daily_wv["avg_hs"].apply(lambda v: f"{v:.1f}m"),
            textposition="outside",
        ))
        fig.update_layout(**PLOT_LAYOUT, height=300,
                          yaxis_title="Avg Hs (m)", showlegend=False)
        st.plotly_chart(fig, use_container_width=True)

        st.markdown('<div class="section-header">Max Wave Height & Peak Period</div>', unsafe_allow_html=True)
        fig = make_subplots(specs=[[{"secondary_y": True}]])
        fig.add_trace(go.Bar(x=daily_wv["date"].astype(str), y=daily_wv["max_hs"],
                             name="Max Hs (m)", marker_color="#4fc3f7"), secondary_y=False)
        fig.add_trace(go.Scatter(x=daily_wv["date"].astype(str), y=daily_wv["avg_tp"],
                                 name="Avg Tp (s)", line=dict(color="#ff9800", width=2)), secondary_y=True)
        fig.update_layout(**PLOT_LAYOUT, height=300)
        fig.update_yaxes(title_text="Max Hs (m)", secondary_y=False, gridcolor="#2a2a3a")
        fig.update_yaxes(title_text="Avg Period (s)", secondary_y=True, gridcolor="#2a2a3a")
        st.plotly_chart(fig, use_container_width=True)

    st.stop()

# ── SINGLE DAY / RANGE VIEW ───────────────────────────────────────────────────
wdf = pd.DataFrame()
vdf = pd.DataFrame()
tdf = pd.DataFrame()

if show_weather:
    wdf = fetch_range(date_list, fetch_weather)
if show_waves:
    vdf = fetch_range(date_list, fetch_waves)
if show_tides:
    tdf = fetch_range(date_list, fetch_tides)

label = date_list[0] if len(date_list) == 1 else f"{date_list[0]} → {date_list[-1]}"
st.title(f"🌊 Double Island Point")
st.caption(f"Showing: **{label}**")

# ── Summary cards ─────────────────────────────────────────────────────────────
if not wdf.empty or not vdf.empty:
    st.markdown('<div class="section-header">Summary</div>', unsafe_allow_html=True)
    cols = st.columns(4)
    i = 0
    if not wdf.empty:
        with cols[i % 4]:
            metric_card("Avg Temp", fmt(wdf["temp_c"].mean(), "°C"),
                        f"Min {fmt(wdf['temp_c'].min(), '°C')} · Max {fmt(wdf['temp_c'].max(), '°C')}")
        i += 1
        with cols[i % 4]:
            metric_card("Max Wind Gust", fmt(pd.to_numeric(wdf["wind_gust_kmh"], errors="coerce").max(), " km/h"),
                        f"Avg {fmt(pd.to_numeric(wdf['wind_speed_kmh'], errors='coerce').mean(), ' km/h')}")
        i += 1
        with cols[i % 4]:
            rain_vals = pd.to_numeric(wdf["rainfall_mm"], errors="coerce")
            metric_card("Rainfall", fmt(rain_vals.sum(), " mm"), "total")
        i += 1
        with cols[i % 4]:
            metric_card("Avg Pressure", fmt(pd.to_numeric(wdf["pressure_hpa"], errors="coerce").mean(), " hPa"))
        i += 1
    if not vdf.empty:
        with cols[i % 4]:
            metric_card("Avg Wave Ht (Hs)", fmt(vdf["hs_m"].mean(), " m"),
                        f"Max {fmt(vdf['hs_m'].max(), ' m')}")
        i += 1
        with cols[i % 4]:
            metric_card("Max Wave (Hmax)", fmt(vdf["hmax_m"].max(), " m"))
        i += 1
        with cols[i % 4]:
            metric_card("Avg Peak Period", fmt(vdf["tp_s"].mean(), " s"))
        i += 1
        with cols[i % 4]:
            metric_card("Sea Surface Temp", fmt(vdf["sst_c"].mean(), "°C"))

# ── Weather charts ────────────────────────────────────────────────────────────
if show_weather and not wdf.empty:
    st.markdown('<div class="section-header">🌤 Weather Station — Double Island Point</div>', unsafe_allow_html=True)

    # Temperature + Feels Like + Humidity
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(go.Scatter(x=wdf["dt"], y=wdf["temp_c"], name="Temp (°C)",
                             line=dict(color="#ff7043", width=2)), secondary_y=False)
    fig.add_trace(go.Scatter(x=wdf["dt"], y=wdf["feels_like_c"], name="Feels Like (°C)",
                             line=dict(color="#ffb74d", width=1.5, dash="dot")), secondary_y=False)
    fig.add_trace(go.Scatter(x=wdf["dt"], y=wdf["humidity_pct"], name="Humidity (%)",
                             line=dict(color="#4fc3f7", width=1.5), opacity=0.7), secondary_y=True)
    fig.update_layout(**PLOT_LAYOUT, height=300, title_text="Temperature & Humidity")
    fig.update_yaxes(title_text="°C", secondary_y=False, gridcolor="#2a2a3a")
    fig.update_yaxes(title_text="Humidity %", secondary_y=True, gridcolor="#2a2a3a", range=[0, 110])
    st.plotly_chart(fig, use_container_width=True)

    # Wind speed + gusts
    fig = make_subplots(specs=[[{"secondary_y": False}]])
    fig.add_trace(go.Scatter(
        x=wdf["dt"],
        y=pd.to_numeric(wdf["wind_gust_kmh"], errors="coerce"),
        name="Wind Gust (km/h)",
        fill="tozeroy", fillcolor="rgba(100,181,246,0.15)",
        line=dict(color="#64b5f6", width=1.5),
    ))
    fig.add_trace(go.Scatter(
        x=wdf["dt"],
        y=pd.to_numeric(wdf["wind_speed_kmh"], errors="coerce"),
        name="Wind Speed (km/h)",
        line=dict(color="#1565c0", width=2),
    ))
    fig.update_layout(**PLOT_LAYOUT, height=250, title_text="Wind Speed & Gusts")
    fig.update_yaxes(title_text="km/h", gridcolor="#2a2a3a")
    st.plotly_chart(fig, use_container_width=True)

    # Pressure + Rainfall
    col1, col2 = st.columns(2)
    with col1:
        fig = go.Figure(go.Scatter(
            x=wdf["dt"], y=pd.to_numeric(wdf["pressure_hpa"], errors="coerce"),
            name="Pressure", line=dict(color="#ce93d8", width=2), fill="tozeroy",
            fillcolor="rgba(206,147,216,0.1)",
        ))
        fig.update_layout(**PLOT_LAYOUT, height=250, title_text="Pressure (hPa)")
        st.plotly_chart(fig, use_container_width=True)
    with col2:
        fig = go.Figure(go.Bar(
            x=wdf["dt"],
            y=pd.to_numeric(wdf["rainfall_mm"], errors="coerce"),
            name="Rainfall (mm)", marker_color="#80cbc4",
        ))
        fig.update_layout(**PLOT_LAYOUT, height=250, title_text="Rainfall (mm)")
        st.plotly_chart(fig, use_container_width=True)

    # Wind rose
    st.markdown('<div class="section-header">Wind Direction Rose</div>', unsafe_allow_html=True)
    wind_dir_map = {"N":0,"NNE":22.5,"NE":45,"ENE":67.5,"E":90,"ESE":112.5,
                    "SE":135,"SSE":157.5,"S":180,"SSW":202.5,"SW":225,"WSW":247.5,
                    "W":270,"WNW":292.5,"NW":315,"NNW":337.5}
    wdf_wind = wdf[wdf["wind_dir"].isin(wind_dir_map)].copy()
    wdf_wind["wind_deg"] = wdf_wind["wind_dir"].map(wind_dir_map)
    wdf_wind["wind_speed_num"] = pd.to_numeric(wdf_wind["wind_speed_kmh"], errors="coerce")

    bins = [0, 20, 40, 60, 80, 200]
    labels = ["0–20", "20–40", "40–60", "60–80", "80+"]
    wdf_wind["speed_bin"] = pd.cut(wdf_wind["wind_speed_num"], bins=bins, labels=labels)

    fig = go.Figure()
    colors = ["#b3e5fc", "#4fc3f7", "#0288d1", "#01579b", "#003c6e"]
    for lbl, color in zip(labels, colors):
        subset = wdf_wind[wdf_wind["speed_bin"] == lbl]
        if not subset.empty:
            fig.add_trace(go.Barpolar(
                r=[1] * len(subset),
                theta=subset["wind_deg"],
                name=f"{lbl} km/h",
                marker_color=color,
                opacity=0.85,
            ))
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="#0e1117",
        font_color="#ccc", height=380,
        polar=dict(
            bgcolor="#0e1117",
            radialaxis=dict(visible=False),
            angularaxis=dict(direction="clockwise", tickmode="array",
                             tickvals=[0,45,90,135,180,225,270,315],
                             ticktext=["N","NE","E","SE","S","SW","W","NW"],
                             gridcolor="#2a2a3a"),
        ),
        legend=dict(bgcolor="rgba(0,0,0,0)"),
    )
    st.plotly_chart(fig, use_container_width=True)

# ── Wave charts ───────────────────────────────────────────────────────────────
if show_waves and not vdf.empty:
    st.markdown('<div class="section-header">🌊 Wave Buoy — Wide Bay</div>', unsafe_allow_html=True)

    # Hs + Hmax + Tp
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(go.Scatter(
        x=vdf["dt"], y=vdf["hs_m"], name="Hs — Sig. Wave Height (m)",
        fill="tozeroy", fillcolor="rgba(79,195,247,0.15)",
        line=dict(color="#4fc3f7", width=2),
    ), secondary_y=False)
    fig.add_trace(go.Scatter(
        x=vdf["dt"], y=vdf["hmax_m"], name="Hmax — Max Wave (m)",
        line=dict(color="#0288d1", width=1.5, dash="dot"),
    ), secondary_y=False)
    fig.add_trace(go.Scatter(
        x=vdf["dt"], y=vdf["tp_s"], name="Tp — Peak Period (s)",
        line=dict(color="#ff9800", width=1.5),
    ), secondary_y=True)
    fig.update_layout(**PLOT_LAYOUT, height=320, title_text="Wave Height & Period")
    fig.update_yaxes(title_text="Height (m)", secondary_y=False, gridcolor="#2a2a3a")
    fig.update_yaxes(title_text="Period (s)", secondary_y=True, gridcolor="#2a2a3a")
    st.plotly_chart(fig, use_container_width=True)

    # SST + Wave direction
    col1, col2 = st.columns(2)
    with col1:
        fig = go.Figure(go.Scatter(
            x=vdf["dt"], y=vdf["sst_c"], name="SST (°C)",
            line=dict(color="#ef5350", width=2), fill="tozeroy",
            fillcolor="rgba(239,83,80,0.1)",
        ))
        fig.update_layout(**PLOT_LAYOUT, height=250, title_text="Sea Surface Temperature (°C)")
        st.plotly_chart(fig, use_container_width=True)
    with col2:
        fig = go.Figure(go.Scatter(
            x=vdf["dt"], y=vdf["dir_deg"], name="Wave Dir (°)",
            mode="markers", marker=dict(color="#ba68c8", size=5),
        ))
        fig.update_layout(**PLOT_LAYOUT, height=250, title_text="Wave Direction (°, clockwise from N)",
                          yaxis=dict(range=[0, 360], gridcolor="#2a2a3a",
                                     tickvals=[0,90,180,270,360],
                                     ticktext=["N","E","S","W","N"]))
        st.plotly_chart(fig, use_container_width=True)

    # Wave direction rose
    st.markdown('<div class="section-header">Wave Direction Rose</div>', unsafe_allow_html=True)
    vdf_dir = vdf.dropna(subset=["dir_deg", "hs_m"])
    hs_bins  = [0, 0.5, 1.0, 1.5, 2.0, 10]
    hs_labels = ["0–0.5m", "0.5–1m", "1–1.5m", "1.5–2m", "2m+"]
    vdf_dir = vdf_dir.copy()
    vdf_dir["hs_bin"] = pd.cut(vdf_dir["hs_m"], bins=hs_bins, labels=hs_labels)
    fig = go.Figure()
    colors = ["#e3f2fd","#90caf9","#42a5f5","#1565c0","#0d47a1"]
    for lbl, color in zip(hs_labels, colors):
        subset = vdf_dir[vdf_dir["hs_bin"] == lbl]
        if not subset.empty:
            fig.add_trace(go.Barpolar(
                r=[1] * len(subset), theta=subset["dir_deg"],
                name=lbl, marker_color=color, opacity=0.85,
            ))
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="#0e1117",
        font_color="#ccc", height=380,
        polar=dict(
            bgcolor="#0e1117",
            radialaxis=dict(visible=False),
            angularaxis=dict(direction="clockwise", tickmode="array",
                             tickvals=[0,45,90,135,180,225,270,315],
                             ticktext=["N","NE","E","SE","S","SW","W","NW"],
                             gridcolor="#2a2a3a"),
        ),
        legend=dict(bgcolor="rgba(0,0,0,0)"),
    )
    st.plotly_chart(fig, use_container_width=True)

# ── Tide chart ────────────────────────────────────────────────────────────────
if show_tides and not tdf.empty:
    st.markdown('<div class="section-header">🌊 Tides — Tin Can Bay Approaches</div>', unsafe_allow_html=True)

    # Build a smooth tide curve via cosine interpolation between events
    tide_times = tdf["dt"].values.astype("int64") / 1e9
    tide_heights = tdf["height_m"].values

    dense_times = np.linspace(tide_times.min(), tide_times.max(), 500)
    dense_heights = np.interp(dense_times, tide_times, tide_heights)

    dense_dts = pd.to_datetime(dense_times * 1e9)

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=dense_dts, y=dense_heights,
        name="Tide height (m)",
        fill="tozeroy", fillcolor="rgba(100,181,246,0.15)",
        line=dict(color="#64b5f6", width=2),
    ))
    highs = tdf[tdf["type"] == "high"]
    lows  = tdf[tdf["type"] == "low"]
    fig.add_trace(go.Scatter(
        x=highs["dt"], y=highs["height_m"],
        mode="markers+text", name="High tide",
        marker=dict(color="#ff7043", size=10, symbol="triangle-up"),
        text=highs["height_m"].apply(lambda v: f"{v:.2f}m"),
        textposition="top center", textfont=dict(color="#ff7043"),
    ))
    fig.add_trace(go.Scatter(
        x=lows["dt"], y=lows["height_m"],
        mode="markers+text", name="Low tide",
        marker=dict(color="#80cbc4", size=10, symbol="triangle-down"),
        text=lows["height_m"].apply(lambda v: f"{v:.2f}m"),
        textposition="bottom center", textfont=dict(color="#80cbc4"),
    ))
    fig.update_layout(**PLOT_LAYOUT, height=300, title_text="Tide Predictions (AEST)")
    fig.update_yaxes(title_text="Height (m)", gridcolor="#2a2a3a")
    st.plotly_chart(fig, use_container_width=True)

# ── Correlation ───────────────────────────────────────────────────────────────
if show_waves and show_weather and not vdf.empty and not wdf.empty:
    st.markdown('<div class="section-header">📊 Correlations</div>', unsafe_allow_html=True)

    # Merge on nearest timestamp
    wdf_m = wdf.set_index("dt").resample("30min").mean(numeric_only=True).reset_index()
    vdf_m = vdf.set_index("dt").resample("30min").mean(numeric_only=True).reset_index()
    merged = pd.merge_asof(vdf_m.sort_values("dt"), wdf_m.sort_values("dt"),
                           on="dt", tolerance=pd.Timedelta("30min"), direction="nearest")
    merged = merged.dropna(subset=["hs_m", "wind_speed_kmh", "temp_c"])

    col1, col2 = st.columns(2)
    with col1:
        fig = px.scatter(merged, x="wind_speed_kmh", y="hs_m",
                         color="tp_s", color_continuous_scale="Blues",
                         labels={"wind_speed_kmh": "Wind Speed (km/h)",
                                 "hs_m": "Significant Wave Height (m)",
                                 "tp_s": "Peak Period (s)"},
                         title="Wind Speed vs Wave Height")
        fig.update_layout(**PLOT_LAYOUT, height=320)
        st.plotly_chart(fig, use_container_width=True)
    with col2:
        fig = px.scatter(merged, x="temp_c", y="sst_c",
                         color="hs_m", color_continuous_scale="Blues",
                         labels={"temp_c": "Air Temp (°C)",
                                 "sst_c": "Sea Surface Temp (°C)",
                                 "hs_m": "Hs (m)"},
                         title="Air Temp vs Sea Surface Temp")
        fig.update_layout(**PLOT_LAYOUT, height=320)
        st.plotly_chart(fig, use_container_width=True)
