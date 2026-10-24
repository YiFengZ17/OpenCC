import type { ModelPlazaGroup, PlazaModel } from '@/api/modelPlaza'
import type { UserPricingInterval } from '@/api/channels'
export function priceRate(group: ModelPlazaGroup, model: PlazaModel) {
  if (model.pricing?.billing_mode === 'image' && group.image_rate_independent)
    return group.image_rate_multiplier
  if (model.pricing?.billing_mode === 'video' && group.video_rate_independent)
    return group.video_rate_multiplier
  return group.user_rate_multiplier ?? group.rate_multiplier
}
// Temporary commercial policy: same numerical value, USD upstream → CNY points here.
export function pointPrice(
  value: number | null | undefined,
  rate: number,
  unit = 1_000_000
): number | null {
  return value == null || !Number.isFinite(value) || !Number.isFinite(rate)
    ? null
    : value * rate * unit
}
export function intervalPrice(
  base: number | null | undefined,
  tier: UserPricingInterval,
  field:
    | 'input_price'
    | 'output_price'
    | 'cache_read_price'
    | 'cache_write_price'
) {
  const multiplier = {
    input_price: tier.input_multiplier,
    output_price: tier.output_multiplier,
    cache_read_price: tier.cache_read_multiplier,
    cache_write_price: tier.cache_write_multiplier
  }[field]
  return tier[field] ?? (base == null ? null : base * (multiplier ?? 1))
}
