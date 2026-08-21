import { readFileSync } from 'fs';
import { join } from 'path';
import { ECGPanel } from '@/components/dashboard/ECGPanel';
import { EEGPanel } from '@/components/dashboard/EEGPanel';
import { StatsPanel } from '@/components/dashboard/StatsPanel';
import { SummaryPanel } from '@/components/dashboard/SummaryPanel';
import { HealthReport } from '@/lib/health-types';
import './dashboard.css';

function loadReport(): HealthReport | null {
  try {
    const p = join(process.cwd(), 'public', 'health_report.json');
    return JSON.parse(readFileSync(p, 'utf-8')) as HealthReport;
  } catch {
    return null;
  }
}

export const dynamic = 'force-dynamic'; // always re-read the JSON on request

export default function DashboardPage() {
  const report = loadReport();

  if (!report) {
    return (
      <div className="dash-error">
        <p>Không tìm thấy dữ liệu.</p>
        <p>
          Chạy: <code>python backend/process_health_data.py</code>
        </p>
      </div>
    );
  }

  const { session, ecg, eeg, summary } = report;

  return (
    <div className="dash-root">
      {/* ── Top bar ── */}
      <header className="dash-header">
        <div className="dash-header-left">
          <span className="dash-title">Health Dashboard</span>
          <span className="dash-subtitle">
            {session.date} &nbsp;·&nbsp;
            {session.start.slice(11, 16)}–{session.end.slice(11, 16)} &nbsp;·&nbsp;
            {session.duration_minutes} phút
          </span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span
            className="dash-score-chip"
            style={{
              background:
                summary.quality_score >= 85
                  ? 'var(--bgSuccess)'
                  : summary.quality_score >= 70
                    ? 'var(--bgAccentPrimary)'
                    : summary.quality_score >= 55
                      ? 'var(--bgModerate)'
                      : 'var(--bgSerious)',
              color:
                summary.quality_score >= 85
                  ? 'var(--fgSuccess)'
                  : summary.quality_score >= 70
                    ? 'var(--fgAccent)'
                    : summary.quality_score >= 55
                      ? 'var(--fgModerate)'
                      : 'var(--fgSerious)',
            }}
          >
            {summary.quality_label} — {summary.quality_score}/100
          </span>
        </div>
      </header>

      {/* ── 2 × 2 grid ── */}
      <main className="dash-grid">
        <EEGPanel data={eeg} />
        <StatsPanel session={session} ecg={ecg} eeg={eeg} summary={summary} />
        <ECGPanel data={ecg} />
        <SummaryPanel summary={summary} />
      </main>
    </div>
  );
}
