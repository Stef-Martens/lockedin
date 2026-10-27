/** What today's form (fitness − fatigue) means, in a few words. */
export function formWords(form: number): string {
  if (form < -20) return "Very tired, ease off";
  if (form < -10) return "Building";
  if (form <= 5) return "Steady";
  return "Fresh";
}

/** Load numbers are averages: whole numbers read better, with an explicit + for positive form. */
export const loadNumber = (v: number) => String(Math.round(v));
export const formNumber = (v: number) => (Math.round(v) > 0 ? `+${Math.round(v)}` : loadNumber(v).replace("-", "−"));
