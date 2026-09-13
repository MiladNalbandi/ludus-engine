'use client';

import {
  ChoiceField,
  NumberField,
  RawConfigEditor,
  ToggleField,
} from '@/components/behaviour/fields';
import {
  behaviorEditorRegistry,
  type BehaviourEditorProps,
} from '@/components/behaviour/registry';

/**
 * One panel per movement type, registered rather than switched on.
 *
 * Each reads a handful of keys and writes them straight back, leaving anything it does not know
 * about untouched — which is why every `onChange` spreads the existing config. A panel that
 * replaced the object wholesale would silently drop fields it has no control for, and the author
 * would find out when the wave played differently.
 */
function patch(props: BehaviourEditorProps, changes: Record<string, unknown>): void {
  props.onChange({ ...props.config, ...changes });
}

function n(props: BehaviourEditorProps, key: string): number | undefined {
  const value = props.config[key];
  return typeof value === 'number' ? value : undefined;
}

function s<T extends string>(props: BehaviourEditorProps, key: string): T | undefined {
  const value = props.config[key];
  return typeof value === 'string' ? (value as T) : undefined;
}

function b(props: BehaviourEditorProps, key: string): boolean | undefined {
  const value = props.config[key];
  return typeof value === 'boolean' ? value : undefined;
}

function PatrolEditor(props: BehaviourEditorProps) {
  return (
    <>
      <NumberField
        label="Speed"
        value={n(props, 'speed')}
        min={0.1}
        step={5}
        onChange={(speed) => patch(props, { speed })}
      />
      <ChoiceField
        label="Direction"
        value={s<'horizontal' | 'vertical' | 'both'>(props, 'direction')}
        options={['horizontal', 'vertical', 'both'] as const}
        onChange={(direction) => patch(props, { direction })}
      />
    </>
  );
}

function OrbitEditor(props: BehaviourEditorProps) {
  return (
    <>
      <ChoiceField
        label="Centre"
        value={s<'player' | 'fixed'>(props, 'center')}
        options={['player', 'fixed'] as const}
        onChange={(center) => patch(props, { center })}
      />
      <NumberField
        label="Radius"
        value={n(props, 'radius')}
        min={0.1}
        step={5}
        onChange={(radius) => patch(props, { radius })}
      />
      <NumberField
        label="Angular speed"
        value={n(props, 'angular_speed')}
        step={0.1}
        onChange={(angular_speed) => patch(props, { angular_speed })}
      />
      <ToggleField
        label="Clockwise"
        value={b(props, 'clockwise')}
        onChange={(clockwise) => patch(props, { clockwise })}
      />
    </>
  );
}

function ZigzagEditor(props: BehaviourEditorProps) {
  return (
    <>
      <NumberField
        label="Speed"
        value={n(props, 'speed')}
        min={0.1}
        step={5}
        onChange={(speed) => patch(props, { speed })}
      />
      <NumberField
        label="Amplitude"
        value={n(props, 'amplitude')}
        step={2}
        onChange={(amplitude) => patch(props, { amplitude })}
      />
      <NumberField
        label="Frequency"
        value={n(props, 'frequency')}
        step={0.1}
        onChange={(frequency) => patch(props, { frequency })}
      />
      <ChoiceField
        label="Direction"
        value={s<'up' | 'down' | 'left' | 'right'>(props, 'direction')}
        options={['up', 'down', 'left', 'right'] as const}
        onChange={(direction) => patch(props, { direction })}
      />
    </>
  );
}

function DashEditor(props: BehaviourEditorProps) {
  return (
    <>
      <ChoiceField
        label="Direction"
        value={s<'towards_player' | 'away_from_player' | 'up' | 'down' | 'left' | 'right'>(
          props,
          'direction',
        )}
        options={
          ['towards_player', 'away_from_player', 'up', 'down', 'left', 'right'] as const
        }
        onChange={(direction) => patch(props, { direction })}
      />
      <NumberField
        label="Speed"
        value={n(props, 'speed')}
        min={0.1}
        step={10}
        onChange={(speed) => patch(props, { speed })}
      />
      <NumberField
        label="Distance"
        value={n(props, 'distance')}
        min={0.1}
        step={10}
        onChange={(distance) => patch(props, { distance })}
      />
    </>
  );
}

function WaitEditor(props: BehaviourEditorProps) {
  const wiggling = b(props, 'wiggle') ?? false;
  return (
    <>
      <ToggleField
        label="Wiggle while waiting"
        value={wiggling}
        onChange={(wiggle) => patch(props, { wiggle })}
      />
      {wiggling ? (
        <>
          <NumberField
            label="Wiggle amplitude"
            value={n(props, 'wiggle_amplitude')}
            min={0}
            step={1}
            onChange={(wiggle_amplitude) => patch(props, { wiggle_amplitude })}
          />
          <NumberField
            label="Wiggle frequency"
            value={n(props, 'wiggle_frequency')}
            min={0}
            step={0.5}
            onChange={(wiggle_frequency) => patch(props, { wiggle_frequency })}
          />
        </>
      ) : null}
    </>
  );
}

function SpiralEditor(props: BehaviourEditorProps) {
  return (
    <>
      <NumberField
        label="Angular speed"
        value={n(props, 'angular_speed')}
        step={0.1}
        onChange={(angular_speed) => patch(props, { angular_speed })}
      />
      <NumberField
        label="Radial speed"
        value={n(props, 'radial_speed')}
        step={1}
        onChange={(radial_speed) => patch(props, { radial_speed })}
      />
      <NumberField
        label="Start radius"
        value={n(props, 'start_radius')}
        min={0}
        step={1}
        onChange={(start_radius) => patch(props, { start_radius })}
      />
    </>
  );
}

function CrossEditor(props: BehaviourEditorProps) {
  return (
    <NumberField
      label="Speed"
      value={n(props, 'speed')}
      min={0.1}
      step={5}
      onChange={(speed) => patch(props, { speed })}
    />
  );
}

/** `hide` and `despawn` genuinely have nothing to configure, and saying so beats an empty panel. */
function NoOptionsEditor() {
  return <p className="muted">This movement has no options.</p>;
}

/**
 * Registers every panel. `teleport` and `jump` fall through to the raw editor on purpose: both
 * configure spawn positions, which needs a position picker that does not exist yet, and a
 * half-built picker that silently wrote the wrong shape would be worse than a JSON field.
 */
export function registerBuiltInBehaviourEditors(): void {
  behaviorEditorRegistry.register('patrol', PatrolEditor);
  behaviorEditorRegistry.register('orbit', OrbitEditor);
  behaviorEditorRegistry.register('zigzag', ZigzagEditor);
  behaviorEditorRegistry.register('dash', DashEditor);
  behaviorEditorRegistry.register('wait', WaitEditor);
  behaviorEditorRegistry.register('spiral', SpiralEditor);
  behaviorEditorRegistry.register('cross', CrossEditor);
  behaviorEditorRegistry.register('hide', NoOptionsEditor);
  behaviorEditorRegistry.register('despawn', NoOptionsEditor);
  behaviorEditorRegistry.register('teleport', RawConfigEditor);
  behaviorEditorRegistry.register('jump', RawConfigEditor);
}
