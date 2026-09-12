import { beforeEach, describe, expect, it } from 'vitest';
import { readFileSync, readdirSync } from 'node:fs';
import { resolve } from 'node:path';
import type { MovementStep, MovementType } from '@/lib/wave-schema';
import {
  blockAt,
  move,
  resetBlockIds,
  restart,
  toSequence,
  toTimeline,
  totalDuration,
} from '@/lib/timeline';

/**
 * The conversion, and the one case in it that is not arithmetic.
 *
 * The round-trip tests are the ones that matter. A conversion that loses a step does not throw and
 * does not fail to render — it produces a wave that plays differently from the one the author saved,
 * which is discovered by playing it.
 */
const SCHEMA = JSON.parse(
  readFileSync(resolve(__dirname, '..', '..', '..', 'contracts', 'schemas', 'wave', 'v1.json'), 'utf8'),
) as {
  $defs: {
    movementType: { enum: MovementType[] };
    movementStep: { properties: Record<string, unknown> };
  };
};

const SAMPLES = resolve(__dirname, '..', '..', '..', 'samples', 'waves');

function step(type: MovementType, duration: number, extra: Partial<MovementStep> = {}): MovementStep {
  return { type, duration, ...extra } as MovementStep;
}

beforeEach(() => {
  resetBlockIds();
});

describe('the config key convention', () => {
  it('holds for every movement type in the schema', () => {
    // The conversion derives the config property as `${type}_config`. If a movement type is ever
    // added with a differently named config, this fails here rather than silently dropping that
    // config on every save.
    const missing = SCHEMA.$defs.movementType.enum.filter(
      (type) => !(`${type}_config` in SCHEMA.$defs.movementStep.properties),
    );

    expect(SCHEMA.$defs.movementType.enum).toHaveLength(11);
    expect(missing).toEqual([]);
  });
});

describe('toTimeline', () => {
  it('computes start times by accumulating durations', () => {
    const blocks = toTimeline([step('patrol', 3), step('wait', 2), step('dash', 1)]);

    expect(blocks.map((block) => [block.type, block.start, block.duration])).toEqual([
      ['patrol', 0, 3],
      ['wait', 3, 2],
      ['dash', 5, 1],
    ]);
  });

  it('carries each step config through untouched', () => {
    const blocks = toTimeline([
      step('patrol', 3, { patrol_config: { speed: 2.5, direction: 'horizontal' } }),
    ]);

    expect(blocks[0]?.config).toEqual({ speed: 2.5, direction: 'horizontal' });
  });

  it('folds a zero-duration jump into the next block rather than drawing it', () => {
    const target = { type: 'fixed' as const, x: 40, y: 90 };
    const blocks = toTimeline([
      step('patrol', 2),
      step('jump', 0, { jump_config: { target } }),
      step('dash', 1),
    ]);

    expect(blocks).toHaveLength(2);
    expect(blocks.map((block) => block.type)).toEqual(['patrol', 'dash']);
    expect(blocks[1]?.jumpTo).toEqual(target);
    // The jump takes no time, so the dash still starts at 2.
    expect(blocks[1]?.start).toBe(2);
  });

  it('leaves the timeline contiguous across a fold', () => {
    const blocks = toTimeline([
      step('patrol', 2),
      step('jump', 0, { jump_config: { target: { type: 'fixed', x: 1, y: 1 } } }),
      step('dash', 1),
    ]);

    expect(blocks[1]?.start).toBe(2);
    expect(totalDuration(blocks)).toBe(3);
  });

  it('keeps a jump that takes time as a block of its own', () => {
    const blocks = toTimeline([
      step('jump', 0.5, { jump_config: { target: { type: 'fixed', x: 1, y: 1 } } }),
    ]);

    expect(blocks).toHaveLength(1);
    expect(blocks[0]?.type).toBe('jump');
    expect(blocks[0]?.jumpTo).toBeUndefined();
  });

  it('keeps a trailing zero-duration jump, because there is nothing to fold it into', () => {
    const blocks = toTimeline([
      step('patrol', 2),
      step('jump', 0, { jump_config: { target: { type: 'fixed', x: 5, y: 5 } } }),
    ]);

    expect(blocks).toHaveLength(2);
    expect(blocks[1]?.type).toBe('jump');
    expect(blocks[1]?.duration).toBe(0);
  });

  it('lets a second jump before the same block win, as the game would', () => {
    const first = { type: 'fixed' as const, x: 1, y: 1 };
    const second = { type: 'fixed' as const, x: 2, y: 2 };
    const blocks = toTimeline([
      step('jump', 0, { jump_config: { target: first } }),
      step('jump', 0, { jump_config: { target: second } }),
      step('dash', 1),
    ]);

    expect(blocks).toHaveLength(1);
    expect(blocks[0]?.jumpTo).toEqual(second);
  });

  it('handles an empty sequence', () => {
    expect(toTimeline([])).toEqual([]);
  });
});

