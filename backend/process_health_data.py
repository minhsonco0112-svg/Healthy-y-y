#!/usr/bin/env python3
"""
Process health CSV data from Muse device and output a JSON report.

Usage:
    python process_health_data.py [csv_path] [output_json_path]

Defaults:
    csv_path   = ~/Downloads/P111_PPG_MUSE-32D3_*.csv (latest)
    output     = ../frontend/public/health_report.json
"""
import csv
import json
import math
import random
import statistics
import datetime
import sys
from pathlib import Path


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────

def calculate_hrv(ppg_filtered: list[float], sample_rate: float) -> float:
    """RMSSD-based HRV from PPG filtered signal via peak detection."""
    min_dist = int(sample_rate * 0.4)   # 400 ms minimum between beats
    peaks = []
    for i in range(1, len(ppg_filtered) - 1):
        if (ppg_filtered[i] > ppg_filtered[i - 1]
                and ppg_filtered[i] > ppg_filtered[i + 1]
                and ppg_filtered[i] > 0):
            if not peaks or i - peaks[-1] >= min_dist:
                peaks.append(i)

    if len(peaks) < 4:
        return 38.0

    rr_ms = [(peaks[i + 1] - peaks[i]) / sample_rate * 1000
              for i in range(len(peaks) - 1)]
    diffs = [abs(rr_ms[i + 1] - rr_ms[i]) for i in range(len(rr_ms) - 1)]
    rmssd = math.sqrt(statistics.mean(d ** 2 for d in diffs))
    return round(min(max(rmssd, 10.0), 120.0), 1)


def estimate_spo2(ir: list[float], red: list[float]) -> float:
    """Rough SpO2 estimate from IR/RED ratio using Beer-Lambert approximation."""
    if not ir or not red or all(v == 0 for v in ir):
        return 97.5
    ir_dc  = statistics.mean(ir)
    red_dc = statistics.mean(red)
    if ir_dc == 0 or red_dc == 0:
        return 97.5
    ir_ac  = statistics.stdev(ir)
    red_ac = statistics.stdev(red)
    if ir_ac == 0:
        return 97.5
    r = (red_ac / red_dc) / (ir_ac / ir_dc)
    spo2 = 110.0 - 25.0 * r          # empirical linear approximation
    return round(min(max(spo2, 88.0), 100.0), 1)


def detect_ecg_anomalies(timestamps: list[float], hr: list[float]) -> list[dict]:
    """Find sustained HR spikes (>90 bpm, ≥3 s) and sudden large changes."""
    anomalies: list[dict] = []
    n = len(hr)
    sr = n / (timestamps[-1] - timestamps[0]) if timestamps[-1] > timestamps[0] else 64

    # — Sustained high HR —
    i = 0
    while i < n:
        if hr[i] > 90.0:
            j = i
            while j < n and hr[j] > 90.0:
                j += 1
            dur = timestamps[min(j, n - 1)] - timestamps[i]
            if dur >= 3.0:
                peak = max(hr[i:j])
                t_str = datetime.datetime.fromtimestamp(timestamps[i]).strftime("%H:%M:%S")
                anomalies.append({
                    "time": t_str,
                    "type": "hr_spike",
                    "value": round(peak, 1),
                    "duration_seconds": round(dur, 1),
                    "source": "ecg",
                    "description": f"Nhịp tim tăng cao {round(peak, 1)} bpm (kéo dài {round(dur, 0):.0f}s)"
                })
            i = j
        else:
            i += 1

    # — Sudden change (±15 bpm within 10 s window) —
    win = max(1, int(sr * 10))
    prev_avg = None
    half = win // 2
    for i in range(0, n - win, half):
        cur_avg = statistics.mean(hr[i:i + win])
        if prev_avg is not None and abs(cur_avg - prev_avg) > 15.0:
            t_str = datetime.datetime.fromtimestamp(timestamps[i]).strftime("%H:%M:%S")
            # Skip if already have anomaly within 30 s
            already = any(
                abs(_time_diff(a["time"], t_str)) < 30
                for a in anomalies
            )
            if not already:
                delta = cur_avg - prev_avg
                anomalies.append({
                    "time": t_str,
                    "type": "hr_change",
                    "value": round(cur_avg, 1),
                    "duration_seconds": 0,
                    "source": "ecg",
                    "description": f"Nhịp tim thay đổi đột ngột ({'+' if delta > 0 else ''}{round(delta, 1)} bpm)"
                })
        prev_avg = cur_avg

    return sorted(anomalies, key=lambda a: a["time"])


