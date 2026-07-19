import streamlit as st
import requests
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
from datetime import date, timedelta
import numpy as np
import re

# ── Config ────────────────────────────────────────────────────────────────────
WEATHER_BASE = "https://doubleislandweather01.lukas-deisenrieder.workers.dev"
WAVE_BASE    = "https://wavebuoy.lukas-deisenrieder.workers.dev"

st.set_page_config(
    page_title="Double Island Point — Weather & Ocean",
    page_icon="🌊",
    layout="wide",
    initial_sidebar_state="expanded",
)

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

# ── Plot base layout (NO yaxis key — set per chart) ──────────────────────────
def base_layout(height=300, title=""):
    return dict(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="#0e1117",
        font_color="#ccc",
        margin=dict(l=10, r=10, t=40 if title else 10, b=10),
        legend=dict(bgcolor="rgba(0,0,0,0)"),
        xaxis=dict(gridcolor="#2a2a3a", showgrid=True),
        yaxis=dict(gridcolor="#2a2a3a", showgrid=True),
        height=height,
        title_text=title,
    )

# ── Data fetching ─────────────────────────────────────────────────────────────
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

@st.cache_data(ttl=300)
def fetch_available_dates():
    def extract(keys, prefix):
        result = set()
        for key in keys:
            d = key.replace(prefix, "").replace(".json", "").strip()
            if DATE_RE.match(d):
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
        r = requests.get(f"{WEATHER_BASE}/data/{date_str}.json", timeout=10)
        if r.ok:
            df = pd.DataFrame(r.json())
            df["dt"] = pd.to_datetime(df["local_date_time"], format="%Y%m%d%H%M%S")
            return df.sort_values("dt").reset_index(drop=True)
    except Exception: pass
    return pd.DataFrame()

@st.cache_data(ttl=300)
def fetch_waves(date_str):
    try:
        r = requests.get(f"{WAVE_BASE}/waves/{date_str}", timeout=10)
        if r.ok:
            df = pd.DataFrame(r.json())
            df["dt"] = pd.to_datetime(df["local_date_time"])
            return df.sort_values("dt").reset_index(drop=True)
    except Exception: pass
    return pd.DataFrame()

@st.cache_data(ttl=300)
def fetch_tides(date_str):
    try:
        r = requests.get(f"{WAVE_BASE}/tides/{date_str}", timeout=10)
        if r.ok:
            df = pd.DataFrame(r.json())
            # Strip timezone offset so pandas reads as naive local time
            # Parse "2026-07-19T06:01:00+10:00" — slice first 19 chars to keep AEST local time
            df["dt"] = pd.to_datetime(df["datetime_aest"].str[:19])
            return df.sort_values("dt").reset_index(drop=True)
    except Exception: pass
    return pd.DataFrame()

def fetch_range(date_list, fetch_fn):
    frames = [fetch_fn(d) for d in date_list]
    frames = [f for f in frames if not f.empty]
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()

# ── Helpers ───────────────────────────────────────────────────────────────────
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

    mode = st.radio("View mode", ["Single day", "Date range", "Calendar overview"])

    date_objs = [date.fromisoformat(d) for d in all_dates]
    min_date, max_date = min(date_objs), max(date_objs)

    if mode == "Single day":
        selected_date = st.date_input("Date", value=max_date, min_value=min_date, max_value=max_date)
        date_list = [selected_date.isoformat()]
    elif mode == "Date range":
        c1, c2 = st.columns(2)
        with c1:
            range_start = st.date_input("From", value=max_date - timedelta(days=6), min_value=min_date, max_value=max_date)
        with c2:
            range_end = st.date_input("To", value=max_date, min_value=min_date, max_value=max_date)
        if range_start > range_end:
            st.error("Start must be before end")
            st.stop()
        date_list = [
            (range_start + timedelta(days=i)).isoformat()
            for i in range((range_end - range_start).days + 1)
            if (range_start + timedelta(days=i)).isoformat() in all_dates
        ]
    else:
        date_list = all_dates

    st.divider()
    show_weather = st.toggle("Weather station", value=True)
    show_waves   = st.toggle("Wave buoy", value=True)
    show_tides   = st.toggle("Tides", value=True)
    st.divider()
    st.caption(f"📅 {len(all_dates)} days archived")
    st.caption(f"🌤 {len(weather_dates)} weather · 🌊 {len(wave_dates)} wave · 🌊 {len(tide_dates)} tide")

