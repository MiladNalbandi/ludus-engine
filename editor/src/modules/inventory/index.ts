import { MODULE_API_VERSION, type EditorModule } from '@/shell/module';
import ItemsScreen from '@/modules/inventory/screens/Items';
import SchemaScreen from '@/modules/inventory/screens/Schema';

export const inventoryModule: EditorModule = {
  api: MODULE_API_VERSION,
  app: 'inventory',
  slug: 'inventory',
  label: 'Inventory',
  summary: 'Items players can hold, and their attributes',
  routes: [
    { path: '', title: 'Items', screen: ItemsScreen },
    { path: 'items/:id', title: 'Item', screen: ItemsScreen },
    { path: 'schema', title: 'Attribute schema', screen: SchemaScreen },
  ],
};
