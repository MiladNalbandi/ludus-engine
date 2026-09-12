'use client';

import { useEffect, useRef } from 'react';
import type { Wave } from '@/lib/wave-schema';
import { DEFAULT_FIELD, stateAt, waveDuration } from '@/simulator/simulate';

/**
 * The wave drawn at the playhead's moment.
 *
 * A schematic, and the roadmap is explicit that it will stay one: a preview that faithfully
 * reproduces any game's movement is a game engine, and building that against unknown content means
 * guessing. What this answers is "where does each entity go, and when", which is the question an
 * author is actually asking when they place a movement.
 *
 * It renders from {@link stateAt} and holds nothing itself, so dragging the playhead backwards
 * shows exactly what playing forwards to that moment shows. A canvas that accumulated state per
 * frame would not, and an author checking their work against it would be checking against
 * something the game never produces.
 */
export function Preview({
  wave,
  seconds,
  onScrub,
}: {
  wave: Wave;
  seconds: number;
  onScrub: (seconds: number) => void;
}) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const state = stateAt(wave, seconds);
  const duration = waveDuration(wave);

  useEffect(() => {
    const canvas = canvasRef.current;
    const context = canvas?.getContext('2d');
    if (!canvas || !context) {
      return;
    }

    const { width, height } = DEFAULT_FIELD;
    // Drawn at the device's pixel ratio so the dots are not blurry on a retina display, with the
    // CSS size left at the field's own units so coordinates need no conversion.
    const ratio = window.devicePixelRatio || 1;
    canvas.width = width * ratio;
    canvas.height = height * ratio;
    context.setTransform(ratio, 0, 0, ratio, 0, 0);

    context.fillStyle = '#0b1526';
    context.fillRect(0, 0, width, height);

    // The player, where the simulator puts it.
    context.fillStyle = '#8fa6c4';
    context.beginPath();
    context.arc(width / 2, height * 0.88, 7, 0, Math.PI * 2);
    context.fill();

    for (const entity of state.entities) {
      if (!entity.visible) {
        continue;
      }
      context.fillStyle = '#1ca9f0';
      context.beginPath();
      context.arc(entity.position.x, entity.position.y, 9, 0, Math.PI * 2);
      context.fill();

      context.fillStyle = '#ffffff';
      context.font = '10px Menlo, monospace';
      context.fillText(entity.stepType, entity.position.x + 12, entity.position.y + 3);
    }
  }, [state, seconds]);

  return (
    <div>
      <canvas
        ref={canvasRef}
        aria-label="wave preview"
        style={{
          // Scaled to fit the viewport while keeping the field's aspect ratio. The backing store
          // stays at field resolution, so drawing coordinates need no conversion -- only the
          // element's display size changes. A 640px-tall canvas at natural size pushes the action
          // below the fold on most screens, which makes the preview useless without scrolling.
          height: `min(${DEFAULT_FIELD.height}px, 62vh)`,
          aspectRatio: `${DEFAULT_FIELD.width} / ${DEFAULT_FIELD.height}`,
          maxWidth: '100%',
          borderRadius: 'var(--radius)',
          border: '1px solid rgba(143, 166, 196, 0.3)',
          display: 'block',
        }}
      />

      <input
        type="range"
        aria-label="playhead"
        min={0}
        max={Math.max(duration, 0.1)}
        step={1 / 60}
        value={Math.min(seconds, duration)}
        onChange={(event) => onScrub(Number(event.target.value))}
        style={{
          // Matched to the canvas's displayed width, so the slider sits under the picture it scrubs.
          width: `calc(min(${DEFAULT_FIELD.height}px, 62vh) * ${DEFAULT_FIELD.width} / ${DEFAULT_FIELD.height})`,
          maxWidth: '100%',
          marginTop: '0.75rem',
        }}
      />

      <p className="muted" style={{ fontSize: '13px', margin: '0.25rem 0 0' }}>
        {state.entities.filter((entity) => entity.visible).length} of {state.entities.length}{' '}
        spawned entities visible at {seconds.toFixed(2)}s of {duration}s
      </p>

      {state.unsupported.length > 0 ? (
        <p className="error" style={{ fontSize: '13px' }}>
          {/* Said out loud rather than drawn as a stationary dot, which would look like a working
              entity standing still. */}
          No preview for: {state.unsupported.join(', ')}. Those movements are saved correctly and
          simply are not drawn here.
        </p>
      ) : null}
    </div>
  );
}