# ── Load data ─────────────────────────────────────────────────────────────────
wdf = fetch_range(date_list, fetch_weather) if show_weather else pd.DataFrame()
vdf = fetch_range(date_list, fetch_waves)   if show_waves   else pd.DataFrame()
tdf = fetch_range(date_list, fetch_tides)   if show_tides   else pd.DataFrame()

# ── CALENDAR VIEW ─────────────────────────────────────────────────────────────
if mode == "Calendar overview":
    st.title("📅 Calendar Overview")

    if not wdf.empty:
        wdf["date"] = wdf["dt"].dt.date
        daily_w = wdf.groupby("date").agg(
            avg_temp=("temp_c", "mean"),
            max_gust=("wind_gust_kmh", "max"),
        ).reset_index()

        st.markdown('<div class="section-header">Average Temperature by Day</div>', unsafe_allow_html=True)
        fig = go.Figure(go.Bar(
            x=daily_w["date"].astype(str), y=daily_w["avg_temp"],
            marker_color=daily_w["avg_temp"], marker_colorscale="RdYlBu_r",
            text=daily_w["avg_temp"].apply(lambda v: f"{v:.1f}°C"), textposition="outside",
        ))
        fig.update_layout(**base_layout(250, "Avg Temperature (°C)"))
        st.plotly_chart(fig, width="stretch")

    if not vdf.empty:
        vdf["date"] = vdf["dt"].dt.date
        daily_v = vdf.groupby("date").agg(
            avg_hs=("hs_m", "mean"), max_hs=("hs_m", "max"), avg_tp=("tp_s", "mean"),
        ).reset_index()

        st.markdown('<div class="section-header">Wave Height by Day</div>', unsafe_allow_html=True)
        fig = go.Figure(go.Bar(
            x=daily_v["date"].astype(str), y=daily_v["avg_hs"],
            marker_color=daily_v["avg_hs"], marker_colorscale="Blues",
            text=daily_v["avg_hs"].apply(lambda v: f"{v:.1f}m"), textposition="outside",
        ))
        fig.update_layout(**base_layout(280, "Avg Significant Wave Height (m)"))
        st.plotly_chart(fig, width="stretch")

        fig = make_subplots(specs=[[{"secondary_y": True}]])
        fig.add_trace(go.Bar(x=daily_v["date"].astype(str), y=daily_v["max_hs"],
                             name="Max Hs (m)", marker_color="#4fc3f7"), secondary_y=False)
        fig.add_trace(go.Scatter(x=daily_v["date"].astype(str), y=daily_v["avg_tp"],
                                 name="Avg Tp (s)", line=dict(color="#ff9800", width=2)), secondary_y=True)
        layout = base_layout(300, "Max Wave Height & Peak Period")
        fig.update_layout(**layout)
        fig.update_yaxes(title_text="Max Hs (m)", secondary_y=False, gridcolor="#2a2a3a")
        fig.update_yaxes(title_text="Avg Period (s)", secondary_y=True, gridcolor="#2a2a3a")
        st.plotly_chart(fig, width="stretch")
    st.stop()

