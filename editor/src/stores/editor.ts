import { create } from 'zustand';
import type { MovementStep, MovementType, Wave } from '@/lib/wave-schema';
import { move, restart, toSequence, toTimeline, type TimelineBlock } from '@/lib/timeline';

/**
 * The wave being edited.
 *
 * The document is the truth and the blocks are a view of it, rebuilt whenever a document is loaded
 * and converted back whenever one is saved. Keeping both and syncing them would mean two truths and
 * a reconciliation bug; instead, every edit here goes through the conversion in `lib/timeline`.
 *
 * Nothing is saved implicitly. `dirty` says whether the document in hand differs from the one the
 * engine has, and an editor that autosaved would publish half-finished thinking to anyone who
 * happened to fetch between keystrokes — the engine's draft/publish split makes that recoverable
 * but not invisible.
 */
type EditorState = {
  wave: Wave | null;
  /** One timeline per spawn rule, because each spawn rule has its own movement sequence. */
  timelines: TimelineBlock[][];
  selectedRule: number;
  selectedBlock: string | null;
  playhead: number;
  dirty: boolean;

  load: (wave: Wave) => void;
  close: () => void;
  selectRule: (index: number) => void;
  selectBlock: (id: string | null) => void;
  setPlayhead: (seconds: number) => void;

  moveBlock: (from: number, to: number) => void;
  resizeBlock: (id: string, duration: number) => void;
  updateBlockConfig: (id: string, config: Record<string, unknown>) => void;
  addBlock: (type: MovementType) => void;
  removeBlock: (id: string) => void;

  /** The document as it would be saved, with every timeline converted back. */
  document: () => Wave | null;
};

/** A new block gets a sensible duration rather than zero, which would be invisible. */
const DEFAULT_DURATION = 2;

function sequencesOf(wave: Wave): MovementStep[][] {
  return wave.spawn_rules.map((rule) => rule.movement_rules.sequence);
}

export const useEditor = create<EditorState>((set, get) => ({
  wave: null,
  timelines: [],
  selectedRule: 0,
  selectedBlock: null,
  playhead: 0,
  dirty: false,

  load: (wave) =>
    set({
      wave,
      timelines: sequencesOf(wave).map((sequence) => toTimeline(sequence)),
      selectedRule: 0,
      selectedBlock: null,
      playhead: 0,
      dirty: false,
    }),

  close: () =>
    set({ wave: null, timelines: [], selectedBlock: null, playhead: 0, dirty: false }),

  selectRule: (index) => set({ selectedRule: index, selectedBlock: null }),
  selectBlock: (id) => set({ selectedBlock: id }),
  setPlayhead: (seconds) => set({ playhead: Math.max(0, seconds) }),

  moveBlock: (from, to) =>
    set((state) => ({
      timelines: state.timelines.map((timeline, index) =>
        index === state.selectedRule ? move(timeline, from, to) : timeline,
      ),
      dirty: true,
    })),

  resizeBlock: (id, duration) =>
    set((state) => ({
      timelines: state.timelines.map((timeline, index) =>
        index === state.selectedRule
          ? restart(
              timeline.map((block) =>
                // Never negative. A negative duration is not a shorter block, it is a document the
                // engine will refuse with a schema error about a minimum.
                block.id === id ? { ...block, duration: Math.max(0, duration) } : block,
              ),
            )
          : timeline,
      ),
      dirty: true,
    })),

  updateBlockConfig: (id, config) =>
    set((state) => ({
      timelines: state.timelines.map((timeline, index) =>
        index === state.selectedRule
          ? timeline.map((block) => (block.id === id ? { ...block, config } : block))
          : timeline,
      ),
      dirty: true,
    })),

  addBlock: (type) =>
    set((state) => ({
      timelines: state.timelines.map((timeline, index) => {
        if (index !== state.selectedRule) {
          return timeline;
        }
        return restart([
          ...timeline,
          {
            id: `new-${Date.now()}-${timeline.length}`,
            type,
            start: 0,
            duration: DEFAULT_DURATION,
            config: undefined,
            fireRules: undefined,
            cubeRules: undefined,
          },
        ]);
      }),
      dirty: true,
    })),

  removeBlock: (id) =>
    set((state) => ({
      timelines: state.timelines.map((timeline, index) =>
        index === state.selectedRule
          ? restart(timeline.filter((block) => block.id !== id))
          : timeline,
      ),
      selectedBlock: state.selectedBlock === id ? null : state.selectedBlock,
      dirty: true,
    })),

  document: () => {
    const { wave, timelines } = get();
    if (!wave) {
      return null;
    }
    return {
      ...wave,
      // The schema says a wave has at least one spawn rule, so the generated type is a non-empty
      // tuple and `map` widens it to a plain array. The mapping is one-to-one, so non-emptiness is
      // preserved -- this narrows the type back rather than asserting something new.
      spawn_rules: wave.spawn_rules.map((rule, index) => ({
        ...rule,
        movement_rules: {
          ...rule.movement_rules,
          sequence: toSequence(timelines[index] ?? []),
        },
      })) as Wave['spawn_rules'],
    };
  },
}));
