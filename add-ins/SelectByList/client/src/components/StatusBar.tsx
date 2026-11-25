export type StatusTone = 'ok' | 'warn' | 'error' | 'dim';

type StatusBarProps = {
  message: string;
  tone: StatusTone;
};

export function StatusBar({ message, tone }: StatusBarProps) {
  return (
    <div id="sbl-status-bar" className={`sbl-status sbl-status-${tone}`} role="status" aria-live="polite">
      <span id="sbl-status-text" className="sbl-statusText">
        {message}
      </span>
    </div>
  );
}
