'use client';

import { behaviorEditorRegistry } from '@/components/behaviour/registry';
import { RawConfigEditor } from '@/components/behaviour/fields';
import { NumberField } from '@/components/behaviour/fields';
import { useEditor } from '@/stores/editor';

/**
 * The panel for whichever movement is selected.
 *
 * The form comes from the registry, never from a switch on the type. An unregistered type falls
 * back to the raw JSON editor rather than an empty panel, so a movement without a form is still
 * editable instead of quietly uneditable.
 */
export function Inspector() {
  const timelines = useEditor((state) => state.timelines);
  const selectedRule = useEditor((state) => state.selectedRule);
  const selectedBlock = useEditor((state) => state.selectedBlock);
  const resizeBlock = useEditor((state) => state.resizeBlock);
  const updateBlockConfig = useEditor((state) => state.updateBlockConfig);
  const removeBlock = useEditor((state) => state.removeBlock);

  const block = (timelines[selectedRule] ?? []).find((candidate) => candidate.id === selectedBlock);

  if (!block) {
    return (
      <div className="panel">
        <p className="muted" style={{ margin: 0 }}>
          Select a movement on the timeline to edit it.
        </p>
      </div>
    );
  }

  const Editor = behaviorEditorRegistry.get(block.type) ?? RawConfigEditor;

  return (
    <div className="panel">
      <h3 style={{ marginTop: 0, textTransform: 'capitalize' }}>{block.type}</h3>

      <NumberField
        label="Duration (seconds)"
        value={block.duration}
        min={0}
        step={0.5}
        onChange={(duration) => resizeBlock(block.id, duration)}
      />

      <Editor
        config={block.config ?? {}}
        onChange={(config) => updateBlockConfig(block.id, config)}
      />

      {block.jumpTo ? (
        <p className="muted" style={{ fontSize: '13px' }}>
          This movement begins after an instant jump. The jump takes no time, so it has no block of
          its own — it is part of where this movement starts.
        </p>
      ) : null}

      <button
        type="button"
        onClick={() => removeBlock(block.id)}
        style={{ background: 'var(--danger)', marginTop: '0.75rem' }}
      >
        Remove movement
      </button>
    </div>
  );
}
