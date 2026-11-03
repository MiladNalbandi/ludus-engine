import { MODULE_API_VERSION, type EditorModule } from '@/shell/module';
import CatalogueScreen from '@/modules/content/screens/Catalogue';
import WaveEditorScreen from '@/modules/content/screens/WaveEditor';
import LevelEditorScreen from '@/modules/content/screens/LevelEditor';

/** Light Wave Maker, as the screen for the `content` app. Its wave JSON format is unchanged. */
export const contentModule: EditorModule = {
  api: MODULE_API_VERSION,
  app: 'content',
  slug: 'content',
  label: 'Content',
  summary: 'Waves and the levels that order them',
  routes: [
    { path: '', title: 'Catalogue', screen: CatalogueScreen },
    { path: 'waves/:id', title: 'Wave', screen: WaveEditorScreen },
    { path: 'levels/new', title: 'New level', screen: LevelEditorScreen },
    { path: 'levels/:id', title: 'Level', screen: LevelEditorScreen },
  ],
};
