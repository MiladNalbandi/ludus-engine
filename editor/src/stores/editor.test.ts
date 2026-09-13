import { beforeEach, describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import type { Wave } from '@/lib/wave-schema';
import { useEditor } from '@/stores/editor';

const DEMO = JSON.parse(
  readFileSync(
    resolve(__dirname, '..', '..', '..', 'samples', 'waves', 'demo_crossfire.json'),
    'utf8',
  ),
) as Wave;

function fresh(): Wave {
  return JSON.parse(JSON.stringify(DEMO)) as Wave;
}

beforeEach(() => {
  useEditor.getState().close();
});

describe('loading', () => {
  it('builds one timeline per spawn rule', () => {
    const wave = fresh();
    useEditor.getState().load(wave);

    expect(useEditor.getState().timelines).toHaveLength(wave.spawn_rules.length);
  });

  it('starts clean, so nothing is saved that the author did not change', () => {
    useEditor.getState().load(fresh());
    expect(useEditor.getState().dirty).toBe(false);
  });

  it('round-trips an untouched document byte-for-byte in structure', () => {
    const wave = fresh();
    useEditor.getState().load(wave);

    // This is the assertion that matters most for the store: opening a wave and saving it without
    // touching anything must produce the same document. If it does not, every author who opens a
    // wave to look at it and saves out of habit silently rewrites it -- and the ETag moves, so
    // every client re-downloads the catalogue for no reason.
    expect(useEditor.getState().document()).toEqual(wave);
  });
});

describe('editing', () => {
  it('marks the document dirty only once something changes', () => {
    useEditor.getState().load(fresh());
    expect(useEditor.getState().dirty).toBe(false);

    useEditor.getState().resizeBlock(useEditor.getState().timelines[0]![0]!.id, 5);

    expect(useEditor.getState().dirty).toBe(true);
  });

  it('resizing keeps the timeline contiguous', () => {
    useEditor.getState().load(fresh());
    // A rule with at least two blocks, since "contiguous" is a statement about the block after the
    // one that changed. The first draft of this used rule 0, which has a single movement in this
    // demo wave, and failed on an assertion about a block that was never there.
    const ruleIndex = useEditor
      .getState()
      .timelines.findIndex((timeline) => timeline.length >= 2);
    expect(ruleIndex, 'no spawn rule in the fixture has two movements').toBeGreaterThanOrEqual(0);

    useEditor.getState().selectRule(ruleIndex);
    const first = useEditor.getState().timelines[ruleIndex]![0]!;
    const secondDuration = useEditor.getState().timelines[ruleIndex]![1]!.duration;

    useEditor.getState().resizeBlock(first.id, 10);

    const timeline = useEditor.getState().timelines[ruleIndex]!;
    expect(timeline[0]?.duration).toBe(10);
    expect(timeline[1]?.start).toBe(10);
    expect(timeline[1]?.duration, 'the following block must not be resized too').toBe(
      secondDuration,
    );
  });

  it('resizing one rule leaves the other rules alone', () => {
    useEditor.getState().load(fresh());
    const before = JSON.stringify(useEditor.getState().timelines[1]);

    useEditor.getState().selectRule(0);
    useEditor.getState().resizeBlock(useEditor.getState().timelines[0]![0]!.id, 99);

    expect(JSON.stringify(useEditor.getState().timelines[1])).toBe(before);
  });

  it('refuses a negative duration rather than producing a document the engine will reject', () => {
    useEditor.getState().load(fresh());
    useEditor.getState().selectRule(0);
    const first = useEditor.getState().timelines[0]![0]!;

    useEditor.getState().resizeBlock(first.id, -4);

    expect(useEditor.getState().timelines[0]?.[0]?.duration).toBe(0);
  });

  it('adding a block appends it with a visible duration', () => {
    useEditor.getState().load(fresh());
    const before = useEditor.getState().timelines[0]!.length;

    useEditor.getState().addBlock('wait');

    const timeline = useEditor.getState().timelines[0]!;
    expect(timeline).toHaveLength(before + 1);
    expect(timeline.at(-1)?.duration).toBeGreaterThan(0);
  });

  it('removing a block clears the selection if it was selected', () => {
    useEditor.getState().load(fresh());
    const first = useEditor.getState().timelines[0]![0]!;
    useEditor.getState().selectBlock(first.id);

    useEditor.getState().removeBlock(first.id);

    expect(useEditor.getState().selectedBlock).toBeNull();
    expect(useEditor.getState().timelines[0]!.map((b) => b.id)).not.toContain(first.id);
  });

  it('edits only the selected rule, not every rule at once', () => {
    const wave = fresh();
    if (wave.spawn_rules.length < 2) {
      return; // nothing to prove on a single-rule document
    }
    useEditor.getState().load(wave);
    const otherBefore = useEditor.getState().timelines[1]!.length;

    useEditor.getState().selectRule(0);
    useEditor.getState().addBlock('wait');

    expect(useEditor.getState().timelines[1]).toHaveLength(otherBefore);
  });

  it('an edit reaches the saved document', () => {
    useEditor.getState().load(fresh());
    useEditor.getState().addBlock('hide');

    const saved = useEditor.getState().document()!;
    expect(saved.spawn_rules[0]?.movement_rules.sequence.at(-1)?.type).toBe('hide');
  });

  it('keeps everything outside the movement sequences untouched', () => {
    const wave = fresh();
    useEditor.getState().load(wave);
    useEditor.getState().addBlock('wait');

    const saved = useEditor.getState().document()!;
    expect(saved.name).toBe(wave.name);
    expect(saved.constraints).toEqual(wave.constraints);
    expect(saved.progression_config).toEqual(wave.progression_config);
    expect(saved.spawn_rules[0]?.spawn_position).toEqual(wave.spawn_rules[0]?.spawn_position);
  });
});

describe('the playhead', () => {
  it('never goes negative', () => {
    useEditor.getState().load(fresh());
    useEditor.getState().setPlayhead(-3);
    expect(useEditor.getState().playhead).toBe(0);
  });
});
