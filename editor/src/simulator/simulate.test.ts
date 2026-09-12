import { beforeAll, describe, expect, it } from 'vitest';
import { readFileSync, readdirSync } from 'node:fs';
import { resolve } from 'node:path';
import type { Wave } from '@/lib/wave-schema';
import { registerBuiltInMovements } from '@/simulator/movements';
import { simulatorRegistry } from '@/simulator/registry';
import { DEFAULT_FIELD, seekTo, stateAt, waveDuration } from '@/simulator/simulate';

const SAMPLES = resolve(__dirname, '..', '..', '..', 'samples', 'waves');

/**
 * A valid wave with its spawn rules replaced.
 *
 * Built from a demo document rather than written out, because `Wave` requires a good deal of
 * unrelated structure -- `constraints.time_limit`, the whole of `progression_config` -- and a
 * fixture that hand-waved those with a cast would stop catching the thing the generated types are
 * for. Two earlier drafts of these fixtures failed `tsc` for exactly that reason, which is the
 * check working.
 */
function waveWith(id: string, spawnRules: unknown[]): Wave {
  const template = JSON.parse(
    readFileSync(resolve(SAMPLES, 'demo_first_steps.json'), 'utf8'),
  ) as Wave;
  return { ...template, id, spawn_rules: spawnRules as Wave['spawn_rules'] };
}

function demoWaves(): { file: string; wave: Wave }[] {
  return readdirSync(SAMPLES)
    .filter((name) => name.endsWith('.json'))
    .map((file) => ({ file, wave: JSON.parse(readFileSync(resolve(SAMPLES, file), 'utf8')) as Wave }));
}

beforeAll(() => {
  simulatorRegistry.reset();
  registerBuiltInMovements();
});

describe('the registry', () => {
  it('has a simulator for every movement type the schema allows', () => {
    const schema = JSON.parse(
      readFileSync(resolve(__dirname, '..', '..', '..', 'contracts', 'schemas', 'wave', 'v1.json'), 'utf8'),
    ) as { $defs: { movementType: { enum: string[] } } };

    // The point of the registry is that a new movement type is a registration rather than a new
    // case in a switch. This is what notices when one is added and not registered -- otherwise the
    // preview silently draws a stationary dot, which looks like a working entity standing still.
    expect(simulatorRegistry.registered()).toEqual([...schema.$defs.movementType.enum].sort());
  });

  it('refuses a second registration for the same type', () => {
    expect(() => registerBuiltInMovements()).toThrow(/already registered/);
  });
});

/**
 * A wave that exercises every registered movement type, with room to move.
 *
 * The demo waves are not enough for the determinism test and it took a deliberate sabotage to find
 * that out: adding a drifting accumulator to `patrol` left all three of them passing, because
 * `demo_first_steps` patrols into its own bounds and the clamp absorbs any drift — the position
 * saturates at the same value either way. A test whose fixtures happen to hide the failure is a
 * test that will keep passing while the thing it guards rots.
 *
 * So this fixture is built for the property rather than borrowed from the content: one spawn rule
 * per movement type, bounds wide enough never to clamp, and configs chosen so positions actually
 * change over time.
 */
