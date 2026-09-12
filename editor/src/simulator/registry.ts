import type { MovementType, SpawnPosition } from '@/lib/wave-schema';

/**
 * Where movement behaviours are looked up, rather than switched on.
 *
 * A `switch (step.type)` works and is the obvious thing. The reason not to is `v1.1.0`, which turns
 * entity, behaviour and content types into data: every `switch` over a closed set of eleven types is
 * a place that release has to find and unpick, and they are never all in one file by then. A map is
 * already the shape that work needs — a plugin registers into it and the simulator does not change.
 *
 * It is also the difference between a missing behaviour being a visible gap and being a silent
 * default. An unregistered type returns undefined here, and the caller shows the author that the
 * preview cannot draw it, rather than rendering a stationary dot that looks like a working entity
 * standing still.
 */
export type Vector = { x: number; y: number };

/** What a behaviour is told. Everything here is a value; nothing is mutated. */
export type MovementContext = {
  /** Seconds since this movement step began, clamped to its duration. */
  elapsed: number;
  /** How long the step lasts. Zero for an instantaneous one. */
  duration: number;
  /** Where the entity was when the step began. */
  from: Vector;
  /** The player's position, for behaviours that track it. */
  player: Vector;
  /** The `<type>_config` object from the document, unread by anything else. */
  config: Record<string, unknown> | undefined;
  /** The playfield, in the same units as positions. */
  field: { width: number; height: number };
  /**
   * Deterministic pseudo-randomness.
   *
   * A behaviour that wants jitter must take it from here and not from `Math.random`, or the preview
   * stops being reproducible — and a preview that cannot be rewound to the same picture is a
   * preview an author cannot use to check anything.
   */
  random: (n: number) => number;
};

export type MovementSimulator = {
  /** Where the entity is, `elapsed` seconds into this step. */
  positionAt: (context: MovementContext) => Vector;
  /** False while the entity should not be drawn — `hide`, and anything after `despawn`. */
  visible?: (context: MovementContext) => boolean;
  /** True when the entity is gone for good and later steps should not run. */
  terminal?: boolean;
};

const simulators = new Map<string, MovementSimulator>();

export const simulatorRegistry = {
  register(type: MovementType, simulator: MovementSimulator): void {
    if (simulators.has(type)) {
      // Registering twice means two behaviours claim one type, and whichever loaded last silently
      // wins. That is worth a crash at start-up rather than a preview that is subtly wrong.
      throw new Error(`a simulator for '${type}' is already registered`);
    }
    simulators.set(type, simulator);
  },

  get(type: string): MovementSimulator | undefined {
    return simulators.get(type);
  },

  registered(): string[] {
    return [...simulators.keys()].sort();
  },

  /** Only for tests, which need to build a registry from nothing. */
  reset(): void {
    simulators.clear();
  },
};

/** Resolves a spawn position into field coordinates. Shared by spawning and by `jump`. */
export function resolvePosition(
  position: SpawnPosition | undefined,
  field: { width: number; height: number },
  player: Vector,
  fallback: Vector,
): Vector {
  if (!position) {
    return fallback;
  }
  switch (position.type) {
    case 'screen_relative':
      return {
        x: (position.screen_x ?? 0.5) * field.width,
        y: (position.screen_y ?? 0.5) * field.height,
      };
    case 'fixed':
      return { x: position.x ?? fallback.x, y: position.y ?? fallback.y };
    case 'near_player':
      return { x: player.x + (position.player_offset ?? 0), y: player.y };
    default:
      return fallback;
  }
}

/** Reads a number out of an unread config object, with a default. */
export function num(config: Record<string, unknown> | undefined, key: string, fallback: number): number {
  const value = config?.[key];
  return typeof value === 'number' && Number.isFinite(value) ? value : fallback;
}

export function str<T extends string>(
  config: Record<string, unknown> | undefined,
  key: string,
  fallback: T,
): T {
  const value = config?.[key];
  return typeof value === 'string' ? (value as T) : fallback;
}

export function bool(config: Record<string, unknown> | undefined, key: string, fallback: boolean): boolean {
  const value = config?.[key];
  return typeof value === 'boolean' ? value : fallback;
}

/** `0..1` through the step. Zero-duration steps are complete from the first instant. */
export function progress(context: MovementContext): number {
  if (context.duration <= 0) {
    return 1;
  }
  return Math.min(1, Math.max(0, context.elapsed / context.duration));
}
