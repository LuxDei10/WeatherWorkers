// Wide Bay Wave Buoy + Tide Archiver — Cloudflare Worker
// CSV columns used:
// 0 Site, 1 SiteID, 3 ISOdatetime, 4 Lat, 5 Lon,
// 6 Hs, 7 Hmax, 8 Tp, 9 Tz, 10 SST, 11 Dir
// (unix_ts and current_speed excluded)
//
// R2 binding name: weather_bucket
// Wave data  → WaveBuoy/YYYY-MM-DD.json
// Tide data  → Tides/YYYY-MM-DD.json

const WAVE_URL = "https://apps.des.qld.gov.au/data-sets/waves/wave-7dayopdata.csv";

function tideTableUrl() {
  const now  = new Date(Date.now() + 10 * 3600 * 1000); // AEST
  const dd   = String(now.getUTCDate()).padStart(2, "0");
  const mm   = String(now.getUTCMonth() + 1).padStart(2, "0");
  const yyyy = now.getUTCFullYear();
  return `https://www.bom.gov.au/australia/tides/scripts/getTidesTable.php` +
    `?type=tide&aac=QLD_TP151&date=${dd}-${mm}-${yyyy}&days=3` +
    `&region=QLD&offset=0&tz=Australia%2FBrisbane&tz_js=AEST`;
}

// Convert UTC ISO string to AEST (UTC+10, no DST in QLD)
function utcToAest(utcString) {
  const utcMs = new Date(utcString).getTime();
  const aestMs = utcMs + 10 * 3600 * 1000;
  const d = new Date(aestMs);
  const pad = (n) => String(n).padStart(2, "0");
  return `${d.getUTCFullYear()}-${pad(d.getUTCMonth() + 1)}-${pad(d.getUTCDate())}` +
    `T${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())}:${pad(d.getUTCSeconds())}+10:00`;
}

function parseTideHtml(html) {
  const events = [];
  const timeRe = /data-time-utc="(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z)"/g;
  const positions = [];
  let m;
  while ((m = timeRe.exec(html)) !== null) {
    positions.push({ index: m.index, utc: m[1] });
  }

  for (let i = 0; i < positions.length; i++) {
    const pos = positions[i];
    const utcMs = new Date(pos.utc).getTime();
    if (isNaN(utcMs)) { continue; }

    const before      = html.substring(Math.max(0, pos.index - 400), pos.index);
    const typeMatches = [...before.matchAll(/class="instance (high|low)-tide"/g)];
    if (typeMatches.length === 0) { continue; }
    const type = typeMatches[typeMatches.length - 1][1] === "high" ? "high" : "low";

    const nextIdx = (i + 1 < positions.length) ? positions[i + 1].index : pos.index + 600;
    const between = html.substring(pos.index, nextIdx);
    const hm      = between.match(/class="height[^"]*"[^>]*>\s*([\d.]+)/);
    if (!hm) { continue; }

    const h = parseFloat(hm[1]);
    if (isNaN(h) || h < 0 || h > 10) { continue; }

    const aest_datetime = utcToAest(pos.utc);

    events.push({
      datetime_aest: aest_datetime,
      type,                         // "high" or "low"
      height_m: h,
    });
  }
  return events;
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    if (url.pathname === "/run" || url.pathname === "/") {
      return await saveDailyData(env);
    }

    if (url.pathname === "/debug") {
      const res = await fetch(WAVE_URL);
      const csv = await res.text();
      const rows = csv.split("\n").filter((r) => r.toLowerCase().includes("wide bay"));
      const last = rows[rows.length - 1]?.split(",") || [];
      return new Response(
        JSON.stringify({ totalRows: rows.length, lastRowCols: last.map((v, i) => ({ i, v: v.trim() })) }, null, 2),
        { headers: { "Content-Type": "application/json" } }
      );
    }

    if (url.pathname === "/list/waves") {
      const listed = await env.weather_bucket.list({ prefix: "WaveBuoy/" });
      return new Response(JSON.stringify(listed.objects.map((o) => o.key), null, 2), { headers: { "Content-Type": "application/json" } });
    }

    if (url.pathname === "/list/tides") {
      const listed = await env.weather_bucket.list({ prefix: "Tides/" });
      return new Response(JSON.stringify(listed.objects.map((o) => o.key), null, 2), { headers: { "Content-Type": "application/json" } });
    }

    if (url.pathname.startsWith("/waves/")) {
      const dateKey = url.pathname.replace("/waves/", "");
      const obj = await env.weather_bucket.get(`WaveBuoy/${dateKey}.json`);
      if (!obj) return new Response("Not found", { status: 404 });
      return new Response(obj.body, { headers: { "Content-Type": "application/json" } });
    }

    if (url.pathname.startsWith("/tides/")) {
      const dateKey = url.pathname.replace("/tides/", "");
      const obj = await env.weather_bucket.get(`Tides/${dateKey}.json`);
      if (!obj) return new Response("Not found", { status: 404 });
      return new Response(obj.body, { headers: { "Content-Type": "application/json" } });
    }

    return new Response([
      "Available endpoints:",
      "  /run              — fetch and save all data",
      "  /debug            — inspect raw CSV columns",
      "  /list/waves       — list saved wave files",
      "  /list/tides       — list saved tide files",
      "  /waves/YYYY-MM-DD — retrieve a day's wave data",
      "  /tides/YYYY-MM-DD — retrieve a day's tide data",
    ].join("\n"), { status: 200 });
  },

  async scheduled(event, env) {
    await saveDailyData(env);
  },
};

