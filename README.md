# Weather Workers

Cloudflare Workers that fetch and archive weather and ocean data for the Cooloola / Wide Bay region (Queensland, Australia) into a shared Cloudflare R2 bucket. Data is grouped by date and stored as JSON files, building a permanent historical record that can be queried by date from any server or script.

---

## Data Sources

| Source | Data | Update Frequency |
|---|---|---|
| Bureau of Meteorology (BOM) | Air temp, feels like, humidity, wind speed/direction/gust, pressure, rainfall | Every 10–30 min |
| QLD DES Wave Buoy | Significant wave height, max wave height, peak period, zero-crossing period, sea surface temp, wave direction | Every 30 min |
| Bureau of Meteorology (BOM) | Tide predictions (high/low, height in metres) | Daily fetch, 3-day window |

---

## R2 Bucket Structure

All workers write to a single shared R2 bucket. Data is organised into folders by source:

```
weather-bucket/
├── WeatherStation/
│   ├── 2026-06-13.json
│   ├── 2026-06-14.json
│   └── ...
├── WaveBuoy/
│   ├── 2026-06-13.json
│   ├── 2026-06-14.json
│   └── ...
└── Tides/
    ├── 2026-06-13.json
    ├── 2026-06-14.json
    └── ...
```

Each file contains all observations for that day, sorted by time. Re-running a worker merges and deduplicates — no data is overwritten or lost.

---

## Workers

### 1. `weather-station/bom-weather-station.js`

Fetches observations from the **Double Island Point** weather station (BOM station IDQ60801.94584).

**R2 folder:** `WeatherStation/`

**Each record:**
```json
{
  "local_date_time": "20260613143000",
  "temp_c": 21.0,
  "feels_like_c": 14.2,
  "humidity_pct": 72,
  "wind_dir": "SE",
  "wind_speed_kmh": 46,
  "wind_gust_kmh": 54,
  "pressure_hpa": 1027.0,
  "rainfall_mm": "0.0"
}
```

**Endpoints:**
| URL | Description |
|---|---|
| `/run` | Fetch from BOM and save to R2 |
| `/debug` | Inspect raw BOM response (first record) |
| `/list` | List all saved date files |
| `/data/YYYY-MM-DD` | Retrieve a specific day's data |

**Cron:** `0 22 * * *` (8:00 AM AEST daily)

---

### 2. `wave-buoy/wave-buoy-archiver.js`

Fetches wave observations from the **Wide Bay Wave Buoy** (QLD DES) and tide predictions for **Tin Can Bay / Double Island Point** (BOM QLD_TP151).

**R2 folders:** `WaveBuoy/` and `Tides/`

**Each wave record:**
```json
{
  "local_date_time": "2026-06-13T14:00:00",
  "lat": -25.48,
  "lon": 153.17,
  "hs_m": 1.2,
  "hmax_m": 1.8,
  "tp_s": 8.5,
  "tz_s": 6.1,
  "sst_c": 23.4,
  "dir_deg": 135
}
```

**Each tide record:**
```json
{
  "datetime_aest": "2026-06-13T14:32:00+10:00",
  "type": "high",
  "height_m": 1.84
}
```

**Endpoints:**
| URL | Description |
|---|---|
| `/run` | Fetch wave + tide data and save to R2 |
| `/debug` | Inspect raw CSV columns from wave buoy |
| `/list/waves` | List saved wave files |
| `/list/tides` | List saved tide files |
| `/waves/YYYY-MM-DD` | Retrieve a day's wave data |
| `/tides/YYYY-MM-DD` | Retrieve a day's tide data |

**Cron:** `0 22 * * *` (8:00 AM AEST daily) — can be run more frequently (e.g. every 6 hours) to improve backfill safety

---

## Cloudflare Setup

Both workers share the same R2 bucket binding:

| Setting | Value |
|---|---|
| R2 binding variable name | `weather_bucket` |
| Bucket name | your bucket name (e.g. `weather-data`) |

Each worker is deployed separately with its own cron trigger.

---

## Notes

- All times are **AEST (UTC+10)**. Queensland does not observe daylight saving, so this offset is fixed year-round.
- BOM's observation feed returns a rolling ~4-day window. The worker groups records by their own date, so each daily file only contains observations that actually occurred on that day.
- The wave buoy CSV covers ~7 days. Running the worker once daily is sufficient to maintain a complete archive with no gaps.
- Tide predictions come from BOM's tide table for station **QLD_TP151** (Tin Can Bay approaches), which covers the Wide Bay / Double Island Point area.
