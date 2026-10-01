"use client";

/** A row of radio buttons that reads as a segmented control. */
export function Segmented({ name, legend, options, defaultValue, hint }: {
  name: string;
  legend: string;
  options: readonly { value: string; label: string; lang?: string }[];
  defaultValue: string;
  hint?: string;
}) {
  return (
    <fieldset>
      <legend className="label">{legend}</legend>
      {hint && <p className="hint -mt-1 mb-2">{hint}</p>}
      <div className="grid auto-cols-fr grid-flow-col gap-1 rounded-lg bg-sunken p-1">
        {options.map((o) => (
          <label key={o.value} className="cursor-pointer" lang={o.lang}>
            <input type="radio" name={name} value={o.value} defaultChecked={o.value === defaultValue} className="peer sr-only" />
            <span className="block rounded-md px-3 py-2 text-center text-sm text-muted transition-colors peer-checked:bg-surface peer-checked:font-semibold peer-checked:text-ink peer-checked:shadow-[0_1px_2px_rgb(15_20_27/0.12)] peer-focus-visible:outline-2 peer-focus-visible:outline-accent hover:text-ink">
              {o.label}
            </span>
          </label>
        ))}
      </div>
    </fieldset>
  );
}

export const LANGUAGES = [
  { value: "el", label: "Ελληνικά", lang: "el" },
  { value: "en", label: "English", lang: "en" },
] as const;
