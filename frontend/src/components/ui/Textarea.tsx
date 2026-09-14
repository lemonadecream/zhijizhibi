import { useId, type TextareaHTMLAttributes } from "react";

interface TextareaProps extends TextareaHTMLAttributes<HTMLTextAreaElement> {
  label?: string;
  hint?: string;
  error?: string;
}

export default function Textarea({ label, hint, error, id, className = "", ...rest }: TextareaProps) {
  const autoId = useId();
  const areaId = id ?? autoId;
  return (
    <div className="field">
      {label && <label className="field-label" htmlFor={areaId}>{label}</label>}
      <textarea id={areaId} className={`textarea ${className}`} aria-invalid={error ? true : undefined} {...rest} />
      {hint && !error && <span className="field-hint">{hint}</span>}
      {error && <span className="field-error">{error}</span>}
    </div>
  );
}
