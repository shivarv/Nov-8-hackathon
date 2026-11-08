/** Delivery slots and fees for the demo store (no real logistics behind them). */

export const FREE_DELIVERY_CENTS = 3500;
export const DELIVERY_FEE_CENTS = 399;
const DAYS = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];
const WINDOWS = [8, 10, 12, 14, 16, 18]; // two-hour windows starting at these hours

export interface Slot {
  key: string;
  day: string; // "Today", "Tomorrow", "Monday"
  label: string; // "2–4pm"
}

function hourLabel(h: number): string {
  const h12 = h % 12 || 12;
  return `${h12}${h < 12 ? "am" : "pm"}`;
}

/** A week of two-hour windows, from the next window that hasn't started. */
export function upcomingSlots(now = new Date()): Slot[] {
  const slots: Slot[] = [];
  for (let d = 0; d < 7; d++) {
    const date = new Date(now);
    date.setDate(now.getDate() + d);
    const day = d === 0 ? "Today" : d === 1 ? "Tomorrow" : DAYS[date.getDay()];
    for (const h of WINDOWS) {
      if (d === 0 && h <= now.getHours() + 1) continue;
      slots.push({ key: `${d}-${h}`, day, label: `${hourLabel(h)}–${hourLabel(h + 2)}` });
    }
  }
  return slots;
}

/** The first upcoming slot on the shopper's usual weekday and closest to their usual hour. */
export function usualSlot(slots: Slot[], usualDay: string, usualHour: number, now = new Date()): Slot {
  const target = Math.max(DAYS.indexOf(usualDay), 0);
  usualHour = usualHour ?? 12; // shoppers saved before the field existed
  const ahead = (target - now.getDay() + 7) % 7;
  const window = WINDOWS.reduce((a, b) => (Math.abs(b + 1 - usualHour) < Math.abs(a + 1 - usualHour) ? b : a));
  return slots.find((s) => s.key === `${ahead}-${window}`) ?? slots.find((s) => s.key.startsWith(`${ahead}-`)) ?? slots[0];
}
