'use client';

import { Anomaly } from '@/lib/health-types';

const TYPE_META: Record<string, { label: string; color: string; icon: string }> = {
  hr_spike: { label: 'HR tăng cao', color: 'var(--fgSerious)', icon: '↑' },
  hr_change: { label: 'HR thay đổi đột ngột', color: 'var(--fgModerate)', icon: '⚡' },
  beta_spike: { label: 'EEG Beta tăng', color: 'var(--fgModerate)', icon: '≈' },
};

function AnomalyItem({ anomaly }: { anomaly: Anomaly }) {
  const meta = TYPE_META[anomaly.type] ?? { label: anomaly.type, color: 'var(--fg3)', icon: '!' };
  return (
    <div
      style={{
        display: 'flex',
        gap: 10,
        padding: '8px 0',
        borderBottom: '1px solid var(--separator1)',
        alignItems: 'flex-start',
      }}
    >
      <span
        style={{
          width: 22,
          height: 22,
          borderRadius: '50%',
          background: meta.color + '22',
          color: meta.color,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          fontSize: 11,
          fontWeight: 700,
          flexShrink: 0,
          marginTop: 1,
        }}
      >
        {meta.icon}
      </span>
      <div style={{ flex: 1 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span style={{ fontSize: 11, color: meta.color, fontWeight: 600 }}>{meta.label}</span>
          <span
            style={{ fontSize: 10, color: 'var(--fg4)', fontFamily: 'var(--font-commit-mono)' }}
          >
            {anomaly.time}
          </span>
        </div>
        <p style={{ margin: 0, fontSize: 11, color: 'var(--fg2)', lineHeight: 1.4, marginTop: 2 }}>
          {anomaly.description}
        </p>
        {anomaly.duration_seconds && anomaly.duration_seconds > 0 && (
          <span style={{ fontSize: 10, color: 'var(--fg4)' }}>
            Nguồn: {anomaly.source?.toUpperCase()}
          </span>
        )}
      </div>
    </div>
  );
}

export function SummaryPanel({
  summary,
}: {
  summary: {
    quality_score: number;
    quality_label: string;
    anomalies: Anomaly[];
    overall_assessment: string;
  };
}) {
  const { quality_score, quality_label, anomalies, overall_assessment } = summary;

  const scoreColor =
    quality_score >= 85
      ? 'var(--fgSuccess)'
      : quality_score >= 70
        ? 'var(--fgAccent)'
        : quality_score >= 55
          ? 'var(--fgModerate)'
          : 'var(--fgSerious)';

  const ringPct = quality_score;

  return (
    <div className="panel">
      <div className="panel-header">
        <span className="panel-title">Tóm tắt & Bất thường</span>
      </div>

      {/* Score ring */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 20, marginBottom: 16 }}>
        <svg width="72" height="72" viewBox="0 0 72 72">
          <circle cx="36" cy="36" r="28" fill="none" stroke="var(--bg3)" strokeWidth="7" />
          <circle
            cx="36"
            cy="36"
            r="28"
            fill="none"
            stroke={scoreColor}
            strokeWidth="7"
            strokeDasharray={`${(ringPct / 100) * 175.9} 175.9`}
            strokeLinecap="round"
            transform="rotate(-90 36 36)"
          />
          <text
            x="36"
            y="38"
            textAnchor="middle"
            fontSize="16"
            fontWeight="700"
            fill={scoreColor}
            fontFamily="var(--font-commit-mono)"
          >
            {quality_score}
          </text>
          <text x="36" y="50" textAnchor="middle" fontSize="7" fill="var(--fg4)">
            / 100
          </text>
        </svg>
        <div>
          <div style={{ fontSize: 18, fontWeight: 700, color: scoreColor }}>{quality_label}</div>
          <div
            style={{
              fontSize: 11,
              color: 'var(--fg3)',
              marginTop: 2,
              maxWidth: 180,
              lineHeight: 1.4,
            }}
          >
            {overall_assessment}
          </div>
        </div>
      </div>

      {/* Anomalies */}
      <div
        style={{
          fontSize: 10,
          color: 'var(--fg4)',
          textTransform: 'uppercase',
          letterSpacing: '0.08em',
          marginBottom: 6,
        }}
      >
        Sự kiện bất thường ({anomalies.length})
      </div>

      {anomalies.length === 0 ? (
        <div
          style={{
            padding: '16px 12px',
            background: 'var(--bgSuccess)',
            borderRadius: 6,
            fontSize: 12,
            color: 'var(--fgSuccess)',
            display: 'flex',
            gap: 8,
            alignItems: 'center',
          }}
        >
          <span>✓</span>
          <span>Không phát hiện bất thường trong phiên ghi nhận.</span>
        </div>
      ) : (
        <div style={{ overflowY: 'auto', flex: 1 }}>
          {anomalies.map((a, i) => (
            <AnomalyItem key={i} anomaly={a} />
          ))}
        </div>
      )}
    </div>
  );
}
