import {
  Coffee,
  type LucideIcon,
  Package,
  Pill,
  Plug,
  Shirt,
  ShoppingBasket,
  Smartphone,
  Store,
} from "lucide-react";

/** Logo mark from public/logo.svg with the wordmark set in the display face. */
export function Logo({ compact = false }: { compact?: boolean }) {
  return (
    <span className="flex items-center gap-2.5">
      <img src="/logo.svg" alt="" aria-hidden="true" className="h-8 w-8" />
      {!compact && (
        <span className="display text-[1.35rem] font-bold leading-none tracking-[0.02em] text-navy">
          JACHAI
        </span>
      )}
    </span>
  );
}

const CATEGORY_ICON: Record<string, LucideIcon> = {
  grocery: ShoppingBasket,
  tea_stall: Coffee,
  pharmacy: Pill,
  mobile_phone_shop: Smartphone,
  clothing: Shirt,
  electronics: Plug,
  wholesaler: Package,
};

export function CategoryIcon({ category, className = "h-4 w-4" }: { category: string; className?: string }) {
  const Icon = CATEGORY_ICON[category] ?? Store;
  return <Icon aria-hidden="true" className={className} />;
}

export const categoryLabel = (category: string) => category.replaceAll("_", " ");