# ── SINGLE DAY / RANGE ────────────────────────────────────────────────────────
label = date_list[0] if len(date_list) == 1 else f"{date_list[0]} → {date_list[-1]}"
st.title("🌊 Double Island Point")
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
            metric_card("Max Wind Gust",
                        fmt(pd.to_numeric(wdf["wind_gust_kmh"], errors="coerce").max(), " km/h"),
                        f"Avg {fmt(pd.to_numeric(wdf['wind_speed_kmh'], errors='coerce').mean(), ' km/h')}")
        i += 1
        with cols[i % 4]:
            metric_card("Rainfall", fmt(pd.to_numeric(wdf["rainfall_mm"], errors="coerce").sum(), " mm"), "total")
        i += 1
        with cols[i % 4]:
            metric_card("Avg Pressure", fmt(pd.to_numeric(wdf["pressure_hpa"], errors="coerce").mean(), " hPa"))
        i += 1
    if not vdf.empty:
        with cols[i % 4]:
            metric_card("Avg Hs", f"{fmt(vdf['hs_m'].mean(), ' m')}  ·  Max {fmt(vdf['hs_m'].max(), ' m')}")
        i += 1
        with cols[i % 4]:
            metric_card("Max Hmax", fmt(vdf["hmax_m"].max(), " m"))
        i += 1
        with cols[i % 4]:
            metric_card("Avg Peak Period", fmt(vdf["tp_s"].mean(), " s"))
        i += 1
        with cols[i % 4]:
            metric_card("Sea Surface Temp", fmt(vdf["sst_c"].mean(), "°C"))

# ── Weather charts ────────────────────────────────────────────────────────────
if show_weather and not wdf.empty:
    st.markdown('<div class="section-header">🌤 Weather Station — Double Island Point</div>', unsafe_allow_html=True)

    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(go.Scatter(x=wdf["dt"], y=wdf["temp_c"], name="Temp (°C)",
                             line=dict(color="#ff7043", width=2)), secondary_y=False)
    fig.add_trace(go.Scatter(x=wdf["dt"], y=wdf["feels_like_c"], name="Feels Like (°C)",
                             line=dict(color="#ffb74d", width=1.5, dash="dot")), secondary_y=False)
    fig.add_trace(go.Scatter(x=wdf["dt"], y=wdf["humidity_pct"], name="Humidity (%)",
                             line=dict(color="#4fc3f7", width=1.5), opacity=0.7), secondary_y=True)
    fig.update_layout(**base_layout(300, "Temperature & Humidity"))
    fig.update_yaxes(title_text="°C", secondary_y=False, gridcolor="#2a2a3a")
    fig.update_yaxes(title_text="Humidity %", secondary_y=True, gridcolor="#2a2a3a", range=[0, 110])
    st.plotly_chart(fig, width="stretch")

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=wdf["dt"],
                             y=pd.to_numeric(wdf["wind_gust_kmh"], errors="coerce"),
                             name="Gust (km/h)", fill="tozeroy",
                             fillcolor="rgba(100,181,246,0.15)",
                             line=dict(color="#64b5f6", width=1.5)))
    fig.add_trace(go.Scatter(x=wdf["dt"],
                             y=pd.to_numeric(wdf["wind_speed_kmh"], errors="coerce"),
                             name="Speed (km/h)", line=dict(color="#1565c0", width=2)))
    fig.update_layout(**base_layout(250, "Wind Speed & Gusts"))
    st.plotly_chart(fig, width="stretch")

    c1, c2 = st.columns(2)
    with c1:
        press = pd.to_numeric(wdf["pressure_hpa"], errors="coerce")
        p_min, p_max = press.min(), press.max()
        p_buf = max((p_max - p_min) * 0.5, 1.0)
        fig = go.Figure(go.Scatter(x=wdf["dt"], y=press,
                                   line=dict(color="#ce93d8", width=2),
                                   fill="tozeroy", fillcolor="rgba(206,147,216,0.1)"))
        layout = base_layout(250, "Pressure (hPa)")
        layout["yaxis"] = dict(range=[p_min - p_buf, p_max + p_buf], gridcolor="#2a2a3a")
        fig.update_layout(**layout)
        st.plotly_chart(fig, width="stretch")
    with c2:
        fig = go.Figure(go.Bar(x=wdf["dt"],
                               y=pd.to_numeric(wdf["rainfall_mm"], errors="coerce"),
                               marker_color="#80cbc4"))
        fig.update_layout(**base_layout(250, "Rainfall (mm)"))
        st.plotly_chart(fig, width="stretch")

    st.markdown('<div class="section-header">Wind Direction Rose</div>', unsafe_allow_html=True)
    wind_dir_map = {"N":0,"NNE":22.5,"NE":45,"ENE":67.5,"E":90,"ESE":112.5,
                    "SE":135,"SSE":157.5,"S":180,"SSW":202.5,"SW":225,"WSW":247.5,
                    "W":270,"WNW":292.5,"NW":315,"NNW":337.5}
    wdf_wind = wdf[wdf["wind_dir"].isin(wind_dir_map)].copy()
    wdf_wind["wind_deg"] = wdf_wind["wind_dir"].map(wind_dir_map)
    wdf_wind["wind_speed_num"] = pd.to_numeric(wdf_wind["wind_speed_kmh"], errors="coerce")
    wdf_wind["speed_bin"] = pd.cut(wdf_wind["wind_speed_num"],
                                   bins=[0,20,40,60,80,200],
                                   labels=["0–20","20–40","40–60","60–80","80+"])
    fig = go.Figure()
    for lbl, color in zip(["0–20","20–40","40–60","60–80","80+"],
                           ["#b3e5fc","#4fc3f7","#0288d1","#01579b","#003c6e"]):
        sub = wdf_wind[wdf_wind["speed_bin"] == lbl]
        if not sub.empty:
            fig.add_trace(go.Barpolar(r=[1]*len(sub), theta=sub["wind_deg"],
                                      name=f"{lbl} km/h", marker_color=color, opacity=0.85))
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="#0e1117",
        font_color="#ccc", height=380,
        polar=dict(bgcolor="#0e1117", radialaxis=dict(visible=False),
                   angularaxis=dict(direction="clockwise", tickmode="array",
                                    tickvals=[0,45,90,135,180,225,270,315],
                                    ticktext=["N","NE","E","SE","S","SW","W","NW"],
                                    gridcolor="#2a2a3a")),
        legend=dict(bgcolor="rgba(0,0,0,0)"),
    )
    st.plotly_chart(fig, width="stretch")

