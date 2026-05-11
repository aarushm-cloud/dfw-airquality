"""End-to-end smoke test for the AERIA live deploy.

Exercises the Render API + Vercel frontend and prints a structured report.
Run from the project root:

    python scripts/smoke_test.py

Or with custom URLs:

    API_BASE=http://localhost:8000 WEB_BASE=http://localhost:5173 python scripts/smoke_test.py
    python scripts/smoke_test.py --api-base http://localhost:8000 --web-base http://localhost:5173

No commits, no file writes, no side effects on the deploy.
"""

import argparse
import os
import re
import sys
import time
from urllib.parse import urlparse

import requests

DEFAULT_API_BASE = "https://aeria-api.onrender.com"
DEFAULT_WEB_BASE = "https://dfw-airquality.vercel.app"
PER_REQUEST_TIMEOUT = 120


def fmt_ms(seconds: float) -> str:
    return f"{seconds * 1000:.0f} ms"


def shorten(s: str, n: int = 80) -> str:
    s = str(s)
    return s if len(s) <= n else s[: n - 1] + "…"


class Results:
    def __init__(self) -> None:
        self.rows: list[dict] = []
        self.passes: list[str] = []
        self.fails: list[tuple[str, str]] = []

    def add_row(self, check: str, elapsed: float | None, notes: str) -> None:
        self.rows.append({"check": check, "elapsed": elapsed, "notes": notes})

    def passed(self, name: str) -> None:
        self.passes.append(name)

    def failed(self, name: str, reason: str) -> None:
        self.fails.append((name, reason))


def make_session() -> requests.Session:
    s = requests.Session()
    # Disable keep-alive so every request pays a fresh TCP/TLS handshake.
    # Matches a real browser's per-tab behavior more closely than a pool of
    # warm sockets would.
    s.headers["Connection"] = "close"
    return s


def check_1_health_cold(session: requests.Session, api_base: str, r: Results) -> dict | None:
    name = "1. Health cold-read"
    print(f"\n[{name}] GET /api/health")
    t0 = time.time()
    resp = session.get(f"{api_base}/api/health", timeout=PER_REQUEST_TIMEOUT)
    elapsed = time.time() - t0
    if resp.status_code != 200:
        r.failed(name, f"HTTP {resp.status_code}")
        r.add_row("/api/health (1)", elapsed, f"HTTP {resp.status_code}")
        print(f"  FAIL: HTTP {resp.status_code} body={shorten(resp.text)}")
        return None
    data = resp.json()
    cache_warm = data.get("cache_warm")
    uptime = data.get("uptime_seconds")
    print(f"  PASS in {fmt_ms(elapsed)}  cache_warm={cache_warm}  uptime_seconds={uptime}")
    print(f"  → Cache was {'already warm' if cache_warm else 'COLD'} before any user-facing request.")
    r.passed(name)
    r.add_row("/api/health (1)", elapsed, f"cache_warm={cache_warm} uptime={uptime}s")
    return data


def check_2_grid_first(
    session: requests.Session, api_base: str, r: Results, cache_warm_before: bool
) -> tuple[float | None, dict | None]:
    name = "2. Grid first call"
    label = "cache hit" if cache_warm_before else "cold path"
    print(f"\n[{name}] GET /api/grid  (expecting: {label})")
    t0 = time.time()
    resp = session.get(f"{api_base}/api/grid", timeout=PER_REQUEST_TIMEOUT)
    elapsed = time.time() - t0
    if resp.status_code != 200:
        r.failed(name, f"HTTP {resp.status_code}")
        r.add_row(f"/api/grid ({label})", elapsed, f"HTTP {resp.status_code}")
        print(f"  FAIL: HTTP {resp.status_code} body={shorten(resp.text)}")
        return elapsed, None
    data = resp.json()
    res = data.get("resolution")
    sensor_count = data.get("sensor_count")
    avg = data.get("avg_pm25")
    print(
        f"  PASS in {fmt_ms(elapsed)}  resolution={res}  sensors={sensor_count}  avg_pm25={avg:.2f}"
    )
    r.passed(name)
    r.add_row(f"/api/grid ({label})", elapsed, f"res={res} sensors={sensor_count}")
    return elapsed, data


