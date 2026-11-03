import { segment, send, sendJson } from '@/lib/requests';

/**
 * Audio clips and sprites: list, upload and delete each, as `listAudioClips`, `uploadAudioClip`,
 * `deleteAudioClip`, `listSprites`, `uploadSprite` and `deleteSprite` in the v1 contract.
 *
 * The bytes are never fetched by this layer. A clip plays, and a sprite shows, straight from the
 * public stream routes through the editor's proxy, which streams rather than buffers.
 */
export type MediaSummary = {
  id: string;
  filename: string;
  contentType: string;
  sizeBytes: number;
  createdAt: string;
};

export type MediaKind = {
  list: () => Promise<MediaSummary[]>;
  upload: (file: File) => Promise<MediaSummary>;
  remove: (id: string) => Promise<void>;
  /** Where the browser fetches the bytes from. */
  url: (id: string) => string;
};

function kind(adminPath: string, publicPath: string): MediaKind {
  return {
    list: () => sendJson<MediaSummary[]>(adminPath),

    upload: (file) => {
      // No Content-Type here: the browser writes multipart/form-data with the boundary in it. Set
      // by hand it would have no boundary, and the engine could not find the parts.
      const form = new FormData();
      form.append('file', file, file.name);
      return sendJson<MediaSummary>(adminPath, { method: 'POST', body: form });
    },

    remove: async (id) => {
      await send(`${adminPath}/${segment(id)}`, { method: 'DELETE' });
    },

    url: (id) => `/api/engine${publicPath}/${segment(id)}`,
  };
}

export const media = {
  audio: kind('/api/v1/admin/audio', '/api/v1/public/audio'),
  sprites: kind('/api/v1/admin/sprites', '/api/v1/public/sprites'),
};

export function formatBytes(bytes: number): string {
  if (bytes < 1024) {
    return `${bytes} B`;
  }
  if (bytes < 1024 * 1024) {
    return `${(bytes / 1024).toFixed(1)} KB`;
  }
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}
