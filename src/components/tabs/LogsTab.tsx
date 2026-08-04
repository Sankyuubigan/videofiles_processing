import { useEffect, useRef, useState } from 'react';
import { t } from '../../i18n';

interface Props {
  logs: string[];
  onClear: () => void;
}

export default function LogsTab({ logs, onClear }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [copied, setCopied] = useState(false);
  const stickToBottomRef = useRef(true);

  useEffect(() => {
    const el = containerRef.current;
    if (el && stickToBottomRef.current) {
      el.scrollTop = el.scrollHeight;
    }
  }, [logs]);

  const handleScroll = () => {
    const el = containerRef.current;
    if (!el) return;
    stickToBottomRef.current = el.scrollHeight - el.scrollTop - el.clientHeight < 50;
  };

  const handleCopy = async () => {
    if (logs.length === 0) return;
    try {
      await navigator.clipboard.writeText(logs.join('\n'));
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      const el = containerRef.current;
      if (el) {
        const range = document.createRange();
        range.selectNodeContents(el);
        const sel = window.getSelection();
        sel?.removeAllRanges();
        sel?.addRange(range);
      }
    }
  };

  return (
    <div style={{ position: 'relative', height: '100%' }}>
      <div style={{ position: 'absolute', top: 6, right: 6, zIndex: 1, display: 'flex', gap: 6 }}>
        <button
          onClick={onClear}
          disabled={logs.length === 0}
          style={{
            padding: '4px 10px',
            fontSize: 12,
            borderRadius: 4,
            border: '1px solid #555',
            background: '#2d2d2d',
            color: '#d4d4d4',
            cursor: logs.length === 0 ? 'default' : 'pointer',
            opacity: logs.length === 0 ? 0.4 : 1,
          }}
        >
          {t('logs.clear')}
        </button>
        <button
          onClick={handleCopy}
          disabled={logs.length === 0}
          style={{
            padding: '4px 10px',
            fontSize: 12,
            borderRadius: 4,
            border: '1px solid #555',
            background: copied ? '#2a7d2a' : '#2d2d2d',
            color: '#d4d4d4',
            cursor: logs.length === 0 ? 'default' : 'pointer',
            opacity: logs.length === 0 ? 0.4 : 1,
          }}
        >
          {copied ? t('logs.copied') : t('logs.copy')}
        </button>
      </div>
      <div className="logs-container" ref={containerRef} onScroll={handleScroll}>
        {logs.length === 0 ? t('logs.no_logs') : logs.join('\n')}
      </div>
    </div>
  );
}
