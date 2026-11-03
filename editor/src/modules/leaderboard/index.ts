import { MODULE_API_VERSION, type EditorModule } from '@/shell/module';
import BoardsScreen from '@/modules/leaderboard/screens/Boards';

export const leaderboardModule: EditorModule = {
  api: MODULE_API_VERSION,
  app: 'leaderboard',
  slug: 'leaderboards',
  label: 'Leaderboards',
  summary: 'Boards, and who leads them',
  routes: [
    { path: '', title: 'Leaderboards', screen: BoardsScreen },
    { path: 'boards/:id', title: 'Board', screen: BoardsScreen },
  ],
};
