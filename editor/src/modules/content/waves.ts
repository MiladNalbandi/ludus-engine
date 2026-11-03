import { apiJson } from '@/lib/api';

/**
 * The engine's wave and level responses, named after the schemas in the committed contract.
 *
 * These mirror `WaveSummary`, `WaveLevelSummary` and friends in `docs/api/openapi.json`. They are
 * hand-written and small, unlike the wave *document* types, which are generated from the JSON
 * Schema — the difference is that the schema is the source of truth for a document's shape, while
 * these envelope types belong to the HTTP contract and are a handful of fields each.
 */
export type WaveSummary = {
  id: string;
  name: string;
  order: number;
  schemaVersion: number;
  published: boolean;
  createdAt: string;
  updatedAt: string;
};

export type WaveLevelMember = {
  waveId: string;
  published: boolean;
};

export type WaveLevelSummary = {
  id: string;
  name: string;
  description: string | null;
  active: boolean;
  waves: WaveLevelMember[];
  createdAt: string;
  updatedAt: string;
};

export type CurrentCaller = {
  kind: string;
  subject: string;
  project: string;
  role: string;
};

export const engine = {
  me: (): Promise<CurrentCaller> => apiJson<CurrentCaller>('/api/v1/me'),

  waves: (): Promise<WaveSummary[]> => apiJson<WaveSummary[]>('/api/v1/admin/waves'),

  waveLevels: (): Promise<WaveLevelSummary[]> =>
    apiJson<WaveLevelSummary[]>('/api/v1/admin/wave-levels'),

  publish: (id: string): Promise<WaveSummary> =>
    apiJson<WaveSummary>(`/api/v1/admin/waves/${encodeURIComponent(id)}/publish`, {
      method: 'POST',
    }),

  unpublish: (id: string): Promise<WaveSummary> =>
    apiJson<WaveSummary>(`/api/v1/admin/waves/${encodeURIComponent(id)}/unpublish`, {
      method: 'POST',
    }),

  activateLevel: (id: string): Promise<WaveLevelSummary> =>
    apiJson<WaveLevelSummary>(`/api/v1/admin/wave-levels/${encodeURIComponent(id)}/activate`, {
      method: 'POST',
    }),
};