# ── Wave charts ───────────────────────────────────────────────────────────────
if show_waves and not vdf.empty:
    st.markdown('<div class="section-header">🌊 Wave Buoy — Wide Bay</div>', unsafe_allow_html=True)

    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(go.Scatter(x=vdf["dt"], y=vdf["hs_m"], name="Hs (m)",
                             fill="tozeroy", fillcolor="rgba(79,195,247,0.15)",
                             line=dict(color="#4fc3f7", width=2)), secondary_y=False)
    fig.add_trace(go.Scatter(x=vdf["dt"], y=vdf["hmax_m"], name="Hmax (m)",
                             line=dict(color="#0288d1", width=1.5, dash="dot")), secondary_y=False)
    fig.add_trace(go.Scatter(x=vdf["dt"], y=vdf["tp_s"], name="Peak Period (s)",
                             line=dict(color="#ff9800", width=1.5)), secondary_y=True)
    fig.update_layout(**base_layout(320, "Wave Height & Period"))
    fig.update_yaxes(title_text="Height (m)", secondary_y=False, gridcolor="#2a2a3a")
    fig.update_yaxes(title_text="Period (s)", secondary_y=True, gridcolor="#2a2a3a")
    st.plotly_chart(fig, width="stretch")

    # SST with zoomed y-axis
    sst_min = vdf["sst_c"].min()
    sst_max = vdf["sst_c"].max()
    sst_buf = max((sst_max - sst_min) * 0.5, 0.5)
    fig = go.Figure(go.Scatter(x=vdf["dt"], y=vdf["sst_c"],
                               line=dict(color="#ef5350", width=2),
                               fill="tozeroy", fillcolor="rgba(239,83,80,0.1)"))
    layout = base_layout(250, "Sea Surface Temperature (°C)")
    layout["yaxis"] = dict(range=[sst_min - sst_buf, sst_max + sst_buf], gridcolor="#2a2a3a")
    fig.update_layout(**layout)
    st.plotly_chart(fig, width="stretch")

    # Wave direction: scatter + rose side by side
    st.markdown('<div class="section-header">Wave Direction</div>', unsafe_allow_html=True)
    dc1, dc2 = st.columns(2)
    with dc1:
        fig = go.Figure(go.Scatter(x=vdf["dt"], y=vdf["dir_deg"],
                                   mode="markers", marker=dict(color="#ba68c8", size=5)))
        layout = base_layout(380, "Direction over Time (°)")
        layout["yaxis"] = dict(range=[0,360], gridcolor="#2a2a3a",
                               tickvals=[0,90,180,270,360],
                               ticktext=["N","E","S","W","N"])
        fig.update_layout(**layout)
        st.plotly_chart(fig, width="stretch")
    with dc2:
        vdf_dir = vdf.dropna(subset=["dir_deg","hs_m"]).copy()
        vdf_dir["hs_bin"] = pd.cut(vdf_dir["hs_m"], bins=[0,0.5,1.0,1.5,2.0,10],
                                   labels=["0–0.5m","0.5–1m","1–1.5m","1.5–2m","2m+"])
        fig = go.Figure()
        for lbl, color in zip(["0–0.5m","0.5–1m","1–1.5m","1.5–2m","2m+"],
                               ["#e3f2fd","#90caf9","#42a5f5","#1565c0","#0d47a1"]):
            sub = vdf_dir[vdf_dir["hs_bin"] == lbl]
            if not sub.empty:
                fig.add_trace(go.Barpolar(r=[1]*len(sub), theta=sub["dir_deg"],
                                          name=lbl, marker_color=color, opacity=0.85))
        fig.update_layout(
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="#0e1117",
            font_color="#ccc", height=380,
            polar=dict(bgcolor="#0e1117", radialaxis=dict(visible=False),
                       angularaxis=dict(direction="clockwise", tickmode="array",
                                        tickvals=[0,45,90,135,180,225,270,315],
                                        ticktext=["N","NE","E","SE","S","SW","W","NW"],
                                        gridcolor="#2a2a3a")),
            legend=dict(bgcolor="rgba(0,0,0,0)"),
        )
        st.plotly_chart(fig, width="stretch")

