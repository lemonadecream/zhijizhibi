import { useId, type InputHTMLAttributes } from "react";

interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  hint?: string;
  error?: string;
}

export default function Input({ label, hint, error, id, className = "", ...rest }: InputProps) {
  // useId 保证重渲染间稳定（原 Math.random() 实现会让 label 关联在每次渲染后漂移）
  const autoId = useId();
  const inputId = id ?? autoId;
  return (
    <div className="field">
      {label && <label className="field-label" htmlFor={inputId}>{label}</label>}
      <input id={inputId} className={`input ${className}`} aria-invalid={error ? true : undefined} {...rest} />
      {hint && !error && <span className="field-hint">{hint}</span>}
      {error && <span className="field-error">{error}</span>}
    </div>
  );
}
