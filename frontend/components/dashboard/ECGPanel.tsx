'use client';

import { ECGData } from '@/lib/health-types';

function HRChart({ timeline, maxHR }: { timeline: ECGData['timeline']; maxHR: number }) {
  if (!timeline.length) return null;

  const W = 560;
  const H = 120;
  const PAD = { t: 8, r: 8, b: 24, l: 36 };
  const cW = W - PAD.l - PAD.r;
  const cH = H - PAD.t - PAD.b;

  const values = timeline.map((p) => p.hr);
  const minV = Math.max(0, Math.min(...values) - 5);
  const maxV = Math.max(...values, 100) + 5;
  const range = maxV - minV;

  const xOf = (i: number) => PAD.l + (i / Math.max(timeline.length - 1, 1)) * cW;
  const yOf = (v: number) => PAD.t + (1 - (v - minV) / range) * cH;

  const points = timeline.map((p, i) => `${xOf(i).toFixed(1)},${yOf(p.hr).toFixed(1)}`).join(' ');
  const y90 = yOf(90);

  const yTicks = [Math.ceil(minV / 10) * 10, 70, 90, Math.floor(maxV / 10) * 10].filter(
    (v, i, a) => v >= minV && v <= maxV && a.indexOf(v) === i
  );

  const n = timeline.length;
  const xTicks = [0, Math.floor(n / 3), Math.floor((2 * n) / 3), n - 1].filter(
    (v, i, a) => a.indexOf(v) === i
  );

  return (
    <svg viewBox={`0 0 ${W} ${H}`} style={{ width: '100%', height: '100%' }}>
      {/* Y grid + labels */}
      {yTicks.map((v) => (
        <g key={v}>
          <line
            x1={PAD.l}
            y1={yOf(v)}
            x2={W - PAD.r}
            y2={yOf(v)}
            stroke={v === 90 ? '#db1b0644' : 'var(--separator1)'}
            strokeWidth={v === 90 ? 1 : 0.5}
            strokeDasharray={v === 90 ? '3 3' : undefined}
          />
          <text
            x={PAD.l - 4}
            y={yOf(v) + 4}
            fontSize="8"
            textAnchor="end"
            fill={v === 90 ? '#db1b06' : 'var(--fg4)'}
          >
            {v}
          </text>
        </g>
      ))}

      {/* 90 bpm label */}
      <text x={W - PAD.r} y={y90 - 3} fontSize="8" textAnchor="end" fill="#db1b06">
        90 bpm
      </text>

      {/* X labels */}
      {xTicks.map((i) => (
        <text
          key={i}
          x={xOf(i)}
          y={H - 4}
          fontSize="8"
          textAnchor={i === 0 ? 'start' : i === n - 1 ? 'end' : 'middle'}
          fill="var(--fg4)"
        >
          {timeline[i].time}
        </text>
      ))}

      {/* Area fill */}
      <path
        d={`M${xOf(0)},${yOf(timeline[0].hr)} ${timeline.map((p, i) => `L${xOf(i)},${yOf(p.hr)}`).join(' ')} L${xOf(n - 1)},${H - PAD.b} L${xOf(0)},${H - PAD.b} Z`}
        fill="#002cf215"
      />

      {/* HR line */}
      <polyline
        points={points}
        fill="none"
        stroke="#002cf2"
        strokeWidth="2"
        strokeLinejoin="round"
        strokeLinecap="round"
      />

      {/* Dots for anomalies: HR > 90 */}
      {timeline.map((p, i) =>
        p.hr > 90 ? <circle key={i} cx={xOf(i)} cy={yOf(p.hr)} r="3" fill="#db1b06" /> : null
      )}

      {/* Y axis */}
      <line
        x1={PAD.l}
        y1={PAD.t}
        x2={PAD.l}
        y2={H - PAD.b}
        stroke="var(--separator2)"
        strokeWidth="0.5"
      />
    </svg>
  );
}

function StatBox({
  label,
  value,
  unit,
  color,
}: {
  label: string;
  value: string | number;
  unit?: string;
  color?: string;
}) {
  return (
    <div className="stat-box">
      <span className="stat-label">{label}</span>
      <span className="stat-value" style={{ color: color ?? 'var(--fg0)' }}>
        {value}
        {unit && <span className="stat-unit"> {unit}</span>}
      </span>
    </div>
  );
}

export function ECGPanel({ data }: { data: ECGData }) {
  const { avg_hr, min_hr, max_hr, resting_hr, hrv_ms, spo2_avg, timeline, anomalies } = data;

  return (
    <div className="panel">
      <div className="panel-header">
        <span className="panel-title">ECG / PPG — Nhịp tim</span>
        {anomalies.length > 0 && (
          <span className="badge badge-warn">{anomalies.length} bất thường</span>
        )}
      </div>

      {/* Key stats row */}
      <div className="stat-row">
        <StatBox label="Trung bình" value={avg_hr} unit="bpm" />
        <StatBox label="Thấp nhất" value={min_hr} unit="bpm" color="var(--fgSuccess)" />
        <StatBox
          label="Cao nhất"
          value={max_hr}
          unit="bpm"
          color={max_hr > 95 ? 'var(--fgSerious)' : 'var(--fg0)'}
        />
        <StatBox label="Nghỉ ngơi" value={resting_hr} unit="bpm" />
        <StatBox
          label="HRV"
          value={hrv_ms}
          unit="ms"
          color={hrv_ms > 40 ? 'var(--fgSuccess)' : 'var(--fg0)'}
        />
        <StatBox
          label="SpO2"
          value={spo2_avg}
          unit="%"
          color={spo2_avg < 95 ? 'var(--fgSerious)' : 'var(--fgSuccess)'}
        />
      </div>

      {/* HR chart */}
      <div style={{ flex: 1, minHeight: 120, marginTop: 8 }}>
        <div style={{ fontSize: 10, color: 'var(--fg4)', marginBottom: 2 }}>Heart Rate (bpm)</div>
        <div style={{ height: 120 }}>
          <HRChart timeline={timeline} maxHR={max_hr} />
        </div>
      </div>
    </div>
  );
}