def check_3_grid_second(
    session: requests.Session, api_base: str, r: Results, first_elapsed: float | None
) -> float | None:
    name = "3. Grid second call"
    print(f"\n[{name}] GET /api/grid  (must be cache hit)")
    t0 = time.time()
    resp = session.get(f"{api_base}/api/grid", timeout=PER_REQUEST_TIMEOUT)
    elapsed = time.time() - t0
    if resp.status_code != 200:
        r.failed(name, f"HTTP {resp.status_code}")
        r.add_row("/api/grid (warm)", elapsed, f"HTTP {resp.status_code}")
        print(f"  FAIL: HTTP {resp.status_code} body={shorten(resp.text)}")
        return elapsed
    delta_note = ""
    if first_elapsed is not None:
        floor = first_elapsed - elapsed
        delta_note = f" (first call was {fmt_ms(first_elapsed)}; warmup floor ≈ {fmt_ms(max(0, floor))})"
    print(f"  PASS in {fmt_ms(elapsed)}{delta_note}")
    r.passed(name)
    r.add_row("/api/grid (warm)", elapsed, "cache hit")
    return elapsed


def check_4_health_post_grid(
    session: requests.Session, api_base: str, r: Results, first_health: dict | None
) -> None:
    name = "4. Health post-grid"
    print(f"\n[{name}] GET /api/health  (cache_warm must be true)")
    t0 = time.time()
    resp = session.get(f"{api_base}/api/health", timeout=PER_REQUEST_TIMEOUT)
    elapsed = time.time() - t0
    if resp.status_code != 200:
        r.failed(name, f"HTTP {resp.status_code}")
        r.add_row("/api/health (2)", elapsed, f"HTTP {resp.status_code}")
        print(f"  FAIL: HTTP {resp.status_code}")
        return
    data = resp.json()
    cache_warm = data.get("cache_warm")
    uptime = data.get("uptime_seconds")
    issues: list[str] = []
    if cache_warm is not True:
        issues.append(f"cache_warm={cache_warm} (expected true)")
    if first_health is not None:
        prev_uptime = first_health.get("uptime_seconds", 0)
        if uptime is not None and uptime < prev_uptime:
            issues.append(f"uptime regressed: {prev_uptime} → {uptime}")
    if issues:
        r.failed(name, "; ".join(issues))
        r.add_row("/api/health (2)", elapsed, "; ".join(issues))
        print(f"  FAIL: {'; '.join(issues)}")
    else:
        print(f"  PASS in {fmt_ms(elapsed)}  cache_warm={cache_warm}  uptime_seconds={uptime}")
        r.passed(name)
        r.add_row("/api/health (2)", elapsed, f"cache_warm={cache_warm} uptime={uptime}s")


def check_5_sensors(session: requests.Session, api_base: str, r: Results) -> None:
    name = "5. Sensors"
    print(f"\n[{name}] GET /api/sensors  (independent cache from /api/grid)")
    t0 = time.time()
    resp = session.get(f"{api_base}/api/sensors", timeout=PER_REQUEST_TIMEOUT)
    elapsed = time.time() - t0
    if resp.status_code != 200:
        r.failed(name, f"HTTP {resp.status_code}")
        r.add_row("/api/sensors", elapsed, f"HTTP {resp.status_code}")
        print(f"  FAIL: HTTP {resp.status_code} body={shorten(resp.text)}")
        return
    data = resp.json()
    count = data.get("count")
    ts = data.get("timestamp")
    print(f"  PASS in {fmt_ms(elapsed)}  count={count}  timestamp={ts}")
    r.passed(name)
    r.add_row("/api/sensors", elapsed, f"count={count}")


