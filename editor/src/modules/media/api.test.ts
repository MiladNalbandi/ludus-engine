import { describe, expect, it } from 'vitest';
import { formatBytes, media } from '@/modules/media/api';
import { empty, json, mockEngine } from '@/test/engine';

const clip = {
  id: 'c1',
  filename: 'hit.ogg',
  contentType: 'audio/ogg',
  sizeBytes: 2048,
  createdAt: '2026-01-01T00:00:00Z',
};

const sprite = { ...clip, id: 's1', filename: 'ship.png', contentType: 'image/png' };

describe('the media calls', () => {
  it('lists audio clips and sprites from their own routes', async () => {
    mockEngine({
      'GET /api/v1/admin/audio': json([clip]),
      'GET /api/v1/admin/sprites': json([sprite]),
    });

    await expect(media.audio.list()).resolves.toEqual([clip]);
    await expect(media.sprites.list()).resolves.toEqual([sprite]);
  });

  it('uploads as multipart with the file under "file", and lets the browser set the boundary', async () => {
    const sent = mockEngine({
      'POST /api/v1/admin/audio': json(clip, 201),
      'POST /api/v1/admin/sprites': json(sprite, 201),
    });
    const file = new File([new Uint8Array([1, 2, 3])], 'hit.ogg', { type: 'audio/ogg' });

    await expect(media.audio.upload(file)).resolves.toEqual(clip);
    await media.sprites.upload(new File([new Uint8Array([9])], 'ship.png', { type: 'image/png' }));

    const body = sent[0]?.body;
    expect(body).toBeInstanceOf(FormData);
    expect((body as FormData).get('file')).toBeInstanceOf(File);
    expect(((body as FormData).get('file') as File).name).toBe('hit.ogg');
    // A Content-Type set by hand has no boundary, and the engine cannot find the parts.
    expect(sent[0]?.contentType).toBeNull();
    expect(sent[1]?.path).toBe('/api/v1/admin/sprites');
  });

  it('deletes with the delete routes and accepts the 204', async () => {
    const sent = mockEngine({
      'DELETE /api/v1/admin/audio/c1': empty(),
      'DELETE /api/v1/admin/sprites/s1': empty(),
    });

    await media.audio.remove('c1');
    await media.sprites.remove('s1');

    expect(sent.map((r) => `${r.method} ${r.path}`)).toEqual([
      'DELETE /api/v1/admin/audio/c1',
      'DELETE /api/v1/admin/sprites/s1',
    ]);
  });

  it("surfaces the engine's reason when an upload is refused", async () => {
    mockEngine({ 'POST /api/v1/admin/sprites': json({ detail: 'SVG is not accepted as a sprite' }, 415) });

    await expect(media.sprites.upload(new File(['<svg/>'], 'x.svg'))).rejects.toThrow('SVG');
  });

  it('plays and shows the bytes from the public routes, through the proxy', () => {
    expect(media.audio.url('c 1')).toBe('/api/engine/api/v1/public/audio/c%201');
    expect(media.sprites.url('s1')).toBe('/api/engine/api/v1/public/sprites/s1');
  });
});

describe('formatBytes', () => {
  it('reads like a person would say it', () => {
    expect(formatBytes(0)).toBe('0 B');
    expect(formatBytes(999)).toBe('999 B');
    expect(formatBytes(2048)).toBe('2.0 KB');
    expect(formatBytes(12 * 1024 * 1024)).toBe('12.0 MB');
  });
});
