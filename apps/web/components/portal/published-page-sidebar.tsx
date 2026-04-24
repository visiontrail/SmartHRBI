"use client";

import type { PublishedSidebarItem } from "@/lib/portal/api";

export function PublishedPageSidebar({ items }: { items: PublishedSidebarItem[] }) {
  return (
    <nav className="w-56 shrink-0 overflow-auto border-r border-[#e2dccf] bg-[#fffdf7] p-4">
      {items.map((item) => (
        <a key={item.id} href={`#${item.anchorRowId}`} className="block py-2 text-sm font-semibold">
          {item.label}
          {item.children?.map((child) => (
            <span key={child.id} className="ml-4 block py-1 text-xs font-normal text-[#777166]">
              {child.label}
            </span>
          ))}
        </a>
      ))}
    </nav>
  );
}
