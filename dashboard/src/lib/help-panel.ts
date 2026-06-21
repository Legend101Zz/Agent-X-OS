/**
 * Help-panel persistence — pure helpers behind the <HelpPanel> primitive.
 *
 * The "How this page works" panel remembers whether you collapsed it, per page,
 * in localStorage. The storage plumbing lives here (testable with an injected
 * Storage stub) so the component stays a thin view.
 */

const PREFIX = "agentx.help.";

/** localStorage key for a given panel id. */
export function helpPanelStorageKey(id: string): string {
  return `${PREFIX}${id}`;
}

/**
 * Read whether the panel is open. Panels default to OPEN the first time (so a
 * new user sees the explanation), and respect the saved choice afterwards.
 * Any storage error degrades to the default rather than throwing.
 */
export function readHelpPanelOpen(
  id: string,
  storage: Pick<Storage, "getItem"> | undefined,
  defaultOpen = true,
): boolean {
  if (!storage) return defaultOpen;
  try {
    const raw = storage.getItem(helpPanelStorageKey(id));
    if (raw === null) return defaultOpen;
    return raw === "1";
  } catch {
    return defaultOpen;
  }
}

/** Persist the open/closed choice. Swallows storage errors (private mode etc.). */
export function writeHelpPanelOpen(
  id: string,
  open: boolean,
  storage: Pick<Storage, "setItem"> | undefined,
): void {
  if (!storage) return;
  try {
    storage.setItem(helpPanelStorageKey(id), open ? "1" : "0");
  } catch {
    // storage unavailable; in-memory only
  }
}