CELL_REQUIRED_FIELDS = {
    "zip", "lat", "lon", "cell_lat", "cell_lon", "cell_i", "cell_j",
    "pm25", "aqi_category", "confidence", "neighborhood", "timestamp",
}


def check_6_cell_clean(session: requests.Session, api_base: str, r: Results) -> None:
    name = "6. Cell by zip — 75201 (downtown)"
    print(f"\n[{name}] GET /api/cells/75201")
    t0 = time.time()
    resp = session.get(f"{api_base}/api/cells/75201", timeout=PER_REQUEST_TIMEOUT)
    elapsed = time.time() - t0
    if resp.status_code != 200:
        r.failed(name, f"HTTP {resp.status_code}")
        r.add_row("/api/cells/75201", elapsed, f"HTTP {resp.status_code}")
        print(f"  FAIL: HTTP {resp.status_code} body={shorten(resp.text)}")
        return
    data = resp.json()
    missing = CELL_REQUIRED_FIELDS - set(data.keys())
    if missing:
        r.failed(name, f"missing fields: {sorted(missing)}")
        r.add_row("/api/cells/75201", elapsed, f"missing: {sorted(missing)}")
        print(f"  FAIL: missing fields {sorted(missing)}")
        return
    print(
        f"  PASS in {fmt_ms(elapsed)}  pm25={data['pm25']:.2f}  "
        f"aqi={data['aqi_category']}  zip={data['zip']}  nbhd={data.get('neighborhood')}"
    )
    r.passed(name)
    r.add_row("/api/cells/75201", elapsed, f"pm25={data['pm25']:.2f} {data['aqi_category']}")


def check_7_cell_boundary(session: requests.Session, api_base: str, r: Results) -> None:
    name = "7. Cell by zip — 75025 (boundary case)"
    print(f"\n[{name}] GET /api/cells/75025")
    t0 = time.time()
    resp = session.get(f"{api_base}/api/cells/75025", timeout=PER_REQUEST_TIMEOUT)
    elapsed = time.time() - t0
    if resp.status_code != 200:
        # Frontend disclosure semantics handle the resolved≠typed case, so any
        # 2xx is informational. Anything else is a regression worth surfacing.
        r.failed(name, f"HTTP {resp.status_code}")
        r.add_row("/api/cells/75025", elapsed, f"HTTP {resp.status_code} {shorten(resp.text, 40)}")
        print(f"  FAIL: HTTP {resp.status_code} body={shorten(resp.text)}")
        return
    data = resp.json()
    resolved_zip = data.get("zip")
    nbhd = data.get("neighborhood")
    print(
        f"  PASS in {fmt_ms(elapsed)}  typed=75025  resolved zip={resolved_zip}  "
        f"nbhd={nbhd}  pm25={data.get('pm25')}"
    )
    r.passed(name)
    r.add_row("/api/cells/75025", elapsed, f"resolved zip={resolved_zip}")


def check_8_cells_at(session: requests.Session, api_base: str, r: Results) -> None:
    name = "8. Cells/at coverage"
    print(f"\n[{name}] GET /api/cells/at?lat=32.78&lon=-96.80")
    t0 = time.time()
    resp = session.get(
        f"{api_base}/api/cells/at",
        params={"lat": 32.78, "lon": -96.80},
        timeout=PER_REQUEST_TIMEOUT,
    )
    elapsed = time.time() - t0
    if resp.status_code != 200:
        r.failed(name, f"HTTP {resp.status_code}")
        r.add_row("/api/cells/at", elapsed, f"HTTP {resp.status_code}")
        print(f"  FAIL: HTTP {resp.status_code} body={shorten(resp.text)}")
        return
    data = resp.json()
    in_bbox = data.get("in_bbox")
    issues: list[str] = []
    if in_bbox is not True:
        issues.append(f"in_bbox={in_bbox} (expected true)")
    if issues:
        r.failed(name, "; ".join(issues))
        r.add_row("/api/cells/at", elapsed, "; ".join(issues))
        print(f"  FAIL: {'; '.join(issues)}")
        return
    print(
        f"  PASS in {fmt_ms(elapsed)}  zip={data.get('zip')}  nbhd={data.get('neighborhood')}  "
        f"row={data.get('row')} col={data.get('col')} in_bbox={in_bbox}"
    )
    r.passed(name)
    r.add_row("/api/cells/at", elapsed, f"zip={data.get('zip')} row={data.get('row')} col={data.get('col')}")


