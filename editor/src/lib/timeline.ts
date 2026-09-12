import type { MovementStep, MovementType, SpawnPosition } from '@/lib/wave-schema';

/**
 * Converting a movement sequence to something a timeline can draw, and back.
 *
 * A sequence is a list of steps with durations. A timeline is a row of blocks with positions. The
 * conversion between them is almost arithmetic, except for one case that is not, and that case is
 * the reason this file has tests.
 *
 * **A jump of zero duration is not a block.** It relocates the entity instantly, so it occupies no
 * time and has nothing to draw. Rendered as a block it would be a zero-width sliver an author
 * cannot grab; dropped, the round trip would lose it and the entity would carry on from the wrong
 * place. So it is folded into the following block as that block's starting position, and unfolded
 * on the way out.
 *
 * Everything here is pure. The stores call it, the preview calls it, and the tests call it without
 * a browser.
 */

/** The config property for a movement type is always `<type>_config`. Pinned by a test. */
function configKey(type: MovementType): `${MovementType}_config` {
  return `${type}_config`;
}

export type TimelineBlock = {
  /** Stable across edits so React keys and drag state survive a re-render. */
  id: string;
  type: MovementType;
  /**
   * Seconds from the start of the sequence. Derived, never authored: the order of the list is the
   * order of play, and a start time stored beside it would be a second truth for the same fact.
   */
  start: number;
  duration: number;
  /** The `<type>_config` object, carried through untouched. */
  config: Record<string, unknown> | undefined;
  fireRules: MovementStep['fire_rules'];
  cubeRules: MovementStep['cube_rules'];
  /**
   * Where this block begins, when a zero-duration jump preceded it.
   *
   * Undefined means "carry on from wherever the previous movement ended", which is the normal case.
   */
  jumpTo?: SpawnPosition;
};

let nextId = 0;

/** Ids are per-session and never persisted; nothing in the document refers to them. */
function freshId(): string {
  nextId += 1;
  return `block-${nextId}`;
}

/** Only for tests, so a round trip can be compared without ids getting in the way. */
export function resetBlockIds(): void {
  nextId = 0;
}

function isFoldableJump(step: MovementStep): boolean {
  return step.type === 'jump' && step.duration === 0;
}

function jumpTarget(step: MovementStep): SpawnPosition | undefined {
  const config = step.jump_config;
  return config?.target;
}

/**
 * A sequence as blocks, with start times computed and zero-duration jumps folded in.
 *
 * A trailing zero-duration jump has no following block to fold into, so it is kept as a block of
 * its own. That looks like an inconsistency and is the only lossless option: dropping it would
 * silently delete an author's instruction, and the round-trip test is what would have caught it.
 */
export function toTimeline(sequence: readonly MovementStep[]): TimelineBlock[] {
  const blocks: TimelineBlock[] = [];
  let start = 0;
  let pendingJumpTo: SpawnPosition | undefined;

  for (let index = 0; index < sequence.length; index++) {
    const step = sequence[index]!;

    if (isFoldableJump(step) && index < sequence.length - 1) {
      // Folded rather than emitted. A second jump before the same block would overwrite the first,
      // which is also what the game would do -- two instant relocations in a row land at the
      // second one.
      pendingJumpTo = jumpTarget(step);
      continue;
    }

    blocks.push({
      id: freshId(),
      type: step.type,
      start,
      duration: step.duration,
      config: step[configKey(step.type)] as Record<string, unknown> | undefined,
      fireRules: step.fire_rules,
      cubeRules: step.cube_rules,
      ...(pendingJumpTo === undefined ? {} : { jumpTo: pendingJumpTo }),
    });

    pendingJumpTo = undefined;
    start += step.duration;
  }

  return blocks;
}

/**
 * Blocks back to a sequence, unfolding the jumps.
 *
 * `start` is ignored on the way out, deliberately: the list order is the order of play, and
 * honouring both would mean deciding what a gap or an overlap meant. A pause is a `wait` step,
 * which is a thing the schema has.
 */
export function toSequence(blocks: readonly TimelineBlock[]): MovementStep[] {
  const sequence: MovementStep[] = [];

  for (const block of blocks) {
    if (block.jumpTo !== undefined) {
      sequence.push({
        type: 'jump',
        duration: 0,
        jump_config: { target: block.jumpTo },
      });
    }

    const step: MovementStep = { type: block.type, duration: block.duration };
    if (block.config !== undefined) {
      // Written through an index signature. The key is derived from the movement type and the
      // value is carried through unread, so naming the property statically would mean enumerating
      // all eleven config shapes to gain nothing: the object is never read here.
      (step as unknown as Record<string, unknown>)[configKey(block.type)] = block.config;
    }
    if (block.fireRules !== undefined) {
      step.fire_rules = block.fireRules;
    }
    if (block.cubeRules !== undefined) {
      step.cube_rules = block.cubeRules;
    }
    sequence.push(step);
  }

  return sequence;
}

/** How long the whole sequence lasts. Zero-duration jumps contribute nothing, which is the point. */
export function totalDuration(blocks: readonly TimelineBlock[]): number {
  return blocks.reduce((sum, block) => sum + block.duration, 0);
}

/** Recomputes `start` after a reorder, insert or resize. Cheap, and the only way it is ever set. */
export function restart(blocks: readonly TimelineBlock[]): TimelineBlock[] {
  let start = 0;
  return blocks.map((block) => {
    const positioned = { ...block, start };
    start += block.duration;
    return positioned;
  });
}

/** Moves a block, keeping the sequence contiguous. Out-of-range indices are left alone. */
export function move(blocks: readonly TimelineBlock[], from: number, to: number): TimelineBlock[] {
  if (from === to || from < 0 || to < 0 || from >= blocks.length || to >= blocks.length) {
    return restart(blocks);
  }
  const reordered = [...blocks];
  const [moved] = reordered.splice(from, 1);
  reordered.splice(to, 0, moved!);
  return restart(reordered);
}

/** Which block is on screen at a given time, or none past the end. */
export function blockAt(blocks: readonly TimelineBlock[], seconds: number): TimelineBlock | undefined {
  return blocks.find(
    (block) => seconds >= block.start && seconds < block.start + block.duration,
  );
}
