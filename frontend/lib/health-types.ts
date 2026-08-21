export interface HealthSession {
  start: string;
  end: string;
  date: string;
  duration_minutes: number;
  total_samples: number;
  sample_rate_hz: number;
}

export interface HRPoint {
  time: string;
  hr: number;
}

export interface Anomaly {
  time: string;
  type: string;
  value?: number;
  duration_seconds?: number;
  source: 'ecg' | 'eeg';
  description: string;
}

export interface ECGData {
  avg_hr: number;
  min_hr: number;
  max_hr: number;
  resting_hr: number;
  hrv_ms: number;
  spo2_avg: number;
  timeline: HRPoint[];
  anomalies: Anomaly[];
}

export interface EEGPoint {
  time: string;
  alpha: number;
  theta: number;
  delta: number;
  beta: number;
  gamma: number;
}

export interface BandPowers {
  delta: number;
  theta: number;
  alpha: number;
  beta: number;
  gamma: number;
}

export interface EEGData {
  channels: string[];
  channels_quality: Record<string, string>;
  avg_band_powers: BandPowers;
  dominant_state: string;
  timeline: EEGPoint[];
  anomalies: Anomaly[];
}

export interface HealthReport {
  session: HealthSession;
  ecg: ECGData;
  eeg: EEGData;
  summary: {
    quality_score: number;
    quality_label: string;
    highlights: string[];
    anomalies: Anomaly[];
    overall_assessment: string;
  };
}