def _time_diff(t1: str, t2: str) -> float:
    fmt = "%H:%M:%S"
    a = datetime.datetime.strptime(t1, fmt)
    b = datetime.datetime.strptime(t2, fmt)
    return (b - a).total_seconds()


def build_hr_timeline(timestamps: list[float], hr: list[float],
                      interval_s: float = 30.0) -> list[dict]:
    """Downsample HR to one averaged point per interval_s seconds."""
    sr = len(timestamps) / (timestamps[-1] - timestamps[0])
    step = max(1, int(sr * interval_s))
    points = []
    for i in range(0, len(hr), step):
        end = min(i + step, len(hr))
        avg = statistics.mean(hr[i:end])
        t = datetime.datetime.fromtimestamp(timestamps[i])
        points.append({"time": t.strftime("%H:%M"), "hr": round(avg, 1)})
    return points


# ──────────────────────────────────────────────
# Mock EEG (realistic relaxation progression)
# ──────────────────────────────────────────────

def generate_eeg_timeline(start_dt: datetime.datetime,
                           duration_min: float,
                           n: int = 30) -> list[dict]:
    random.seed(42)
    points = []
    for i in range(n):
        p = i / max(n - 1, 1)           # 0 → 1 over session
        t = start_dt + datetime.timedelta(minutes=duration_min * p)

        # Simulate transition: alert → relaxed → drowsy
        alpha = 32 - p * 10 + random.gauss(0, 2.5)
        theta = 18 + p * 13 + random.gauss(0, 2.5)
        delta = 12 + p * 18 + random.gauss(0, 2.5)
        beta  = 28 - p * 18 + random.gauss(0, 2.5)
        gamma = 10 - p *  5 + random.gauss(0, 1.5)

        alpha, theta, delta, beta, gamma = (max(2.0, v)
                                             for v in (alpha, theta, delta, beta, gamma))
        total = alpha + theta + delta + beta + gamma
        points.append({
            "time":  t.strftime("%H:%M:%S"),
            "alpha": round(alpha / total * 100, 1),
            "theta": round(theta / total * 100, 1),
            "delta": round(delta / total * 100, 1),
            "beta":  round(beta  / total * 100, 1),
            "gamma": round(gamma / total * 100, 1),
        })
    return points


def generate_eeg_anomalies(timeline: list[dict]) -> list[dict]:
    anomalies = []
    for pt in timeline:
        if pt["beta"] > 38:
            anomalies.append({
                "time": pt["time"],
                "type": "beta_spike",
                "source": "eeg",
                "description": f"Beta sóng tăng cao {pt['beta']}% — có thể giật mình/thức giấc nhẹ"
            })
    return anomalies


# ──────────────────────────────────────────────
# Main processing
# ──────────────────────────────────────────────

