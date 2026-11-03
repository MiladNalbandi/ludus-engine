import { ShellFrame } from '@/shell/ShellFrame';

/**
 * Every signed-in page sits inside the shell. A route group rather than a layout under
 * `[module]`, so that moving between modules keeps the frame mounted instead of starting it again.
 */
export default function ShellLayout({ children }: { children: React.ReactNode }) {
  return <ShellFrame>{children}</ShellFrame>;
}
