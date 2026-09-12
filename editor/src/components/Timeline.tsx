'use client';

import { useEditor } from '@/stores/editor';
import { totalDuration } from '@/lib/timeline';

/**
 * The movement sequence as a row of blocks, with a playhead.
 *
 * Widths are proportional to duration, which is the whole point of a timeline: an author sees that
 * the orbit lasts four times as long as the dash without reading two numbers. A zero-duration block
 * would be invisible, so it is drawn at a minimum width with its real duration still zero — the
 * alternative is a block nobody can click.
 */
export function Timeline() {
  const timelines = useEditor((state) => state.timelines);
  const selectedRule = useEditor((state) => state.selectedRule);
  const selectedBlock = useEditor((state) => state.selectedBlock);
  const playhead = useEditor((state) => state.playhead);
  const selectBlock = useEditor((state) => state.selectBlock);
  const setPlayhead = useEditor((state) => state.setPlayhead);
  const moveBlock = useEditor((state) => state.moveBlock);

  const blocks = timelines[selectedRule] ?? [];
  const total = totalDuration(blocks);

  return (
    <div>
      <div
        className="panel"
        style={{ position: 'relative', display: 'flex', gap: '2px', padding: '0.5rem', minHeight: '4.5rem' }}
        onClick={(event) => {
          // Clicking the track scrubs. Computed from the click's position within the element so it
          // stays right whatever the panel's width is.
          const bounds = event.currentTarget.getBoundingClientRect();
          const ratio = (event.clientX - bounds.left) / bounds.width;
          setPlayhead(Math.max(0, Math.min(1, ratio)) * total);
        }}
      >
        {blocks.length === 0 ? (
          <p className="muted" style={{ margin: 'auto' }}>
            This spawn rule has no movements yet.
          </p>
        ) : (
          blocks.map((block, index) => (
            <button
              key={block.id}
              type="button"
              title={`${block.type} · ${block.duration}s${block.jumpTo ? ' · jumps here first' : ''}`}
              onClick={(event) => {
                event.stopPropagation();
                selectBlock(block.id);
              }}
              style={{
                // A floor, so a zero-duration block is still clickable.
                flexGrow: Math.max(block.duration, total * 0.04),
                flexBasis: 0,
                minWidth: '2.5rem',
                background:
                  selectedBlock === block.id ? 'var(--blue)' : 'var(--navy)',
                color: selectedBlock === block.id ? 'var(--navy)' : 'var(--text)',
                border: `1px solid ${selectedBlock === block.id ? 'var(--blue)' : 'var(--slate)'}`,
                borderRadius: 'var(--radius)',
                padding: '0.5rem 0.4rem',
                fontSize: '12px',
                overflow: 'hidden',
                textAlign: 'left',
                position: 'relative',
              }}
            >
              {/* A folded zero-duration jump is shown as a marker on the block it precedes,
                  because that is what it is: where this movement begins. */}
              {block.jumpTo ? (
                <span
                  aria-label="jumps before this movement"
                  style={{ position: 'absolute', left: 2, top: 2, color: 'var(--danger)' }}
                >
                  ↷
                </span>
              ) : null}
              <div style={{ fontWeight: 600 }}>{block.type}</div>
              <div className={selectedBlock === block.id ? undefined : 'muted'}>
                {block.duration}s
              </div>
              <div style={{ display: 'flex', gap: '2px', marginTop: '0.3rem' }}>
                <span
                  role="button"
                  tabIndex={0}
                  aria-label={`move ${block.type} earlier`}
                  onClick={(event) => {
                    event.stopPropagation();
                    moveBlock(index, index - 1);
                  }}
                  onKeyDown={(event) => {
                    if (event.key === 'Enter') {
                      moveBlock(index, index - 1);
                    }
                  }}
                  style={{ cursor: 'pointer', opacity: index === 0 ? 0.3 : 1 }}
                >
                  ‹
                </span>
                <span
                  role="button"
                  tabIndex={0}
                  aria-label={`move ${block.type} later`}
                  onClick={(event) => {
                    event.stopPropagation();
                    moveBlock(index, index + 1);
                  }}
                  onKeyDown={(event) => {
                    if (event.key === 'Enter') {
                      moveBlock(index, index + 1);
                    }
                  }}
                  style={{ cursor: 'pointer', opacity: index === blocks.length - 1 ? 0.3 : 1 }}
                >
                  ›
                </span>
              </div>
            </button>
          ))
        )}

        {total > 0 ? (
          <div
            aria-hidden
            style={{
              position: 'absolute',
              top: 0,
              bottom: 0,
              left: `${Math.min(100, (playhead / total) * 100)}%`,
              width: '2px',
              background: 'var(--danger)',
              pointerEvents: 'none',
            }}
          />
        ) : null}
      </div>

      <p className="muted" style={{ fontSize: '13px' }}>
        {blocks.length} movement{blocks.length === 1 ? '' : 's'} · {total}s ·{' '}
        playhead at {playhead.toFixed(2)}s
      </p>
    </div>
  );
}
