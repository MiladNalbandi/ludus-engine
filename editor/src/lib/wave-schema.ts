// SPDX-License-Identifier: AGPL-3.0-or-later
//
// GENERATED FROM contracts/schemas/wave/v1.json -- DO NOT EDIT.
//
// Regenerate with `npm run generate:types` in editor/. CI runs `npm run verify:types` and fails
// on any difference, so editing this by hand is not a shortcut, it is a broken build.

export type SpawnPosition = {
  type: 'screen_relative' | 'fixed' | 'near_player';
  screen_x?: number;
  screen_y?: number;
  x?: number;
  y?: number;
  player_offset?: number;
} & {
  type: 'screen_relative' | 'fixed' | 'near_player';
  screen_x?: number;
  screen_y?: number;
  x?: number;
  y?: number;
  player_offset?: number;
} & {
  type: 'screen_relative' | 'fixed' | 'near_player';
  screen_x?: number;
  screen_y?: number;
  x?: number;
  y?: number;
  player_offset?: number;
} & {
  type: 'screen_relative' | 'fixed' | 'near_player';
  screen_x?: number;
  screen_y?: number;
  x?: number;
  y?: number;
  player_offset?: number;
};
export type MovementStep = {
  type: MovementType;
  duration: number;
  fire_rules?: FireRules;
  cube_rules?: CubeRules;
  patrol_config?: {
    bounds?: Bounds;
    speed?: number;
    direction?: 'horizontal' | 'vertical' | 'both';
  };
  orbit_config?: {
    center?: 'player' | 'fixed';
    center_position?: {};
    radius?: number;
    angular_speed?: number;
    clockwise?: boolean;
    /**
     * @minItems 2
     * @maxItems 2
     */
    ellipse_ratio?: [number, number];
    follow_speed?: number;
  };
  zigzag_config?: {
    bounds?: Bounds;
    speed?: number;
    amplitude?: number;
    frequency?: number;
    direction?: 'up' | 'down' | 'left' | 'right';
  };
  dash_config?: {
    direction?: 'towards_player' | 'away_from_player' | 'up' | 'down' | 'left' | 'right';
    speed?: number;
    distance?: number;
    ease?: string;
  };
  wait_config?: {
    duration?: number;
    wiggle?: boolean;
    wiggle_amplitude?: number;
    wiggle_frequency?: number;
  };
  teleport_config?: {
    /**
     * @minItems 1
     */
    positions: [SpawnPosition, ...SpawnPosition[]];
    stay_duration?: number;
    fade_duration?: number;
  };
  spiral_config?: {
    center?: 'player' | 'fixed';
    center_position?: {};
    start_radius?: number;
    end_radius?: number;
    angular_speed?: number;
    clockwise?: boolean;
  };
  cross_config?: {
    speed?: number;
    pattern?: 'horizontal_first' | 'vertical_first' | 'diagonal';
    bounds?: Bounds;
  };
  jump_config?: {
    target: SpawnPosition;
  };
  hide_config?: {
    fade_duration?: number;
  };
  despawn_config?: {
    fade_duration?: number;
  };
} & {
  type: MovementType;
  duration: number;
  fire_rules?: FireRules;
  cube_rules?: CubeRules;
  patrol_config?: {
    bounds?: Bounds;
    speed?: number;
    direction?: 'horizontal' | 'vertical' | 'both';
  };
  orbit_config?: {
    center?: 'player' | 'fixed';
    center_position?: {};
    radius?: number;
    angular_speed?: number;
    clockwise?: boolean;
    /**
     * @minItems 2
     * @maxItems 2
     */
    ellipse_ratio?: [number, number];
    follow_speed?: number;
  };
  zigzag_config?: {
    bounds?: Bounds;
    speed?: number;
    amplitude?: number;
    frequency?: number;
    direction?: 'up' | 'down' | 'left' | 'right';
  };
  dash_config?: {
    direction?: 'towards_player' | 'away_from_player' | 'up' | 'down' | 'left' | 'right';
    speed?: number;
    distance?: number;
    ease?: string;
  };
  wait_config?: {
    duration?: number;
    wiggle?: boolean;
    wiggle_amplitude?: number;
    wiggle_frequency?: number;
  };
  teleport_config?: {
    /**
     * @minItems 1
     */
    positions: [SpawnPosition, ...SpawnPosition[]];
    stay_duration?: number;
    fade_duration?: number;
  };
  spiral_config?: {
    center?: 'player' | 'fixed';
    center_position?: {};
    start_radius?: number;
    end_radius?: number;
    angular_speed?: number;
    clockwise?: boolean;
  };
  cross_config?: {
    speed?: number;
    pattern?: 'horizontal_first' | 'vertical_first' | 'diagonal';
    bounds?: Bounds;
  };
  jump_config?: {
    target: SpawnPosition;
  };
  hide_config?: {
    fade_duration?: number;
  };
  despawn_config?: {
    fade_duration?: number;
  };
};
/**
 * The movement behaviours a client is expected to understand. Adding a value here is a breaking change for clients built against an earlier generation, so it must come with a schema_version bump.
 */
