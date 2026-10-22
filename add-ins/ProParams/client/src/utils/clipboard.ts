import { hasAdsk } from '../connector/fusionBridge';

/** Copy text to the clipboard, stripping ProParams `{{ }}` delimiters. */
export async function copyToClipboard(text: string): Promise<boolean> {
  const cleaned = text.replace(/{{/g, '').replace(/}}/g, '');

  // The palette is a file:// Chromium view. It rejects the async Clipboard
  // API, and a textarea parked off-screen never reaches the OS clipboard.
  // The add-in writes the system clipboard directly.
  if (hasAdsk() && (await copyWithHost(cleaned))) return true;
  if (copyWithExecCommand(cleaned)) return true;

  try {
    if (navigator.clipboard && typeof navigator.clipboard.writeText === 'function') {
      await navigator.clipboard.writeText(cleaned);
      return true;
    }
  } catch {
    return false;
  }
  return false;
}

async function copyWithHost(text: string): Promise<boolean> {
  try {
    const raw = await Promise.resolve(
      window.adsk!.fusionSendData('clipboard:copy', JSON.stringify({ text }))
    );
    if (!raw) return false;
    const parsed: unknown = JSON.parse(raw);
    return typeof parsed === 'object' && parsed !== null && 'ok' in parsed && parsed.ok === true;
  } catch {
    return false;
  }
}

function copyWithExecCommand(text: string): boolean {
  const previous = document.activeElement;
  const selection =
    previous instanceof HTMLInputElement || previous instanceof HTMLTextAreaElement
      ? { start: previous.selectionStart, end: previous.selectionEnd }
      : null;
  // ParamTable watches focusout. This marks the temporary focus move so the
  // open editor does not save or clear while the copy is in progress.
  document.body.dataset.ppCopying = 'true';
  const area = document.createElement('textarea');
  area.id = 'pp_clipboard_sink';
  area.value = text;
  area.setAttribute('aria-hidden', 'true');
  // Keep the field in the viewport. Fusion's browser ignores a selection
  // parked at a large negative offset.
  area.style.position = 'fixed';
  area.style.top = '0';
  area.style.left = '0';
  area.style.width = '2em';
  area.style.height = '2em';
  area.style.padding = '0';
  area.style.border = 'none';
  area.style.outline = 'none';
  area.style.boxShadow = 'none';
  area.style.background = 'transparent';
  area.style.opacity = '0';
  document.body.appendChild(area);

  let ok = false;
  try {
    area.focus({ preventScroll: true });
    area.select();
    area.setSelectionRange(0, area.value.length);
    ok = document.execCommand('copy');
  } catch {
    ok = false;
  } finally {
    document.body.removeChild(area);
    if (previous instanceof HTMLElement && previous.isConnected) {
      previous.focus({ preventScroll: true });
      if (
        selection &&
        selection.start !== null &&
        selection.end !== null &&
        (previous instanceof HTMLInputElement || previous instanceof HTMLTextAreaElement)
      ) {
        previous.setSelectionRange(selection.start, selection.end);
      }
    }
    delete document.body.dataset.ppCopying;
  }
  return ok;
}
