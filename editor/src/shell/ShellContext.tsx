'use client';

import { createContext, useContext } from 'react';
import type { CurrentCaller } from '@/shell/caller';
import type { AppReport, ModuleRegistry } from '@/shell/registry';

/** What the shell knows once it has started: who is signed in, and what the service runs. */
export type ShellState = {
  registry: ModuleRegistry;
  report: AppReport;
  caller: CurrentCaller | null;
};

export const ShellContext = createContext<ShellState | null>(null);

/** For the shell's own pages. Modules get what they need as props, never from here. */
export function useShell(): ShellState {
  const state = useContext(ShellContext);
  if (!state) {
    throw new Error('useShell is only available inside the shell frame');
  }
  return state;
}