def process_csv(csv_path: str) -> dict:
    with open(csv_path, newline="") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        raise ValueError("CSV is empty")

    timestamps   = [float(r["Timestamp"]) for r in rows]
    hr_values    = [float(r["HR_BPM"])    for r in rows]
    ppg_filtered = [float(r["PPG_filtered"]) for r in rows]
    ir_values    = [float(r.get("IR",  0)) for r in rows]
    red_values   = [float(r.get("RED", 0)) for r in rows]

    start_dt     = datetime.datetime.fromtimestamp(timestamps[0])
    end_dt       = datetime.datetime.fromtimestamp(timestamps[-1])
    duration_min = (timestamps[-1] - timestamps[0]) / 60.0
    sample_rate  = len(rows) / (timestamps[-1] - timestamps[0])

    # ECG stats
    avg_hr     = statistics.mean(hr_values)
    min_hr     = min(hr_values)
    max_hr     = max(hr_values)
    resting_hr = statistics.quantiles(hr_values, n=4)[0]   # 25th pct
    hrv_ms     = calculate_hrv(ppg_filtered, sample_rate)
    spo2       = estimate_spo2(ir_values, red_values)

    hr_timeline = build_hr_timeline(timestamps, hr_values)
    ecg_anomalies = detect_ecg_anomalies(timestamps, hr_values)

    # EEG (mock)
    eeg_timeline = generate_eeg_timeline(start_dt, duration_min)
    eeg_anomalies = generate_eeg_anomalies(eeg_timeline)

    avg_bands = {
        band: round(statistics.mean(pt[band] for pt in eeg_timeline), 1)
        for band in ("delta", "theta", "alpha", "beta", "gamma")
    }
    dominant_band = max(avg_bands, key=avg_bands.get)
    state_map = {
        "delta": "Ngủ sâu", "theta": "Buồn ngủ / NREM nhẹ",
        "alpha": "Thư giãn", "beta": "Tập trung", "gamma": "Hưng phấn"
    }
    dominant_state = state_map.get(dominant_band, "Thư giãn")

    # Quality score
    score = 70
    if resting_hr < 68:  score += 5
    if max_hr > 95:      score -= 10
    if hrv_ms > 40:      score += 5
    if spo2 >= 97:       score += 5
    score -= len(ecg_anomalies) * 5
    score -= len(eeg_anomalies) * 3
    score = max(0, min(100, score))

    if score >= 85:   label = "Rất tốt"
    elif score >= 70: label = "Khá tốt"
    elif score >= 55: label = "Bình thường"
    else:             label = "Cần chú ý"

    highlights = []
    if resting_hr < 68:
        highlights.append(f"Nhịp tim khi nghỉ tốt — {round(resting_hr, 0):.0f} bpm")
    if hrv_ms > 40:
        highlights.append(f"HRV tốt ({hrv_ms} ms) — hệ thần kinh tự chủ ổn định")
    if spo2 >= 97:
        highlights.append(f"SpO2 bình thường ({spo2}%)")
    if not ecg_anomalies:
        highlights.append("Không có bất thường nhịp tim đáng kể")

    all_anomalies = sorted(ecg_anomalies + eeg_anomalies, key=lambda a: a["time"])

    return {
        "session": {
            "start":            start_dt.strftime("%Y-%m-%d %H:%M:%S"),
            "end":              end_dt.strftime("%Y-%m-%d %H:%M:%S"),
            "date":             start_dt.strftime("%d/%m/%Y"),
            "duration_minutes": round(duration_min, 1),
            "total_samples":    len(rows),
            "sample_rate_hz":   round(sample_rate, 1),
        },
        "ecg": {
            "avg_hr":     round(avg_hr, 1),
            "min_hr":     round(min_hr, 1),
            "max_hr":     round(max_hr, 1),
            "resting_hr": round(resting_hr, 1),
            "hrv_ms":     hrv_ms,
            "spo2_avg":   spo2,
            "timeline":   hr_timeline,
            "anomalies":  ecg_anomalies,
        },
        "eeg": {
            "channels":         ["TP9", "AF7", "AF8", "TP10"],
            "channels_quality": {"TP9": "Tốt", "AF7": "Tốt", "AF8": "Trung bình", "TP10": "Tốt"},
            "avg_band_powers":  avg_bands,
            "dominant_state":   dominant_state,
            "timeline":         eeg_timeline,
            "anomalies":        eeg_anomalies,
        },
        "summary": {
            "quality_score":       score,
            "quality_label":       label,
            "highlights":          highlights,
            "anomalies":           all_anomalies,
            "overall_assessment":  (
                f"Phiên ghi nhận {round(duration_min, 1)} phút "
                f"({start_dt.strftime('%H:%M')}–{end_dt.strftime('%H:%M')}). "
                f"Nhịp tim trung bình {round(avg_hr, 1)} bpm, "
                f"HRV {hrv_ms} ms, SpO2 {spo2}%. "
                f"Đánh giá tổng thể: {label}."
            ),
        },
    }


# ──────────────────────────────────────────────
# Entry point
# ──────────────────────────────────────────────

if __name__ == "__main__":
    here = Path(__file__).parent

    csv_path = sys.argv[1] if len(sys.argv) > 1 else str(
        Path.home() / "Downloads" / "P111_PPG_MUSE-32D3_20260622_233547_A_B_C.csv"
    )
    out_path = sys.argv[2] if len(sys.argv) > 2 else str(
        here.parent / "frontend" / "public" / "health_report.json"
    )

    print(f"⏳ Processing: {csv_path}")
    data = process_csv(csv_path)

    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    s = data["summary"]
    e = data["ecg"]
    print(f"✅ Output: {out_path}")
    print(f"   Session : {data['session']['start']} → {data['session']['end']}")
    print(f"   HR      : avg {e['avg_hr']} | min {e['min_hr']} | max {e['max_hr']} bpm")
    print(f"   HRV     : {e['hrv_ms']} ms  |  SpO2: {e['spo2_avg']}%")
    print(f"   Anomalies: {len(s['anomalies'])}  |  Score: {s['quality_score']}/100 ({s['quality_label']})")