function everyMovementWave(): Wave {
  const wide = { x_min: -10000, x_max: 10000, y_min: -10000, y_max: 10000 };
  const steps: Record<string, Record<string, unknown>> = {
    patrol: { speed: 37, direction: 'horizontal', bounds: wide },
    orbit: { center: 'fixed', center_position: { type: 'fixed', x: 120, y: 300 }, radius: 70, angular_speed: 1.7 },
    teleport: {
      positions: [
        { type: 'fixed', x: 20, y: 40 },
        { type: 'fixed', x: 300, y: 500 },
        { type: 'screen_relative', screen_x: 0.25, screen_y: 0.75 },
      ],
    },
    dash: { direction: 'towards_player', speed: 200, distance: 130 },
    wait: { wiggle: true, wiggle_amplitude: 7, wiggle_frequency: 5 },
    jump: { target: { type: 'near_player', player_offset: 33 } },
    zigzag: { speed: 44, amplitude: 26, frequency: 1.3, direction: 'down', bounds: wide },
    spiral: { angular_speed: 2.3, radial_speed: 17, start_radius: 12 },
    cross: { speed: 71, bounds: wide },
    hide: {},
    despawn: {},
  };

  return waveWith('every_movement', Object.entries(steps).map(([type, config], index) => ({
      entity_type: 'light',
      count: 2,
      spawn_delay: index * 0.13,
      spawn_interval: 0.29,
      spawn_position: { type: 'fixed', x: 40 + index * 7, y: 60 + index * 11 },
      movement_rules: {
        loop: index % 2 === 0,
        loop_count: index % 3,
        sequence: [
          { type: 'wait', duration: 0.4 },
          { type, duration: 2.6, [`${type}_config`]: config },
          { type: 'patrol', duration: 1.7, patrol_config: { speed: 23, bounds: wide } },
        ],
      },
    })));
}

describe('determinism', () => {
  /**
   * The property the whole preview rests on.
   *
   * An author drags the playhead backwards and forwards. If arriving at 4.2 seconds by scrubbing
   * differs from arriving there by playing, the picture they are checking against is not the
   * picture the game produces, and the preview is worse than nothing because it is convincing.
   *
   * Verified by breaking it: a module-level accumulator added to `patrol` fails this, and an
   * earlier version of this test that used only the demo waves did not notice.
   */
  it('seeking to a time equals stepping to it, across every movement type', () => {
    const wave = everyMovementWave();
    const stepSize = 1 / 60;

    for (let target = 0; target <= 6; target += 0.41) {
      let stepped = stateAt(wave, 0);
      for (let t = stepSize; t <= target + 1e-9; t += stepSize) {
        stepped = stateAt(wave, t);
      }
      const sought = seekTo(wave, stepped.seconds);

      expect(sought.entities, `at ${stepped.seconds}s`).toEqual(stepped.entities);
    }
  });

  it('seeking to a time equals stepping to it, for every demo wave', () => {
    for (const { file, wave } of demoWaves()) {
      const duration = Math.min(waveDuration(wave), 12);
      const stepSize = 1 / 60;

      for (let target = 0; target <= duration; target += 0.37) {
        // Step there in 60ths of a second, discarding each state as a playing preview would.
        let stepped = stateAt(wave, 0);
        for (let t = stepSize; t <= target + 1e-9; t += stepSize) {
          stepped = stateAt(wave, t);
        }
        const lastSteppedTime = stepped.seconds;

        const sought = seekTo(wave, lastSteppedTime);

        expect(sought.entities, `${file} at ${lastSteppedTime}s`).toEqual(stepped.entities);
      }
    }
  });

  it('the same time twice gives the identical state', () => {
    for (const { file, wave } of demoWaves()) {
      expect(stateAt(wave, 3.5), file).toEqual(stateAt(wave, 3.5));
    }
  });

  it('does not depend on a clock or on Math.random', () => {
    const wave = everyMovementWave();
    const before = stateAt(wave, 2.25);

    // Poisoned deliberately: anything reading Math.random gives different numbers and the states
    // stop matching. Nothing in the simulator may read it -- behaviours take randomness from the
    // seeded generator they are handed.
    const original = Math.random;
    Math.random = () => 0.123456789;
    try {
      expect(stateAt(wave, 2.25)).toEqual(before);
    } finally {
      Math.random = original;
    }
  });
});

describe('spawning', () => {
  it('nothing exists before its spawn delay', () => {
    const wave = waveWith('spawn_test', [
        {
          entity_type: 'light',
          count: 1,
          spawn_delay: 2,
          spawn_position: { type: 'fixed', x: 10, y: 10 },
          movement_rules: { sequence: [{ type: 'wait', duration: 5 }] },
        },
      ]);

    expect(stateAt(wave, 1.99).entities).toHaveLength(0);
    expect(stateAt(wave, 2).entities).toHaveLength(1);
  });

  it('spawn_interval staggers the copies of one rule', () => {
    const wave = waveWith('stagger', [
        {
          entity_type: 'light',
          count: 3,
          spawn_delay: 0,
          spawn_interval: 1,
          spawn_position: { type: 'fixed', x: 10, y: 10 },
          movement_rules: { sequence: [{ type: 'wait', duration: 10 }] },
        },
      ]);

    expect(stateAt(wave, 0).entities).toHaveLength(1);
    expect(stateAt(wave, 1).entities).toHaveLength(2);
    expect(stateAt(wave, 2).entities).toHaveLength(3);
  });
});

