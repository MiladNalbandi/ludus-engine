import { beforeEach, describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { behaviorEditorRegistry } from '@/components/behaviour/registry';
import { registerBuiltInBehaviourEditors } from '@/components/behaviour/panels';

beforeEach(() => {
  behaviorEditorRegistry.reset();
});

describe('the behaviour editor registry', () => {
  it('has a panel for every movement type the schema allows', () => {
    registerBuiltInBehaviourEditors();

    const schema = JSON.parse(
      readFileSync(
        resolve(__dirname, '..', '..', '..', '..', 'contracts', 'schemas', 'wave', 'v1.json'),
        'utf8',
      ),
    ) as { $defs: { movementType: { enum: string[] } } };

    // A movement type with no panel is a movement an author cannot edit. This is what notices,
    // rather than a blank area in the inspector that looks like a rendering bug.
    expect(behaviorEditorRegistry.registered()).toEqual(
      [...schema.$defs.movementType.enum].sort(),
    );
  });

  it('refuses two panels for one type instead of letting the last import win', () => {
    registerBuiltInBehaviourEditors();
    expect(() => registerBuiltInBehaviourEditors()).toThrow(/already registered/);
  });

  it('returns undefined for an unknown type, so the caller can fall back', () => {
    registerBuiltInBehaviourEditors();
    expect(behaviorEditorRegistry.get('warp_drive')).toBeUndefined();
  });
});
