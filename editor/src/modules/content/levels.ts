import { jsonBody, segment, send, sendJson } from '@/lib/requests';
import type { WaveLevelSummary } from '@/modules/content/waves';

/**
 * Authoring a level: `createWaveLevel`, `getWaveLevel`, `updateWaveLevel` and `deleteWaveLevel` in
 * the v1 contract.
 *
 * A level is a name, perhaps a description, and wave ids in play order. An update replaces the
 * wave list wholesale, so the screen edits a local copy and sends all of it; the helpers below
 * build each new order as a new array and never touch the one they were handed.
 */
export type LevelDraft = { name: string; description: string; waves: string[] };

type WaveLevelRequest = { name: string; description?: string; waves: string[] };

const LEVELS = '/api/v1/admin/wave-levels';

/** A blank description is left out, which the engine stores as none. */
export function levelRequest(draft: LevelDraft): WaveLevelRequest {
  const request: WaveLevelRequest = { name: draft.name.trim(), waves: [...draft.waves] };
  const description = draft.description.trim();
  if (description) {
    request.description = description;
  }
  return request;
}

export const levels = {
  get: (id: string): Promise<WaveLevelSummary> =>
    sendJson<WaveLevelSummary>(`${LEVELS}/${segment(id)}`),

  create: (draft: LevelDraft): Promise<WaveLevelSummary> =>
    sendJson<WaveLevelSummary>(LEVELS, jsonBody('POST', levelRequest(draft))),

  update: (id: string, draft: LevelDraft): Promise<WaveLevelSummary> =>
    sendJson<WaveLevelSummary>(`${LEVELS}/${segment(id)}`, jsonBody('PUT', levelRequest(draft))),

  remove: async (id: string): Promise<void> => {
    await send(`${LEVELS}/${segment(id)}`, { method: 'DELETE' });
  },
};

export function draftOfLevel(level: WaveLevelSummary): LevelDraft {
  return {
    name: level.name,
    description: level.description ?? '',
    waves: level.waves.map((member) => member.waveId),
  };
}

/** The list with the wave at `index` moved by `offset`, or the same order past either end. */
export function moveWave(waves: readonly string[], index: number, offset: number): string[] {
  const target = index + offset;
  const next = [...waves];
  if (index < 0 || index >= next.length || target < 0 || target >= next.length) {
    return next;
  }
  const [moved] = next.splice(index, 1);
  next.splice(target, 0, moved as string);
  return next;
}

export function removeWaveAt(waves: readonly string[], index: number): string[] {
  return waves.filter((_, position) => position !== index);
}

/** Appends a wave, unless the level already holds it — the engine refuses a wave named twice. */
export function addWave(waves: readonly string[], waveId: string): string[] {
  return waves.includes(waveId) ? [...waves] : [...waves, waveId];
}

export function checkLevel(draft: LevelDraft): string[] {
  return draft.name.trim() ? [] : ['name: a level needs a name'];
}
