import type { SpawnPosition } from '@/lib/wave-schema';
import {
  bool,
  num,
  progress,
  resolvePosition,
  simulatorRegistry,
  str,
  type MovementContext,
  type MovementSimulator,
  type Vector,
} from '@/simulator/registry';

/**
 * The eleven movement behaviours, each registered under its type.
 *
 * These are a schematic, not a physics engine. The roadmap is explicit that Ludus will not ship a
 * general-purpose 2D simulation — a preview that faithfully reproduces any game's movement *is* a
 * game engine, and the honest alternative is a view that shows an author where an entity goes and
 * when, which is what these do. Anything that depends on the real game's feel has to be checked in
 * the real game.
 *
 * Every one of them is a pure function of elapsed time. None holds state between calls, and none
 * reads a clock or `Math.random`. That is what makes seeking to a time identical to stepping to it,
 * which is the property the determinism test pins.
 */

function bounded(context: MovementContext, point: Vector): Vector {
  const bounds = context.config?.['bounds'] as Record<string, unknown> | undefined;
  const xMin = num(bounds, 'x_min', 0);
  const xMax = num(bounds, 'x_max', context.field.width);
  const yMin = num(bounds, 'y_min', 0);
  const yMax = num(bounds, 'y_max', context.field.height);
  return {
    x: Math.min(xMax, Math.max(xMin, point.x)),
    y: Math.min(yMax, Math.max(yMin, point.y)),
  };
}

/** A triangle wave in `0..1`, so a patrol turns around rather than jumping back. */
function backAndForth(distance: number, span: number): number {
  if (span <= 0) {
    return 0;
  }
  const cycle = distance % (2 * span);
  return cycle <= span ? cycle : 2 * span - cycle;
}

const patrol: MovementSimulator = {
  positionAt(context) {
    const speed = num(context.config, 'speed', 60);
    const direction = str<'horizontal' | 'vertical' | 'both'>(context.config, 'direction', 'horizontal');
    const travelled = speed * context.elapsed;
    const span = direction === 'vertical' ? context.field.height / 3 : context.field.width / 3;
    const offset = backAndForth(travelled, span);

    if (direction === 'vertical') {
      return bounded(context, { x: context.from.x, y: context.from.y + offset });
    }
    if (direction === 'both') {
      return bounded(context, { x: context.from.x + offset, y: context.from.y + offset / 2 });
    }
    return bounded(context, { x: context.from.x + offset, y: context.from.y });
  },
};

const orbit: MovementSimulator = {
  positionAt(context) {
    const radius = num(context.config, 'radius', 80);
    const angularSpeed = num(context.config, 'angular_speed', 1);
    const clockwise = bool(context.config, 'clockwise', true);
    const ratio = (context.config?.['ellipse_ratio'] as number[] | undefined) ?? [1, 1];
    const centre =
      str<'player' | 'fixed'>(context.config, 'center', 'player') === 'player'
        ? context.player
        : resolvePosition(
            context.config?.['center_position'] as SpawnPosition | undefined,
            context.field,
            context.player,
            context.from,
          );

    const angle = angularSpeed * context.elapsed * (clockwise ? 1 : -1);
    return {
      x: centre.x + Math.cos(angle) * radius * (ratio[0] ?? 1),
      y: centre.y + Math.sin(angle) * radius * (ratio[1] ?? 1),
    };
  },
};

const zigzag: MovementSimulator = {
  positionAt(context) {
    const speed = num(context.config, 'speed', 60);
    const amplitude = num(context.config, 'amplitude', 30);
    const frequency = num(context.config, 'frequency', 1);
    const direction = str<'up' | 'down' | 'left' | 'right'>(context.config, 'direction', 'down');
    const along = speed * context.elapsed;
    const across = Math.sin(along * frequency * 0.05) * amplitude;

    const point =
      direction === 'up'
        ? { x: context.from.x + across, y: context.from.y - along }
        : direction === 'down'
          ? { x: context.from.x + across, y: context.from.y + along }
          : direction === 'left'
            ? { x: context.from.x - along, y: context.from.y + across }
            : { x: context.from.x + along, y: context.from.y + across };

    return bounded(context, point);
  },
};

