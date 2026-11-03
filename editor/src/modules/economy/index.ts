import { MODULE_API_VERSION, type EditorModule } from '@/shell/module';
import WalletsScreen from '@/modules/economy/screens/Wallets';

export const economyModule: EditorModule = {
  api: MODULE_API_VERSION,
  app: 'economy',
  slug: 'economy',
  label: 'Economy',
  summary: "Players' wallets, and granting currency",
  routes: [
    { path: '', title: 'Wallets', screen: WalletsScreen },
    { path: 'players/:id', title: 'Wallet', screen: WalletsScreen },
  ],
};
