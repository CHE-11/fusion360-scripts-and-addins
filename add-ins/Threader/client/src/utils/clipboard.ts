import { hasAdsk } from '../connector/fusionBridge';

/** Copy text to the clipboard. Fusion's palette cannot do this itself. */
export async function copyToClipboard(text: string): Promise<boolean> {
  if (hasAdsk() && (await copyWithHost(text))) return true;
  if (copyWithExecCommand(text)) return true;

  try {
    if (navigator.clipboard && typeof navigator.clipboard.writeText === 'function') {
      await navigator.clipboard.writeText(text);
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
  const area = document.createElement('textarea');
  area.id = 'th_clipboard_sink';
  area.value = text;
  area.setAttribute('aria-hidden', 'true');
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
  }
  return ok;
}
