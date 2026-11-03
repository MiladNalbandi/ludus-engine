import { apiJson } from '@/lib/api';

/**
 * Who is signed in, from `currentCaller` in the contract.
 *
 * The shell shows it beside the navigation. `project` is the one project this token is for: the
 * contract has no route that lists projects, so there is nothing to pick between yet.
 */
export type CurrentCaller = {
  kind: string;
  subject: string;
  project: string;
  role: string;
};

export const currentCaller = (): Promise<CurrentCaller> => apiJson<CurrentCaller>('/api/v1/me');