def check_9_route_preview(session: requests.Session, api_base: str, r: Results) -> None:
    name = "9. Route preview-mode contract"
    print(f"\n[{name}] POST /api/route  (must return 503 with detail.code='routing_disabled')")
    body = {"start": "Mockingbird Station Dallas", "end": "Klyde Warren Park Dallas"}
    t0 = time.time()
    resp = session.post(f"{api_base}/api/route", json=body, timeout=PER_REQUEST_TIMEOUT)
    elapsed = time.time() - t0
    if resp.status_code != 503:
        r.failed(name, f"HTTP {resp.status_code} (expected 503)")
        r.add_row("/api/route", elapsed, f"HTTP {resp.status_code} (expected 503)")
        print(f"  FAIL: got HTTP {resp.status_code} body={shorten(resp.text)}")
        return
    try:
        data = resp.json()
    except ValueError:
        r.failed(name, "503 body was not JSON")
        r.add_row("/api/route", elapsed, "503 body not JSON")
        print(f"  FAIL: 503 body was not JSON: {shorten(resp.text)}")
        return
    detail = data.get("detail")
    if not isinstance(detail, dict) or detail.get("code") != "routing_disabled":
        r.failed(name, f"detail shape wrong: {detail!r}")
        r.add_row("/api/route", elapsed, f"detail shape wrong")
        print(f"  FAIL: detail.code != 'routing_disabled' — detail={detail!r}")
        return
    print(
        f"  PASS in {fmt_ms(elapsed)}  HTTP 503  detail.code='routing_disabled'  "
        f"message={shorten(detail.get('message'), 60)!r}"
    )
    r.passed(name)
    r.add_row("/api/route", elapsed, "503 routing_disabled")


def check_10_cors_preflight(
    session: requests.Session, api_base: str, web_base: str, r: Results
) -> None:
    name = "10. CORS preflight"
    print(f"\n[{name}] OPTIONS /api/grid  Origin: {web_base}")
    headers = {
        "Origin": web_base,
        "Access-Control-Request-Method": "GET",
        "Access-Control-Request-Headers": "content-type",
    }
    t0 = time.time()
    resp = session.options(f"{api_base}/api/grid", headers=headers, timeout=PER_REQUEST_TIMEOUT)
    elapsed = time.time() - t0
    allow_origin = resp.headers.get("access-control-allow-origin")
    allow_methods = resp.headers.get("access-control-allow-methods", "")
    print(
        f"  HTTP {resp.status_code}  "
        f"allow-origin={allow_origin!r}  allow-methods={allow_methods!r}"
    )
    if allow_origin == web_base:
        print(f"  PASS in {fmt_ms(elapsed)}")
        r.passed(name)
        r.add_row("OPTIONS /api/grid", elapsed, f"allow-origin={allow_origin}")
    else:
        r.failed(name, f"allow-origin={allow_origin!r} (expected {web_base!r})")
        r.add_row("OPTIONS /api/grid", elapsed, f"allow-origin={allow_origin!r}")
        print(f"  FAIL: allow-origin did not match {web_base}")


