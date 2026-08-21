'use client';

import { EEGData } from '@/lib/health-types';

const BAND_META: {
  key: keyof EEGData['avg_band_powers'];
  label: string;
  symbol: string;
  color: string;
}[] = [
  { key: 'delta', label: 'Delta', symbol: 'δ', color: '#002cf2' },
  { key: 'theta', label: 'Theta', symbol: 'θ', color: '#7c3aed' },
  { key: 'alpha', label: 'Alpha', symbol: 'α', color: '#059669' },
  { key: 'beta', label: 'Beta', symbol: 'β', color: '#d97706' },
  { key: 'gamma', label: 'Gamma', symbol: 'γ', color: '#db1b06' },
];

const QUALITY_COLOR: Record<string, string> = {
  Tốt: '#006430',
  'Trung bình': '#a65006',
  Kém: '#db1b06',
};

function EEGTimelineChart({ timeline }: { timeline: EEGData['timeline'] }) {
  if (!timeline.length) return null;

  const W = 560;
  const H = 90;
  const PAD = { t: 4, r: 4, b: 20, l: 28 };
  const cW = W - PAD.l - PAD.r;
  const cH = H - PAD.t - PAD.b;

  const n = timeline.length;

  const xOf = (i: number) => PAD.l + (i / (n - 1)) * cW;
  const yOf = (v: number) => PAD.t + (1 - v / 60) * cH; // 0–60% range

  const path = (key: keyof (typeof timeline)[0]) =>
    timeline
      .map(
        (pt, i) => `${i === 0 ? 'M' : 'L'}${xOf(i).toFixed(1)},${yOf(Number(pt[key])).toFixed(1)}`
      )
      .join(' ');

  const tickTimes = [0, Math.floor(n / 2), n - 1];

  return (
    <svg viewBox={`0 0 ${W} ${H}`} style={{ width: '100%', height: '100%' }}>
      {/* Y grid */}
      {[0, 20, 40, 60].map((v) => (
        <g key={v}>
          <line
            x1={PAD.l}
            y1={yOf(v)}
            x2={W - PAD.r}
            y2={yOf(v)}
            stroke="var(--separator1)"
            strokeWidth="0.5"
          />
          <text x={PAD.l - 4} y={yOf(v) + 4} fontSize="7" textAnchor="end" fill="var(--fg4)">
            {v}%
          </text>
        </g>
      ))}

      {/* X tick labels */}
      {tickTimes.map((i) => (
        <text
          key={i}
          x={xOf(i)}
          y={H - 4}
          fontSize="7"
          textAnchor={i === 0 ? 'start' : i === n - 1 ? 'end' : 'middle'}
          fill="var(--fg4)"
        >
          {timeline[i].time.slice(0, 5)}
        </text>
      ))}

      {/* Band lines */}
      {BAND_META.map(({ key, color }) => (
        <path
          key={key}
          d={path(key)}
          fill="none"
          stroke={color}
          strokeWidth="1.5"
          strokeLinejoin="round"
        />
      ))}
    </svg>
  );
}

export function EEGPanel({ data }: { data: EEGData }) {
  const { avg_band_powers, dominant_state, channels_quality, timeline } = data;
  const maxVal = Math.max(...Object.values(avg_band_powers));

  return (
    <div className="panel">
      <div className="panel-header">
        <span className="panel-title">EEG — Sóng não</span>
        <span className="badge badge-neutral">{dominant_state}</span>
      </div>

      {/* Band power bars */}
      <div style={{ marginBottom: 16 }}>
        {BAND_META.map(({ key, label, symbol, color }) => {
          const val = avg_band_powers[key];
          const pct = Math.round((val / maxVal) * 100);
          return (
            <div
              key={key}
              style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}
            >
              <span
                style={{
                  width: 56,
                  fontSize: 11,
                  color: 'var(--fg3)',
                  fontFamily: 'var(--font-commit-mono)',
                }}
              >
                {symbol} {label}
              </span>
              <div
                style={{
                  flex: 1,
                  background: 'var(--bg3)',
                  borderRadius: 2,
                  height: 8,
                  overflow: 'hidden',
                }}
              >
                <div
                  style={{ width: `${pct}%`, height: '100%', background: color, borderRadius: 2 }}
                />
              </div>
              <span
                style={{
                  width: 36,
                  fontSize: 11,
                  textAlign: 'right',
                  color: 'var(--fg2)',
                  fontFamily: 'var(--font-commit-mono)',
                }}
              >
                {val.toFixed(1)}%
              </span>
            </div>
          );
        })}
      </div>

      {/* Channel quality */}
      <div style={{ display: 'flex', gap: 12, marginBottom: 16, flexWrap: 'wrap' }}>
        {data.channels.map((ch) => {
          const q = channels_quality[ch] ?? 'Tốt';
          const c = QUALITY_COLOR[q] ?? 'var(--fg3)';
          return (
            <div key={ch} style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
              <span
                style={{
                  width: 7,
                  height: 7,
                  borderRadius: '50%',
                  background: c,
                  display: 'inline-block',
                }}
              />
              <span
                style={{ fontSize: 11, color: 'var(--fg2)', fontFamily: 'var(--font-commit-mono)' }}
              >
                {ch}: {q}
              </span>
            </div>
          );
        })}
      </div>

      {/* Timeline chart */}
      <div style={{ flex: 1, minHeight: 90 }}>
        <div style={{ fontSize: 10, color: 'var(--fg4)', marginBottom: 4 }}>
          Band power over time (%)
        </div>
        <div style={{ height: 90 }}>
          <EEGTimelineChart timeline={timeline} />
        </div>
        <div style={{ display: 'flex', gap: 12, marginTop: 6, flexWrap: 'wrap' }}>
          {BAND_META.map(({ key, label, color }) => (
            <div key={key} style={{ display: 'flex', alignItems: 'center', gap: 3 }}>
              <span style={{ width: 16, height: 2, background: color, display: 'inline-block' }} />
              <span style={{ fontSize: 9, color: 'var(--fg4)' }}>{label}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
