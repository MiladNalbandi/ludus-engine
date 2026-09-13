import type { MovementStep, SpawnRule, Wave } from '@/lib/wave-schema';
import {
  resolvePosition,
  simulatorRegistry,
  type MovementContext,
  type Vector,
} from '@/simulator/registry';

/**
 * Where everything is at a given moment.
 *
 * The whole simulation is a pure function of time: `stateAt(wave, seconds)` reads the document and
 * returns positions, holding nothing between calls. That is not tidiness — it is what makes
 * scrubbing the timeline correct. A simulator that advanced internal state per frame gives a
 * different picture depending on how you arrived at a moment, so an author who drags the playhead
 * back sees something the game will never show them, and the preview stops being evidence.
 *
 * {@link seekTo} and stepping forward in small increments therefore agree exactly, and there is a
 * test that pins it.
 */
export type SimulatedEntity = {
  /** Which spawn rule and which of its `count` copies this is. */
  key: string;
  ruleIndex: number;
  copy: number;
  position: Vector;
  visible: boolean;
  /** The movement step playing now, for the timeline to highlight. */
  stepIndex: number;
  stepType: string;
};

export type SimulationState = {
  seconds: number;
  entities: SimulatedEntity[];
  /** Movement types the document uses that nothing has registered a simulator for. */
  unsupported: string[];
};

export type Field = { width: number; height: number };

export const DEFAULT_FIELD: Field = { width: 360, height: 640 };

/**
 * A deterministic generator, seeded per entity.
 *
 * `Math.random` would make the preview unreproducible, so behaviours are handed this instead. It is
 * a small integer hash rather than anything strong: the requirement is "same input, same numbers",
 * not unpredictability.
 */
function seeded(seed: number): (n: number) => number {
  return (n: number) => {
    let x = (seed * 2654435761 + n * 40503) >>> 0;
    x ^= x >>> 15;
    x = (x * 2246822519) >>> 0;
    x ^= x >>> 13;
    return (x >>> 0) / 4294967296;
  };
}

/** The player sits at the bottom centre, which is where this game's player is. */
function playerPosition(field: Field): Vector {
  return { x: field.width / 2, y: field.height * 0.88 };
}

/**
 * Walks a movement sequence to a moment, returning where the entity is.
 *
 * Walked from the beginning every time. For a sequence of at most thirty steps that is nothing, and
 * it is what keeps the result independent of how the caller got here.
 */
function walkSequence(
  sequence: readonly MovementStep[],
  loop: boolean,
  loopCount: number,
  elapsed: number,
  origin: Vector,
  field: Field,
  random: (n: number) => number,
): { position: Vector; visible: boolean; stepIndex: number; stepType: string } {
  const player = playerPosition(field);
  const cycle = sequence.reduce((sum, step) => sum + step.duration, 0);

  let time = elapsed;
  if (loop && cycle > 0) {
    const completed = Math.floor(elapsed / cycle);
    // loop_count 0 means infinite, per the schema's own description.
    const limit = loopCount === 0 ? Number.POSITIVE_INFINITY : loopCount;
    time = completed >= limit ? cycle : elapsed % cycle;
  }

  let from = origin;
  let visible = true;
  let stepIndex = 0;
  let stepType = sequence[0]?.type ?? 'wait';
  let consumed = 0;

  for (let index = 0; index < sequence.length; index++) {
    const step = sequence[index]!;
    const simulator = simulatorRegistry.get(step.type);
    const context: MovementContext = {
      elapsed: Math.max(0, Math.min(step.duration, time - consumed)),
      duration: step.duration,
      from,
      player,
      config: step[`${step.type}_config` as keyof MovementStep] as
        | Record<string, unknown>
        | undefined,
      field,
      random,
    };

    const active = time < consumed + step.duration || index === sequence.length - 1;
    if (active) {
      stepIndex = index;
      stepType = step.type;
      if (simulator) {
        return {
          position: simulator.positionAt(context),
          visible: simulator.visible ? simulator.visible(context) : true,
          stepIndex,
          stepType,
        };
      }
      // No simulator: the entity stays where it was, and the caller reports the type as
      // unsupported so the author is told rather than shown a plausible lie.
      return { position: from, visible, stepIndex, stepType };
    }

    // The step is finished. Its end position is where the next one begins.
    if (simulator) {
      const ended: MovementContext = { ...context, elapsed: step.duration };
      from = simulator.positionAt(ended);
      visible = simulator.visible ? simulator.visible(ended) : true;
      if (simulator.terminal) {
        return { position: from, visible: false, stepIndex: index, stepType: step.type };
      }
    }
    consumed += step.duration;
  }

  return { position: from, visible, stepIndex, stepType };
}

function spawnTime(rule: SpawnRule, copy: number): number {
  return rule.spawn_delay + (rule.spawn_interval ?? 0) * copy;
}

/** The whole wave at one instant. */
export function stateAt(wave: Wave, seconds: number, field: Field = DEFAULT_FIELD): SimulationState {
  const entities: SimulatedEntity[] = [];
  const unsupported = new Set<string>();
  const player = playerPosition(field);

  wave.spawn_rules.forEach((rule, ruleIndex) => {
    for (const step of rule.movement_rules.sequence) {
      if (!simulatorRegistry.get(step.type)) {
        unsupported.add(step.type);
      }
    }

    for (let copy = 0; copy < rule.count; copy++) {
      const appears = spawnTime(rule, copy);
      if (seconds < appears) {
        continue;
      }

      const origin = resolvePosition(rule.spawn_position, field, player, {
        x: field.width / 2,
        y: 0,
      });
      const walked = walkSequence(
        rule.movement_rules.sequence,
        rule.movement_rules.loop ?? false,
        rule.movement_rules.loop_count ?? 0,
        seconds - appears,
        origin,
        field,
        // Seeded from the rule and the copy, so the same entity gets the same numbers on every
        // run and two copies of one rule do not move identically.
        seeded(ruleIndex * 1000 + copy + 1),
      );

      entities.push({
        key: `${ruleIndex}-${copy}`,
        ruleIndex,
        copy,
        position: walked.position,
        visible: walked.visible,
        stepIndex: walked.stepIndex,
        stepType: walked.stepType,
      });
    }
  });

  return { seconds, entities, unsupported: [...unsupported].sort() };
}

/** How long the wave runs, from the document or from the longest spawn rule. */
export function waveDuration(wave: Wave): number {
  const longest = wave.spawn_rules.reduce((max, rule) => {
    const sequence = rule.movement_rules.sequence.reduce((sum, step) => sum + step.duration, 0);
    const lastCopy = spawnTime(rule, Math.max(0, rule.count - 1));
    return Math.max(max, lastCopy + sequence);
  }, 0);
  return wave.duration ?? longest;
}

/**
 * The same thing as {@link stateAt}, named for what a scrubbing UI is doing.
 *
 * It is deliberately the identical call and not a different code path. A `seekTo` that took a
 * shortcut the per-frame path did not — or the reverse — is exactly how a preview comes to disagree
 * with itself, and the test asserts the two are the same to the last bit.
 */
export function seekTo(wave: Wave, seconds: number, field: Field = DEFAULT_FIELD): SimulationState {
  return stateAt(wave, seconds, field);
}
