import { useEffect, type RefObject } from "react";

/** Modal keyboard behaviour: focus the first control, close on Escape, keep Tab inside the dialog. */
export function useDialogKeys(dialog: RefObject<HTMLElement | null>, onClose: () => void) {
  useEffect(() => {
    const el = dialog.current;
    el?.querySelector<HTMLElement>("input:not([disabled]), button:not([disabled])")?.focus();
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
      if (e.key === "Tab" && el) {
        const focusable = Array.from(el.querySelectorAll<HTMLElement>("input, button, [tabindex]:not([tabindex='-1'])")).filter((f) => !f.hasAttribute("disabled"));
        if (!focusable.length) return;
        const first = focusable[0];
        const last = focusable[focusable.length - 1];
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault();
          last.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault();
          first.focus();
        }
      }
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [dialog, onClose]);
}
