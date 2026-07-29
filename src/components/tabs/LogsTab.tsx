import { useEffect, useRef } from 'react';
import { t } from '../../i18n';

interface Props {
  logs: string[];
}

export default function LogsTab({ logs }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (containerRef.current) {
      containerRef.current.scrollTop = containerRef.current.scrollHeight;
    }
  }, [logs]);

  return (
    <div className="logs-container" ref={containerRef}>
      {logs.length === 0 ? t('logs.no_logs') : logs.join('\n')}
    </div>
  );
}
