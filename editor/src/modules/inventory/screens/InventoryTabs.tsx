'use client';

import { SubNav } from '@/lib/ui';
import type { ModuleScreenProps } from '@/shell/module';

export function InventoryTabs({
  href,
  current,
}: {
  href: ModuleScreenProps['href'];
  current: 'items' | 'schema';
}) {
  return (
    <SubNav
      label="Inventory"
      tabs={[
        { href: href(), label: 'Items', current: current === 'items' },
        { href: href('schema'), label: 'Attribute schema', current: current === 'schema' },
      ]}
    />
  );
}
