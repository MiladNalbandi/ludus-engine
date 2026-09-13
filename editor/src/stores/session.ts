import { create } from 'zustand';

/**
 * The signed-in session.
 *
 * The access token lives here, in memory, and nowhere else. Not `localStorage`, not
 * `sessionStorage`, not a readable cookie: all three are readable by any script that gets onto the
 * page, so one cross-site scripting hole becomes a stolen session that outlives the tab and travels
 * off the machine. Held in a closure it dies with the page, and the httpOnly refresh cookie is what
 * survives a reload.
 *
 * The consequence is deliberate and worth stating: a hard refresh has no access token until the
 * first refresh call completes. That is a spinner, not a logout.
 */
type SessionState = {
  accessToken: string | null;
  status: 'unknown' | 'signed-in' | 'signed-out';
  setAccessToken: (token: string) => void;
  clear: () => void;
};

export const useSession = create<SessionState>((set) => ({
  accessToken: null,
  status: 'unknown',
  setAccessToken: (token) => set({ accessToken: token, status: 'signed-in' }),
  clear: () => set({ accessToken: null, status: 'signed-out' }),
}));

/** Reading and writing the token outside React, which `apiFetch` needs to do. */
export const session = {
  token: (): string | null => useSession.getState().accessToken,
  set: (token: string): void => useSession.getState().setAccessToken(token),
  clear: (): void => useSession.getState().clear(),
};