# ── Tide chart ────────────────────────────────────────────────────────────────
if show_tides and not tdf.empty:
    st.markdown('<div class="section-header">🌊 Tides — Tin Can Bay Approaches</div>', unsafe_allow_html=True)

    # Interpolate per day to avoid connecting across day gaps
    tdf_sorted = tdf.sort_values("dt").reset_index(drop=True)
    dense_dts, dense_hs = [], []
    for day, group in tdf_sorted.groupby(tdf_sorted["dt"].dt.date):
        if len(group) < 2:
            continue
        # Use .timestamp() for correct float seconds since epoch
        ts = group["dt"].apply(lambda x: x.timestamp()).values
        hs = group["height_m"].values
        d_ts = np.linspace(ts.min(), ts.max(), 200)
        d_hs = np.interp(d_ts, ts, hs)
        dense_dts.extend([pd.Timestamp.fromtimestamp(t) for t in d_ts])
        dense_hs.extend(d_hs.tolist())
        dense_dts.append(None)  # break line between days
        dense_hs.append(None)

    highs = tdf_sorted[tdf_sorted["type"] == "high"]
    lows  = tdf_sorted[tdf_sorted["type"] == "low"]

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=dense_dts, y=dense_hs, name="Tide height (m)",
                             fill="tozeroy", fillcolor="rgba(100,181,246,0.15)",
                             line=dict(color="#64b5f6", width=2),
                             connectgaps=False))
    fig.add_trace(go.Scatter(x=highs["dt"], y=highs["height_m"],
                             mode="markers+text", name="High tide",
                             marker=dict(color="#ff7043", size=10, symbol="triangle-up"),
                             text=highs["height_m"].apply(lambda v: f"{v:.2f}m"),
                             textposition="top center", textfont=dict(color="#ff7043")))
    fig.add_trace(go.Scatter(x=lows["dt"], y=lows["height_m"],
                             mode="markers+text", name="Low tide",
                             marker=dict(color="#80cbc4", size=10, symbol="triangle-down"),
                             text=lows["height_m"].apply(lambda v: f"{v:.2f}m"),
                             textposition="bottom center", textfont=dict(color="#80cbc4")))
    fig.update_layout(**base_layout(300, "Tide Predictions (AEST)"))
    st.plotly_chart(fig, width="stretch")