async function saveDailyData(env) {
  try {
    const [waveRes, tableRes] = await Promise.allSettled([
      fetch(WAVE_URL),
      fetch(tideTableUrl(), {
        headers: {
          "User-Agent": "Mozilla/5.0 (compatible; WaveArchiver/1.0)",
          "Referer": "https://www.bom.gov.au/australia/tides/",
        },
      }),
    ]);

    if (waveRes.status !== "fulfilled" || !waveRes.value.ok) {
      return new Response(`Wave fetch failed: ${waveRes.status === "fulfilled" ? waveRes.value.status : waveRes.reason}`, { status: 502 });
    }

    // ── Wave records ──────────────────────────────────────────
    const csv = await waveRes.value.text();
    const waveRecords = [];

    for (const row of csv.split("\n")) {
      const c = row.split(",");
      if (c.length < 12) continue;
      if (!c[0].trim().toLowerCase().includes("wide bay")) continue;

      const hs = parseFloat(c[6]);
      const tp = parseFloat(c[8]);
      if (isNaN(hs) || hs <= 0 || hs > 20 || isNaN(tp) || tp <= 0) continue;

      waveRecords.push({
        local_date_time: c[3].trim(),   // ISO local "YYYY-MM-DDTHH:mm:ss"
        lat: parseFloat(c[4]),
        lon: parseFloat(c[5]),
        hs_m: hs,
        hmax_m: parseFloat(c[7]),
        tp_s: tp,
        tz_s: parseFloat(c[9]),
        sst_c: parseFloat(c[10]),
        dir_deg: parseFloat(c[11]),
      });
    }

    if (!waveRecords.length) {
      return new Response("No wide bay rows found", { status: 502 });
    }

    // ── Tide events ───────────────────────────────────────────
    let tideEvents = [];
    if (tableRes.status === "fulfilled" && tableRes.value.ok) {
      try {
        const html = await tableRes.value.text();
        tideEvents = parseTideHtml(html);
      } catch (_) {}
    }

    // ── Group waves by date ───────────────────────────────────
    const wavesByDate = {};
    for (const rec of waveRecords) {
      const dateKey = rec.local_date_time.slice(0, 10);
      if (!wavesByDate[dateKey]) wavesByDate[dateKey] = [];
      wavesByDate[dateKey].push(rec);
    }

    // ── Group tides by AEST date ──────────────────────────────
    const tidesByDate = {};
    for (const ev of tideEvents) {
      const dateKey = ev.datetime_aest.slice(0, 10);
      if (!tidesByDate[dateKey]) tidesByDate[dateKey] = [];
      tidesByDate[dateKey].push(ev);
    }

    const results = { waves: {}, tides: {} };

    // ── Save wave files ───────────────────────────────────────
    for (const [dateKey, newRecs] of Object.entries(wavesByDate)) {
      const filename = `WaveBuoy/${dateKey}.json`;
      const existingObj = await env.weather_bucket.get(filename);
      let existing = [];
      if (existingObj) {
        try { const parsed = await existingObj.json(); if (Array.isArray(parsed)) existing = parsed; } catch (_) {}
      }

      const merged = [...existing, ...newRecs];
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
      results.waves[filename] = deduped.length;
    }

    // ── Save tide files ───────────────────────────────────────
    for (const [dateKey, newEvs] of Object.entries(tidesByDate)) {
      const filename = `Tides/${dateKey}.json`;
      const existingObj = await env.weather_bucket.get(filename);
      let existing = [];
      if (existingObj) {
        try { const parsed = await existingObj.json(); if (Array.isArray(parsed)) existing = parsed; } catch (_) {}
      }

      const merged = [...existing, ...newEvs];
      const seen = new Set();
      const deduped = [];
      for (const ev of merged) {
        if (!seen.has(ev.datetime_aest)) {
          seen.add(ev.datetime_aest);
          deduped.push(ev);
        }
      }
      deduped.sort((a, b) => a.datetime_aest.localeCompare(b.datetime_aest));

      await env.weather_bucket.put(filename, JSON.stringify(deduped, null, 2), {
        httpMetadata: { contentType: "application/json" },
      });
      results.tides[filename] = deduped.length;
    }

    return new Response(
      JSON.stringify({
        status: "ok",
        fetched_waves: waveRecords.length,
        fetched_tides: tideEvents.length,
        files_updated: results,
      }, null, 2),
      { headers: { "Content-Type": "application/json" } }
    );
  } catch (err) {
    return new Response(`Error: ${err.message}`, { status: 500 });
  }
}
