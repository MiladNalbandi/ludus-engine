import type { ComponentType } from 'react';
import type { MovementType } from '@/lib/wave-schema';

/**
 * Where a movement's editing panel is looked up, rather than switched on.
 *
 * The predecessor dispatched three thousand lines of hand-written forms through
 * `switch (action.type)`. Converting that to a registry is the difference between `v1.1.0` —
 * entity, behaviour and content types becoming data — being a feature and being a rewrite of all
 * of them: a plugin registers a panel here and nothing else changes.
 *
 * An unregistered type falls back to the raw editor rather than rendering nothing, so a movement
 * the editor does not have a form for is still editable instead of being quietly uneditable.
 */
export type BehaviourEditorProps = {
  config: Record<string, unknown>;
  onChange: (config: Record<string, unknown>) => void;
};

export type BehaviourEditor = ComponentType<BehaviourEditorProps>;

const editors = new Map<string, BehaviourEditor>();

export const behaviorEditorRegistry = {
  register(type: MovementType, editor: BehaviourEditor): void {
    if (editors.has(type)) {
      throw new Error(`a behaviour editor for '${type}' is already registered`);
    }
    editors.set(type, editor);
  },

  get(type: string): BehaviourEditor | undefined {
    return editors.get(type);
  },

  registered(): string[] {
    return [...editors.keys()].sort();
  },

  reset(): void {
    editors.clear();
  },
};
