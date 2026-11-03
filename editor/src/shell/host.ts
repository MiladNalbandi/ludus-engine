'use client';

import * as React from 'react';
import { apiFetch, apiJson, NotSignedIn } from '@/lib/api';
import { jsonBody, Refused, segment, send, sendJson, sendText } from '@/lib/requests';
import { ConfirmDelete, EngineError, Problems, SubNav } from '@/lib/ui';
import { formatMoment, useEngineCall } from '@/lib/useEngineCall';
import { MODULE_API_VERSION, type ModuleHost } from '@/shell/module';

/**
 * What a plugin's factory is given: the editor's own React and the helpers a built-in module
 * imports from `src/lib/`.
 *
 * Frozen, all the way down to the groups, so one plugin cannot swap `engine.fetch` for its own
 * and have every plugin loaded after it send requests through that. It is a guard against
 * accidents, not a sandbox: a plugin's code runs on this origin, and the trust that buys is
 * decided when the plugin is installed (see `docs/platform/r8.md`).
 */
export const moduleHost: ModuleHost = Object.freeze({
  api: MODULE_API_VERSION,
  React,
  engine: Object.freeze({
    fetch: apiFetch,
    json: apiJson,
    send,
    sendJson,
    sendText,
    jsonBody,
    segment,
    Refused,
    NotSignedIn,
  }),
  useEngineCall,
  formatMoment,
  ui: Object.freeze({ ConfirmDelete, Problems, EngineError, SubNav }),
});
