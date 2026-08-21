'use client';

import { ECGData, EEGData, HealthSession } from '@/lib/health-types';

function Row({ label, value, highlight }: { label: string; value: string; highlight?: boolean }) {
  return (
    <div
      style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'baseline',
        padding: '7px 0',
        borderBottom: '1px solid var(--separator1)',
      }}
    >
      <span style={{ fontSize: 12, color: 'var(--fg3)' }}>{label}</span>
      <span
        style={{
          fontSize: 13,
          fontFamily: 'var(--font-commit-mono)',
          color: highlight ? 'var(--fgAccent)' : 'var(--fg1)',
          fontWeight: highlight ? 700 : 400,
        }}
      >
        {value}
      </span>
    </div>
  );
}

function formatDuration(minutes: number): string {
  const h = Math.floor(minutes / 60);
  const m = Math.round(minutes % 60);
  return h > 0 ? `${h}g ${m}p` : `${m} phút`;
}

export function StatsPanel({
  session,
  ecg,
  eeg,
  summary,
}: {
  session: HealthSession;
  ecg: ECGData;
  eeg: EEGData;
  summary: { quality_score: number; quality_label: string; highlights: string[] };
}) {
  const scoreColor =
    summary.quality_score >= 85
      ? 'var(--fgSuccess)'
      : summary.quality_score >= 70
        ? 'var(--fgAccent)'
        : summary.quality_score >= 55
          ? 'var(--fgModerate)'
          : 'var(--fgSerious)';

  return (
    <div className="panel">
      <div className="panel-header">
        <span className="panel-title">Chỉ số tổng hợp</span>
        <span
          style={{
            fontSize: 20,
            fontWeight: 700,
            fontFamily: 'var(--font-commit-mono)',
            color: scoreColor,
          }}
        >
          {summary.quality_score}
          <span style={{ fontSize: 11, fontWeight: 400, color: 'var(--fg3)' }}>/100</span>
        </span>
      </div>

      <div style={{ marginBottom: 12 }}>
        <Row label="Ngày ghi" value={session.date} />
        <Row
          label="Thời gian"
          value={`${session.start.slice(11, 16)} – ${session.end.slice(11, 16)}`}
        />
        <Row label="Tổng thời lượng" value={formatDuration(session.duration_minutes)} />
        <Row label="Đánh giá tổng thể" value={summary.quality_label} highlight />
      </div>

      <div style={{ marginBottom: 12 }}>
        <div
          style={{
            fontSize: 10,
            color: 'var(--fg4)',
            marginBottom: 4,
            textTransform: 'uppercase',
            letterSpacing: '0.08em',
          }}
        >
          ECG / Tim mạch
        </div>
        <Row label="Nhịp tim TB" value={`${ecg.avg_hr} bpm`} />
        <Row label="Nhịp nghỉ" value={`${ecg.resting_hr} bpm`} />
        <Row label="HRV (RMSSD)" value={`${ecg.hrv_ms} ms`} />
        <Row label="SpO2" value={`${ecg.spo2_avg}%`} />
      </div>

      <div style={{ marginBottom: 12 }}>
        <div
          style={{
            fontSize: 10,
            color: 'var(--fg4)',
            marginBottom: 4,
            textTransform: 'uppercase',
            letterSpacing: '0.08em',
          }}
        >
          EEG — Sóng não
        </div>
        <Row label="Trạng thái chủ đạo" value={eeg.dominant_state} highlight />
        <Row label="Delta (δ)" value={`${eeg.avg_band_powers.delta}%`} />
        <Row label="Theta (θ)" value={`${eeg.avg_band_powers.theta}%`} />
        <Row label="Alpha (α)" value={`${eeg.avg_band_powers.alpha}%`} />
        <Row label="Beta (β)" value={`${eeg.avg_band_powers.beta}%`} />
      </div>

      {summary.highlights.length > 0 && (
        <div>
          <div
            style={{
              fontSize: 10,
              color: 'var(--fg4)',
              marginBottom: 6,
              textTransform: 'uppercase',
              letterSpacing: '0.08em',
            }}
          >
            Điểm nổi bật
          </div>
          {summary.highlights.map((h, i) => (
            <div
              key={i}
              style={{ display: 'flex', gap: 6, marginBottom: 5, alignItems: 'flex-start' }}
            >
              <span style={{ color: 'var(--fgSuccess)', fontSize: 12, marginTop: 1 }}>✓</span>
              <span style={{ fontSize: 12, color: 'var(--fg2)', lineHeight: 1.4 }}>{h}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
