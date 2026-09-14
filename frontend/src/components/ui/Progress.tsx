type ProgressTone = "primary" | "success" | "warning" | "danger";

interface ProgressProps {
  value: number; // 0-100
  label?: string;
  showValue?: boolean;
  tone?: ProgressTone;
}

export default function Progress({ value, label, showValue = false, tone = "primary" }: ProgressProps) {
  const clamped = Math.max(0, Math.min(100, value));
  return (
    <div>
      {(label || showValue) && (
        <div className="progress-label">
          <span>{label}</span>
          {showValue && <span>{Math.round(clamped)}%</span>}
        </div>
      )}
      <div
        className="progress"
        role="progressbar"
        aria-valuenow={Math.round(clamped)}
        aria-valuemin={0}
        aria-valuemax={100}
      >
        <div className={`progress-bar progress-bar--${tone}`} style={{ width: `${clamped}%` }} />
      </div>
    </div>
  );
}