def check_11_brotli(api_base: str, r: Results) -> None:
    name = "11. Brotli content-encoding"
    print(f"\n[{name}] GET /api/grid  Accept-Encoding: br  (stream + no auto-decode)")
    # Fresh session with stream=True so requests doesn't auto-decompress.
    s = requests.Session()
    s.headers["Connection"] = "close"
    t0 = time.time()
    resp = s.get(
        f"{api_base}/api/grid",
        headers={"Accept-Encoding": "br"},
        stream=True,
        timeout=PER_REQUEST_TIMEOUT,
    )
    # Read raw bytes so Content-Length is the compressed payload size.
    raw_bytes = resp.raw.read(decode_content=False)
    elapsed = time.time() - t0
    enc = resp.headers.get("Content-Encoding")
    clen = resp.headers.get("Content-Length")
    print(
        f"  HTTP {resp.status_code}  Content-Encoding={enc!r}  "
        f"Content-Length={clen}  raw_bytes={len(raw_bytes)}"
    )
    if resp.status_code != 200:
        r.failed(name, f"HTTP {resp.status_code}")
        r.add_row("/api/grid (br)", elapsed, f"HTTP {resp.status_code}")
        return
    if enc == "br":
        print(f"  PASS in {fmt_ms(elapsed)} — brotli active")
        r.passed(name)
        r.add_row("/api/grid (br)", elapsed, f"Content-Encoding=br len={clen}")
    else:
        r.failed(name, f"Content-Encoding={enc!r} (expected 'br')")
        r.add_row("/api/grid (br)", elapsed, f"Content-Encoding={enc!r}")
        print(f"  FAIL: brotli not active")
    s.close()


SCRIPT_SRC_RE = re.compile(r'<script[^>]*\bsrc="([^"]+)"', re.IGNORECASE)
ASSET_HREF_RE = re.compile(r'\b(?:src|href)="(/assets/[^"]+\.(?:js|mjs))"', re.IGNORECASE)


def check_12_frontend_html(
    session: requests.Session, web_base: str, r: Results
) -> tuple[str | None, list[str]]:
    name = "12. Frontend HTML loads"
    print(f"\n[{name}] GET {web_base}/")
    t0 = time.time()
    resp = session.get(f"{web_base}/", timeout=PER_REQUEST_TIMEOUT)
    elapsed = time.time() - t0
    ctype = resp.headers.get("Content-Type", "")
    print(f"  HTTP {resp.status_code}  Content-Type={ctype!r}  body={len(resp.text)} chars")
    if resp.status_code != 200:
        r.failed(name, f"HTTP {resp.status_code}")
        r.add_row("frontend /", elapsed, f"HTTP {resp.status_code}")
        return None, []
    if "text/html" not in ctype.lower():
        r.failed(name, f"Content-Type={ctype!r}")
        r.add_row("frontend /", elapsed, f"Content-Type={ctype!r}")
        return None, []
    asset_paths = ASSET_HREF_RE.findall(resp.text)
    main_bundle = None
    for src in SCRIPT_SRC_RE.findall(resp.text):
        if src.startswith("/assets/") and src.endswith((".js", ".mjs")) and 'type="module"' in resp.text:
            main_bundle = src
            break
    # Fall back to any /assets/*.js if no module tag found
    if main_bundle is None and asset_paths:
        for p in asset_paths:
            if p.endswith((".js", ".mjs")):
                main_bundle = p
                break
    print(f"  main bundle: {main_bundle}")
    r.passed(name)
    r.add_row("frontend /", elapsed, f"main={main_bundle}")
    return main_bundle, sorted(set(asset_paths))


def check_13_chunks(
    session: requests.Session, web_base: str, asset_paths: list[str], r: Results
) -> None:
    name = "13. Code-split chunks reachable"
    print(f"\n[{name}] GET each /assets/*.js referenced by index.html")
    if not asset_paths:
        r.failed(name, "no /assets/*.js URLs in HTML")
        r.add_row("frontend chunks", None, "no asset URLs found")
        print("  FAIL: no asset URLs in index.html")
        return
    js_paths = [p for p in asset_paths if p.endswith((".js", ".mjs"))]
    fail_count = 0
    sizes: list[tuple[str, int, float]] = []
    for path in js_paths:
        url = f"{web_base}{path}"
        t0 = time.time()
        resp = session.get(url, timeout=PER_REQUEST_TIMEOUT)
        e = time.time() - t0
        if resp.status_code != 200:
            print(f"  FAIL {path} → HTTP {resp.status_code}")
            fail_count += 1
            continue
        sizes.append((path, len(resp.content), e))
    for path, size, e in sizes:
        kb = size / 1024
        print(f"  {path}  {kb:>8.1f} KB  in {fmt_ms(e)}")
    if fail_count:
        r.failed(name, f"{fail_count} chunk(s) failed")
        r.add_row("frontend chunks", None, f"{fail_count} failed, {len(sizes)} ok")
    elif len(sizes) < 2:
        r.failed(name, f"only {len(sizes)} chunk(s) — expected ≥2 (main + scene)")
        r.add_row("frontend chunks", None, f"only {len(sizes)} chunk(s)")
        print(f"  FAIL: only {len(sizes)} chunk(s) reachable; expected ≥2")
    else:
        r.passed(name)
        r.add_row("frontend chunks", None, f"{len(sizes)} chunks ok")


