const BOM_URL = "https://www.bom.gov.au/fwo/IDQ60801/IDQ60801.94584.json";

const BOM_HEADERS = {
  "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
  "Accept": "application/json, text/plain, */*",
  "Referer": "https://www.bom.gov.au/places/qld/cooloola/observations/double-island--point/",
};

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    if (url.pathname === "/run" || url.pathname === "/") {
      return await saveDailyData(env);
    }

    if (url.pathname === "/debug") {
      const res = await fetch(BOM_URL, { headers: BOM_HEADERS });
      const data = await res.json();
      return new Response(JSON.stringify(data.observations?.data?.[0] || {}, null, 2), {
        headers: { "Content-Type": "application/json" },
      });
    }

    if (url.pathname === "/list") {
      const listed = await env.weather_bucket.list({ prefix: "WeatherStation/" });
      const keys = listed.objects.map((o) => o.key);
      return new Response(JSON.stringify(keys, null, 2), {
        headers: { "Content-Type": "application/json" },
      });
    }

    if (url.pathname.startsWith("/data/")) {
      const key = url.pathname.replace("/data/", "WeatherStation/");
      const obj = await env.weather_bucket.get(key);
      if (!obj) return new Response("Not found", { status: 404 });
      return new Response(obj.body, {
        headers: { "Content-Type": "application/json" },
      });
    }

    return new Response("Not found", { status: 404 });
  },

  async scheduled(event, env) {
    await saveDailyData(env);
  },
};

async function saveDailyData(env) {
  try {
    const res = await fetch(BOM_URL, { headers: BOM_HEADERS });

    if (!res.ok) {
      return new Response(`BOM fetch failed: ${res.status}`, { status: 502 });
    }

    const bomData = await res.json();
    const observations = bomData?.observations?.data;

    if (!Array.isArray(observations)) {
      return new Response("Unexpected BOM data format", { status: 502 });
    }

    const records = observations.map((o) => ({
      local_date_time: o.local_date_time_full,
      temp_c: o.air_temp,
      feels_like_c: o.apparent_t,
      humidity_pct: o.rel_hum,
      wind_dir: o.wind_dir,
      wind_speed_kmh: o.wind_spd_kmh,
      wind_gust_kmh: o.gust_kmh,
      pressure_hpa: o.press,
      rainfall_mm: o.rain_trace,
    }));

    // Group records by their own date (YYYYMMDD -> YYYY-MM-DD)
    const byDate = {};
    for (const rec of records) {
      const dateKey = rec.local_date_time.slice(0, 4) + "-" + rec.local_date_time.slice(4, 6) + "-" + rec.local_date_time.slice(6, 8);
      if (!byDate[dateKey]) byDate[dateKey] = [];
      byDate[dateKey].push(rec);
    }

    const results = {};

    for (const [dateKey, newRecs] of Object.entries(byDate)) {
      const filename = `WeatherStation/${dateKey}.json`;

      const existingObj = await env.weather_bucket.get(filename);
      let existingRecords = [];
      if (existingObj) {
        existingRecords = await existingObj.json();
      }

      const merged = [...existingRecords, ...newRecs];
      const seen = new Set();
      const deduped = [];
      for (const rec of merged) {
        if (!seen.has(rec.local_date_time)) {
          seen.add(rec.local_date_time);
          deduped.push(rec);
        }
      }
      deduped.sort((a, b) => a.local_date_time.localeCompare(b.local_date_time));

      await env.weather_bucket.put(filename, JSON.stringify(deduped, null, 2), {
        httpMetadata: { contentType: "application/json" },
      });

      results[filename] = deduped.length;
    }

    return new Response(
      JSON.stringify({ status: "ok", files_updated: results, fetched: records.length }, null, 2),
      { headers: { "Content-Type": "application/json" } }
    );
  } catch (err) {
    return new Response(`Error: ${err.message}`, { status: 500 });
  }
}
