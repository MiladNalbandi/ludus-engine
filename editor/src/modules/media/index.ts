import { MODULE_API_VERSION, type EditorModule } from '@/shell/module';
import { AudioScreen, SpritesScreen } from '@/modules/media/screens/Library';

export const mediaModule: EditorModule = {
  api: MODULE_API_VERSION,
  app: 'media',
  slug: 'media',
  label: 'Media',
  summary: 'Audio clips and sprites, uploaded and streamed',
  routes: [
    { path: '', title: 'Audio clips', screen: AudioScreen },
    { path: 'sprites', title: 'Sprites', screen: SpritesScreen },
  ],
};