const dash: MovementSimulator = {
  positionAt(context) {
    const distance = num(context.config, 'distance', 120);
    const direction =
      str<'towards_player' | 'away_from_player' | 'up' | 'down' | 'left' | 'right'>(
        context.config,
        'direction',
        'towards_player',
      );
    // Eased with a cubic ease-out, which is what makes a dash read as a dash rather than a slide.
    const eased = 1 - Math.pow(1 - progress(context), 3);
    const travelled = distance * eased;

    let unit: Vector;
    if (direction === 'towards_player' || direction === 'away_from_player') {
      const dx = context.player.x - context.from.x;
      const dy = context.player.y - context.from.y;
      const length = Math.hypot(dx, dy) || 1;
      const sign = direction === 'towards_player' ? 1 : -1;
      unit = { x: (dx / length) * sign, y: (dy / length) * sign };
    } else {
      unit =
        direction === 'up'
          ? { x: 0, y: -1 }
          : direction === 'down'
            ? { x: 0, y: 1 }
            : direction === 'left'
              ? { x: -1, y: 0 }
              : { x: 1, y: 0 };
    }

    return { x: context.from.x + unit.x * travelled, y: context.from.y + unit.y * travelled };
  },
};

const wait: MovementSimulator = {
  positionAt(context) {
    if (!bool(context.config, 'wiggle', false)) {
      return context.from;
    }
    const amplitude = num(context.config, 'wiggle_amplitude', 4);
    const frequency = num(context.config, 'wiggle_frequency', 6);
    return {
      x: context.from.x + Math.sin(context.elapsed * frequency) * amplitude,
      y: context.from.y,
    };
  },
};

/**
 * Steps between fixed positions, holding each for an equal share of the duration.
 *
 * The document gives positions and no per-position timing, so an equal share is the only division
 * available. It is stated here rather than presented as the game's behaviour.
 */
const teleport: MovementSimulator = {
  positionAt(context) {
    const positions = (context.config?.['positions'] as SpawnPosition[] | undefined) ?? [];
    if (positions.length === 0) {
      return context.from;
    }
    const share = context.duration / positions.length;
    const index =
      share > 0
        ? Math.min(positions.length - 1, Math.floor(context.elapsed / share))
        : positions.length - 1;
    return resolvePosition(positions[index], context.field, context.player, context.from);
  },
};

const spiral: MovementSimulator = {
  positionAt(context) {
    const angularSpeed = num(context.config, 'angular_speed', 2);
    const radialSpeed = num(context.config, 'radial_speed', 20);
    const startRadius = num(context.config, 'start_radius', 10);
    const angle = angularSpeed * context.elapsed;
    const radius = startRadius + radialSpeed * context.elapsed;
    return {
      x: context.from.x + Math.cos(angle) * radius,
      y: context.from.y + Math.sin(angle) * radius,
    };
  },
};

/** Straight across and back, through the field's middle. */
const cross: MovementSimulator = {
  positionAt(context) {
    const speed = num(context.config, 'speed', 80);
    const travelled = speed * context.elapsed;
    const span = context.field.width;
    return bounded(context, {
      x: backAndForth(travelled, span),
      y: context.from.y,
    });
  },
};

/** Instantaneous when its duration is zero; otherwise interpolated to the target. */
const jump: MovementSimulator = {
  positionAt(context) {
    const target = resolvePosition(
      context.config?.['target'] as SpawnPosition | undefined,
      context.field,
      context.player,
      context.from,
    );
    const t = progress(context);
    return {
      x: context.from.x + (target.x - context.from.x) * t,
      y: context.from.y + (target.y - context.from.y) * t,
    };
  },
};

const hide: MovementSimulator = {
  positionAt(context) {
    return context.from;
  },
  visible() {
    return false;
  },
};

const despawn: MovementSimulator = {
  positionAt(context) {
    return context.from;
  },
  visible() {
    return false;
  },
  // Nothing after this runs. Without it a sequence that despawns and then patrols would draw an
  // entity that the game has already removed.
  terminal: true,
};

/**
 * Registers all eleven. Called once; calling it twice throws, which is the intended behaviour of
 * the registry rather than something to work around.
 */
export function registerBuiltInMovements(): void {
  simulatorRegistry.register('patrol', patrol);
  simulatorRegistry.register('orbit', orbit);
  simulatorRegistry.register('teleport', teleport);
  simulatorRegistry.register('dash', dash);
  simulatorRegistry.register('wait', wait);
  simulatorRegistry.register('jump', jump);
  simulatorRegistry.register('zigzag', zigzag);
  simulatorRegistry.register('spiral', spiral);
  simulatorRegistry.register('cross', cross);
  simulatorRegistry.register('hide', hide);
  simulatorRegistry.register('despawn', despawn);
}
