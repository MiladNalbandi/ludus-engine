'use client';

import type { BehaviourEditorProps } from '@/components/behaviour/registry';

/**
 * The small set of field controls the panels are built from.
 *
 * Deliberately plain. `v1.2.0` is the schema-driven editor, which will generate these from the
 * JSON Schema rather than from a hand-written list per behaviour; until then a handful of shared
 * controls keeps the per-behaviour panels to a few lines each, so replacing them later is a small
 * change rather than unpicking three thousand lines of bespoke forms.
 */
export function NumberField({
  label,
  value,
  onChange,
  step = 1,
  min,
}: {
  label: string;
  value: number | undefined;
  onChange: (value: number) => void;
  step?: number;
  min?: number;
}) {
  return (
    <label>
      {label}
      <input
        type="number"
        step={step}
        min={min}
        value={value ?? ''}
        onChange={(event) => onChange(Number(event.target.value))}
      />
    </label>
  );
}

export function ChoiceField<T extends string>({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: T | undefined;
  options: readonly T[];
  onChange: (value: T) => void;
}) {
  return (
    <label>
      {label}
      <select
        value={value ?? options[0]}
        onChange={(event) => onChange(event.target.value as T)}
        style={{
          width: '100%',
          padding: '0.6rem 0.75rem',
          borderRadius: 'var(--radius)',
          border: '1px solid var(--slate)',
          background: 'var(--navy-raised)',
          color: 'var(--text)',
          font: 'inherit',
        }}
      >
        {options.map((option) => (
          <option key={option} value={option}>
            {option}
          </option>
        ))}
      </select>
    </label>
  );
}

export function ToggleField({
  label,
  value,
  onChange,
}: {
  label: string;
  value: boolean | undefined;
  onChange: (value: boolean) => void;
}) {
  return (
    <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', textTransform: 'none' }}>
      <input
        type="checkbox"
        checked={value ?? false}
        onChange={(event) => onChange(event.target.checked)}
        style={{ width: 'auto' }}
      />
      {label}
    </label>
  );
}

/**
 * The fallback, for a movement type with no registered panel.
 *
 * It edits the config as JSON, which is not pleasant and is honest: the author can still change
 * anything, and an invalid edit is refused locally rather than saved and rejected by the engine
 * later with a schema error about a field this form never showed.
 */
export function RawConfigEditor({ config, onChange }: BehaviourEditorProps) {
  return (
    <label style={{ textTransform: 'none' }}>
      This movement has no form yet — editing its configuration directly.
      <textarea
        rows={8}
        defaultValue={JSON.stringify(config, null, 2)}
        onBlur={(event) => {
          try {
            const parsed = JSON.parse(event.target.value || '{}') as Record<string, unknown>;
            onChange(parsed);
            event.target.setCustomValidity('');
          } catch {
            event.target.setCustomValidity('that is not valid JSON');
            event.target.reportValidity();
          }
        }}
        style={{
          width: '100%',
          marginTop: '0.4rem',
          padding: '0.6rem',
          borderRadius: 'var(--radius)',
          border: '1px solid var(--slate)',
          background: 'var(--navy)',
          color: 'var(--text)',
          fontFamily: 'Menlo, Monaco, monospace',
          fontSize: '13px',
        }}
      />
    </label>
  );
}