export type MovementType =
  | 'patrol'
  | 'orbit'
  | 'teleport'
  | 'dash'
  | 'wait'
  | 'jump'
  | 'zigzag'
  | 'spiral'
  | 'cross'
  | 'hide'
  | 'despawn';
export type FireRules = {
  enabled: boolean;
  pattern: FirePattern;
  interval?: number;
  interval_variance?: number;
  targeting?: {
    type: TargetingType;
    player_target_chance?: number;
    fixed_angle?: number;
  };
  bullet_config?: {
    speed?: number;
    speed_variance?: number;
  };
  spread_config?: {
    count?: number;
    angle?: number;
    random_offset?: number;
  };
  burst_config?: {
    count?: number;
    delay?: number;
  };
  wave_config?: {
    count?: number;
    wave_speed?: number;
    amplitude?: number;
  };
  ring_config?: {
    count?: number;
    radius?: number;
  };
  spiral_config?: {
    count?: number;
    rotations?: number;
    speed?: number;
  };
  sequence_config?: {
    max_count?: number;
    delay?: number;
  };
  difficulty_scaling?: {
    interval_multiplier?: number;
    speed_multiplier?: number;
    count_addition?: number;
  };
} & {
  enabled: boolean;
  pattern: FirePattern;
  interval?: number;
  interval_variance?: number;
  targeting?: {
    type: TargetingType;
    player_target_chance?: number;
    fixed_angle?: number;
  };
  bullet_config?: {
    speed?: number;
    speed_variance?: number;
  };
  spread_config?: {
    count?: number;
    angle?: number;
    random_offset?: number;
  };
  burst_config?: {
    count?: number;
    delay?: number;
  };
  wave_config?: {
    count?: number;
    wave_speed?: number;
    amplitude?: number;
  };
  ring_config?: {
    count?: number;
    radius?: number;
  };
  spiral_config?: {
    count?: number;
    rotations?: number;
    speed?: number;
  };
  sequence_config?: {
    max_count?: number;
    delay?: number;
  };
  difficulty_scaling?: {
    interval_multiplier?: number;
    speed_multiplier?: number;
    count_addition?: number;
  };
};
/**
 * The fire patterns a client is expected to understand. Same breaking-change rule as movementType.
 */
export type FirePattern =
  'single' | 'burst' | 'spread' | 'wave' | 'sequence' | 'ring' | 'spiral' | 'shotgun';
export type TargetingType = 'towards_player' | 'down' | 'up' | 'fixed' | 'random';
export type HexColor = string;

/**
 * The contract between the editor (author), the engine (validate and serve) and the game client (consume). A wave is a timed arrangement of entity spawns, movement and fire behaviour.
 */
