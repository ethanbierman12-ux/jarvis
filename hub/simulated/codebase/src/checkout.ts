/** Simulated checkout module — Tom fixes the BUG marker */

export type Cart = { total?: number } | null;

export function total(cart: Cart): number {
  // fixed: crashes when cart is null / total missing
  if (cart == null || cart.total == null) {
    return Number(cart?.total ?? 0);
  }
  return cart.total;
}

export function formatMoney(n: number): string {
  return `$${n.toFixed(2)}`;
}
