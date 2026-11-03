import type { EditorModule } from '@/shell/module';
import { contentModule } from '@/modules/content';
import { inventoryModule } from '@/modules/inventory';
import { economyModule } from '@/modules/economy';
import { mediaModule } from '@/modules/media';
import { leaderboardModule } from '@/modules/leaderboard';

/**
 * The modules compiled into this editor, in navigation order.
 *
 * This list is the only place the shell learns that a module exists. Content is first, so that
 * signing in lands on the catalogue whenever the content app is loaded.
 */
export const builtInModules: readonly EditorModule[] = [
  contentModule,
  inventoryModule,
  economyModule,
  mediaModule,
  leaderboardModule,
];
