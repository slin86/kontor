// Shared Tailwind class strings for form controls and buttons.
export const input =
  'mt-1 w-full border border-tinte/30 bg-white/60 px-3 py-2 text-base focus:border-elbe focus:bg-white'
export const primary = 'bg-tinte px-4 py-2 font-medium text-karte hover:bg-elbe-dunkel disabled:opacity-60'
export const secondary = 'px-3 py-2 text-sm font-medium text-elbe-dunkel hover:underline'

/** Parse a user-entered decimal such as "1.234,50" or "3,6" into a plain "3.6" style string. */
export function decimalString(raw: FormDataEntryValue | null): string {
  const text = String(raw ?? '').trim()
  // German input: dots are thousands separators only when a comma is present as well.
  const normalized = text.includes(',') ? text.replace(/\./g, '').replace(',', '.') : text
  return normalized
}