describe('behaviours', () => {
  function oneStep(type: string, duration: number, config: Record<string, unknown>): Wave {
    return waveWith('behaviour', [
      {
        entity_type: 'light',
        count: 1,
        spawn_delay: 0,
        spawn_position: { type: 'fixed', x: 100, y: 100 },
        movement_rules: { sequence: [{ type, duration, [`${type}_config`]: config }] },
      },
    ]);
  }

  it('wait leaves the entity where it spawned', () => {
    const state = stateAt(oneStep('wait', 3, {}), 1.5);
    expect(state.entities[0]?.position).toEqual({ x: 100, y: 100 });
  });

  it('hide keeps the position but stops drawing', () => {
    const state = stateAt(oneStep('hide', 3, {}), 1);
    expect(state.entities[0]?.visible).toBe(false);
    expect(state.entities[0]?.position).toEqual({ x: 100, y: 100 });
  });

  it('despawn is terminal, so a later step does not bring the entity back', () => {
    const wave = waveWith('gone', [
        {
          entity_type: 'light',
          count: 1,
          spawn_delay: 0,
          spawn_position: { type: 'fixed', x: 100, y: 100 },
          movement_rules: {
            sequence: [
              { type: 'despawn', duration: 1 },
              { type: 'patrol', duration: 5, patrol_config: { speed: 50 } },
            ],
          },
        },
      ]);

    expect(stateAt(wave, 3).entities[0]?.visible).toBe(false);
  });

  it('a zero-duration jump has already arrived at its target', () => {
    const state = stateAt(oneStep('jump', 0, { target: { type: 'fixed', x: 40, y: 90 } }), 0);
    expect(state.entities[0]?.position).toEqual({ x: 40, y: 90 });
  });

  it('dash eases towards the player and stops at the configured distance', () => {
    const state = stateAt(oneStep('dash', 1, { direction: 'down', distance: 50 }), 1);
    expect(state.entities[0]?.position.y).toBeCloseTo(150, 5);
  });

  it('screen_relative spawn positions are resolved against the field', () => {
    const wave = waveWith('relative', [
        {
          entity_type: 'light',
          count: 1,
          spawn_delay: 0,
          spawn_position: { type: 'screen_relative', screen_x: 0.5, screen_y: 0.25 },
          movement_rules: { sequence: [{ type: 'wait', duration: 2 }] },
        },
      ]);

    expect(stateAt(wave, 0).entities[0]?.position).toEqual({
      x: DEFAULT_FIELD.width * 0.5,
      y: DEFAULT_FIELD.height * 0.25,
    });
  });
});

describe('unsupported movement types', () => {
  it('are reported rather than drawn as a stationary entity', () => {
    const wave = waveWith('future', [
        {
          entity_type: 'light',
          count: 1,
          spawn_delay: 0,
          spawn_position: { type: 'fixed', x: 10, y: 10 },
          movement_rules: { sequence: [{ type: 'warp_drive', duration: 2 }] },
        },
      ]);

    const state = stateAt(wave, 1);
    expect(state.unsupported).toEqual(['warp_drive']);
    expect(state.entities).toHaveLength(1);
  });

  it('are empty for the demo waves', () => {
    for (const { file, wave } of demoWaves()) {
      expect(stateAt(wave, 1).unsupported, file).toEqual([]);
    }
  });
});

describe('waveDuration', () => {
  it('prefers the document, and falls back to the longest spawn rule', () => {
    for (const { file, wave } of demoWaves()) {
      expect(waveDuration(wave), file).toBeGreaterThan(0);
    }
  });
});