export interface Wave {
  id: string;
  /**
   * Wave contract generation, a monotonic integer. Compatibility rule: a client ignores any wave whose schema_version exceeds the version it was built against and plays the rest — one unreadable wave costs one wave, never the session. Bump ONLY on breaking changes (removal, rename, redefinition); additive fields and new enum values do not bump it. Optional on the wire: the engine stamps the current generation when a document omits it.
   */
  schema_version?: 1;
  /**
   * Author-facing content version, e.g. 1.0.0. Not used for negotiation.
   */
  version: string;
  name: string;
  wave_name?: string;
  description?: string;
  category?: 'easy' | 'medium' | 'hard' | 'custom';
  /**
   * Only published waves are served on public routes.
   */
  published?: boolean;
  duration?: number;
  /**
   * Fields are optional to tolerate partial authored data.
   */
  difficulty_range?: {
    min_phase?: number;
    max_phase?: number;
    min_score?: number;
    max_score?: number;
  };
  constraints: {
    /**
     * REQUIRED and > 0. A wave without it never completes and traps the player on it forever .
     */
    time_limit: number;
    max_lights?: number;
    max_bullets_on_screen?: number;
  };
  progression_config: {
    /**
     * Unique across waves; the server rejects collisions and auto-assigns on create.
     */
    order: number;
    score_thresholds?: {
      min_score_to_start?: number;
    };
    time_contribution?: {
      enabled?: boolean;
      points_per_second?: number;
      percentage_of_total?: number;
    };
    cube_scoring: {
      enemy_destroyed: number;
      enemy_out_of_view?: number;
      bonus_collected: number;
    };
    completion_conditions?: {
      type: 'any' | 'all';
      time_elapsed?: number;
      score_reached?: number;
      cubes_destroyed?: number;
    };
    combo_multiplier_base?: number;
    combo_multiplier_per_combo?: number;
    combo_multiplier_cap?: number;
    surrender_penalty_factor?: number;
    difficulty_bonus_factor?: number;
  };
  /**
   * @minItems 1
   * @maxItems 30
   */
  spawn_rules: [SpawnRule, ...SpawnRule[]];
  audio_config?: {
    /**
     * Public, game-facing audio URL (relative to backend base URL). Replaces the editor-internal _merged_file.
     */
    file_url?: string;
    /**
     * Resources path for bundled audio (offline/local waves).
     */
    file_path?: string;
    start_time?: number;
    /**
     * Trim end time in seconds; absent = play to end.
     */
    end_time?: number;
    volume?: number;
    loop?: boolean;
    /**
     * Track length in seconds. Validated against constraints.time_limit.
     */
    duration?: number;
  };
  visual_config?: {
    vibe_type?: string;
    intensity?: number;
    primary_color?: HexColor;
    secondary_color?: HexColor;
    animation_speed?: number;
    particle_config?: {};
    screen_effects?: {};
    fade_in?: number;
    fade_out?: number;
  };
}
export interface SpawnRule {
  entity_type: 'light';
  count: number;
  spawn_delay: number;
  /**
   * Delay between successive spawns within this rule.
   */
  spawn_interval?: number;
  spawn_position: SpawnPosition;
  conditions?: ConditionRule;
  /**
   * Per-spawn size override for the spawned entity, as a multiplier of its default size.
   */
  light_size?: {};
  movement_rules: {
    loop?: boolean;
    /**
     * 0 = infinite.
     */
    loop_count?: number;
    /**
     * @minItems 1
     * @maxItems 30
     */
    sequence: [MovementStep, ...MovementStep[]];
  };
  fire_rules?: FireRules;
  cube_rules?: CubeRules;
}
/**
 * Gate on when a spawn rule fires.
 */
export interface ConditionRule {
  probability?: number;
  min_survival_time?: number;
  /**
   * @minItems 2
   * @maxItems 2
   */
  phase_range?: [number, number];
}
export interface CubeRules {
  enemy_chance?: number;
  bonus_distribution?: {
    green?: number;
    pink?: number;
    yellow?: number;
    red?: number;
  };
}
export interface Bounds {
  x_min?: number;
  x_max?: number;
  y_min?: number;
  y_max?: number;
}