def print_table(rows: list[dict]) -> None:
    headers = ("Check", "Time", "Notes")
    widths = [
        max(len(headers[0]), max((len(row["check"]) for row in rows), default=0)),
        max(len(headers[1]), 8),
        max(len(headers[2]), max((len(row["notes"]) for row in rows), default=0)),
    ]
    sep = "  ".join("─" * w for w in widths)
    fmt = "  ".join(f"{{:<{w}}}" for w in widths)
    print(fmt.format(*headers))
    print(sep)
    for row in rows:
        t = fmt_ms(row["elapsed"]) if row["elapsed"] is not None else "—"
        print(fmt.format(row["check"], t, row["notes"]))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--api-base",
        default=os.environ.get("API_BASE", DEFAULT_API_BASE),
        help=f"API base URL (default: {DEFAULT_API_BASE})",
    )
    parser.add_argument(
        "--web-base",
        default=os.environ.get("WEB_BASE", DEFAULT_WEB_BASE),
        help=f"Web base URL (default: {DEFAULT_WEB_BASE})",
    )
    args = parser.parse_args()

    api_base = args.api_base.rstrip("/")
    web_base = args.web_base.rstrip("/")

    print(f"AERIA smoke test")
    print(f"  API_BASE = {api_base}")
    print(f"  WEB_BASE = {web_base}")
    print(f"  timeout  = {PER_REQUEST_TIMEOUT}s per request")
    print(f"  host     = {urlparse(api_base).hostname}")

    overall_t0 = time.time()
    r = Results()
    session = make_session()

    health = check_1_health_cold(session, api_base, r)
    cache_warm_before = bool(health and health.get("cache_warm"))

    grid_first_elapsed, _ = check_2_grid_first(session, api_base, r, cache_warm_before)
    check_3_grid_second(session, api_base, r, grid_first_elapsed)
    check_4_health_post_grid(session, api_base, r, health)
    check_5_sensors(session, api_base, r)
    check_6_cell_clean(session, api_base, r)
    check_7_cell_boundary(session, api_base, r)
    check_8_cells_at(session, api_base, r)
    check_9_route_preview(session, api_base, r)
    check_10_cors_preflight(session, api_base, web_base, r)
    check_11_brotli(api_base, r)
    _, asset_paths = check_12_frontend_html(session, web_base, r)
    check_13_chunks(session, web_base, asset_paths, r)

    overall_elapsed = time.time() - overall_t0

    print("\n" + "=" * 64)
    print(f"PASS/FAIL SUMMARY  ({len(r.passes)} passed, {len(r.fails)} failed)")
    print("=" * 64)
    for p in r.passes:
        print(f"  PASS  {p}")
    for n, reason in r.fails:
        print(f"  FAIL  {n} — {reason}")

    print("\n" + "=" * 64)
    print("TIMING SUMMARY")
    print("=" * 64)
    print_table(r.rows)

    print(f"\nWall-clock total: {overall_elapsed:.2f}s ({fmt_ms(overall_elapsed)})")
    return 0 if not r.fails else 1


if __name__ == "__main__":
    sys.exit(main())