# ── Correlations ──────────────────────────────────────────────────────────────
if show_waves and show_weather and not vdf.empty and not wdf.empty:
    st.markdown('<div class="section-header">📊 Correlations</div>', unsafe_allow_html=True)
    wdf_r = wdf.set_index("dt").resample("30min").mean(numeric_only=True).reset_index()
    vdf_r = vdf.set_index("dt").resample("30min").mean(numeric_only=True).reset_index()
    merged = pd.merge_asof(vdf_r.sort_values("dt"), wdf_r.sort_values("dt"),
                           on="dt", tolerance=pd.Timedelta("30min"), direction="nearest")

    CORR_COLS = {
        "Sig. Wave Height (Hs)": "hs_m",
        "Max Wave Height (Hmax)": "hmax_m",
        "Peak Period (Tp)": "tp_s",
        "Zero-crossing Period (Tz)": "tz_s",
        "Wave Direction (°)": "dir_deg",
        "Sea Surface Temp (°C)": "sst_c",
        "Air Temp (°C)": "temp_c",
        "Feels Like (°C)": "feels_like_c",
        "Humidity (%)": "humidity_pct",
        "Wind Speed (km/h)": "wind_speed_kmh",
        "Wind Gust (km/h)": "wind_gust_kmh",
        "Pressure (hPa)": "pressure_hpa",
    }
    available = {k: v for k, v in CORR_COLS.items() if v in merged.columns and merged[v].notna().any()}
    col_labels = list(available.keys())

    cc1, cc2, cc3 = st.columns(3)
    with cc1:
        x_label = st.selectbox("X axis", col_labels, index=col_labels.index("Wind Speed (km/h)") if "Wind Speed (km/h)" in col_labels else 0)
    with cc2:
        y_label = st.selectbox("Y axis", col_labels, index=col_labels.index("Sig. Wave Height (Hs)") if "Sig. Wave Height (Hs)" in col_labels else 1)
    with cc3:
        c_label = st.selectbox("Colour by", col_labels, index=col_labels.index("Peak Period (Tp)") if "Peak Period (Tp)" in col_labels else 2)

    x_col = available[x_label]
    y_col = available[y_label]
    c_col = available[c_label]

    plot_df = merged[[x_col, y_col, c_col, "dt"]].dropna()
    if not plot_df.empty:
        fig = px.scatter(plot_df, x=x_col, y=y_col, color=c_col,
                         color_continuous_scale="Blues",
                         hover_data={"dt": True},
                         labels={x_col: x_label, y_col: y_label, c_col: c_label},
                         title=f"{x_label} vs {y_label}")
        fig.update_layout(**base_layout(400))
        st.plotly_chart(fig, width="stretch")
    else:
        st.info("Not enough overlapping data for the selected columns.")