describe('round trip', () => {
  function roundTrip(sequence: MovementStep[]): MovementStep[] {
    return toSequence(toTimeline(sequence));
  }

  it('returns a plain sequence unchanged', () => {
    const sequence = [step('patrol', 3), step('wait', 2)];
    expect(roundTrip(sequence)).toEqual(sequence);
  });

  it('restores a folded jump in its original position', () => {
    const sequence = [
      step('patrol', 2),
      step('jump', 0, { jump_config: { target: { type: 'fixed', x: 40, y: 90 } } }),
      step('dash', 1),
    ];

    expect(roundTrip(sequence)).toEqual(sequence);
  });

  it('restores two consecutive jumps as the one that won', () => {
    // Deliberately NOT lossless, and the only case that is not. Two instant relocations in a row
    // are indistinguishable in play from the second one alone, so the timeline shows one and saves
    // one. Asserted explicitly rather than left as a surprise.
    const sequence = [
      step('jump', 0, { jump_config: { target: { type: 'fixed', x: 1, y: 1 } } }),
      step('jump', 0, { jump_config: { target: { type: 'fixed', x: 2, y: 2 } } }),
      step('dash', 1),
    ];

    expect(roundTrip(sequence)).toEqual([
      step('jump', 0, { jump_config: { target: { type: 'fixed', x: 2, y: 2 } } }),
      step('dash', 1),
    ]);
  });

  it('preserves fire and cube rules', () => {
    const sequence = [
      step('patrol', 3, {
        fire_rules: { enabled: true, pattern: 'burst', interval: 0.4 },
        cube_rules: { enemy_chance: 0.25 },
      }),
    ];

    expect(roundTrip(sequence)).toEqual(sequence);
  });

  it('preserves a trailing zero-duration jump', () => {
    const sequence = [
      step('patrol', 2),
      step('jump', 0, { jump_config: { target: { type: 'fixed', x: 5, y: 5 } } }),
    ];

    expect(roundTrip(sequence)).toEqual(sequence);
  });

  it('survives every movement sequence in the demo waves', () => {
    const files = readdirSync(SAMPLES).filter((name) => name.endsWith('.json'));
    expect(files.length).toBeGreaterThan(0);

    for (const file of files) {
      const wave = JSON.parse(readFileSync(resolve(SAMPLES, file), 'utf8')) as {
        spawn_rules: { movement_rules: { sequence: MovementStep[] } }[];
      };

      for (const rule of wave.spawn_rules) {
        const sequence = rule.movement_rules.sequence;
        expect(roundTrip(sequence), `${file} changed on a round trip`).toEqual(sequence);
      }
    }
  });
});

describe('editing helpers', () => {
  it('restart recomputes every start time', () => {
    const blocks = restart([
      { id: 'a', type: 'patrol', start: 99, duration: 2, config: undefined, fireRules: undefined, cubeRules: undefined },
      { id: 'b', type: 'dash', start: 99, duration: 1, config: undefined, fireRules: undefined, cubeRules: undefined },
    ]);

    expect(blocks.map((block) => block.start)).toEqual([0, 2]);
  });

  it('move reorders and repositions', () => {
    const blocks = toTimeline([step('patrol', 2), step('wait', 3), step('dash', 1)]);

    const moved = move(blocks, 2, 0);

    expect(moved.map((block) => [block.type, block.start])).toEqual([
      ['dash', 0],
      ['patrol', 1],
      ['wait', 3],
    ]);
  });

  it('move leaves an out-of-range index alone but still repositions', () => {
    const blocks = toTimeline([step('patrol', 2), step('dash', 1)]);

    expect(move(blocks, 0, 9).map((block) => block.type)).toEqual(['patrol', 'dash']);
    expect(move(blocks, -1, 0).map((block) => block.start)).toEqual([0, 2]);
  });

  it('blockAt finds the block playing at a moment, and nothing past the end', () => {
    const blocks = toTimeline([step('patrol', 2), step('dash', 1)]);

    expect(blockAt(blocks, 0)?.type).toBe('patrol');
    expect(blockAt(blocks, 1.99)?.type).toBe('patrol');
    expect(blockAt(blocks, 2)?.type).toBe('dash');
    expect(blockAt(blocks, 3)).toBeUndefined();
  });

  it('blockAt skips a zero-duration block rather than matching it', () => {
    // A zero-duration block covers no instant at all: start <= t < start is empty for every t.
    const blocks = toTimeline([
      step('jump', 0, { jump_config: { target: { type: 'fixed', x: 1, y: 1 } } }),
    ]);

    expect(blockAt(blocks, 0)).toBeUndefined();
  });
});
