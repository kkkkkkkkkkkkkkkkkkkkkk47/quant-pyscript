import type { HealthStatus } from '../types';
import {
  LogoIcon,
  RefreshIcon,
  CheckCircleIcon,
  XCircleIcon,
} from './icons';
import { formatDateTime } from '../utils/formatters';

interface Props {
  health: HealthStatus | null;
  loading: boolean;
  autoRefresh: boolean;
  onToggleAutoRefresh: () => void;
  onRefresh: () => void;
}

export function Header({
  health,
  loading,
  autoRefresh,
  onToggleAutoRefresh,
  onRefresh,
}: Props) {
  return (
    <header className="sticky top-0 z-40 border-b border-gray-800 bg-[#0a0e1a]/90 backdrop-blur-md">
      <div className="max-w-screen-2xl mx-auto px-4 sm:px-6 h-16 flex items-center justify-between gap-4">
        {/* Logo + Title */}
        <div className="flex items-center gap-3 flex-shrink-0">
          <LogoIcon size={32} />
          <div>
            <h1 className="text-lg font-bold text-white leading-none">Basilica III</h1>
            <p className="text-xs text-gray-500 leading-none mt-0.5">Live Market Intelligence</p>
          </div>
        </div>

        {/* Health + Meta */}
        <div className="flex items-center gap-4 flex-wrap justify-end">
          {/* Health pill */}
          {health && (
            <div
              className={`flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-medium border ${
                health.status === 'ok'
                  ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-400'
                  : 'bg-red-500/10 border-red-500/30 text-red-400'
              }`}
            >
              {health.status === 'ok' ? (
                <CheckCircleIcon size={12} />
              ) : (
                <XCircleIcon size={12} />
              )}
              {health.status === 'ok' ? 'System OK' : 'Degraded'}
            </div>
          )}

          {/* Last cycle */}
          {health?.last_successful_cycle_at && (
            <div className="hidden sm:flex flex-col items-end">
              <span className="text-xs text-gray-500">Last cycle</span>
              <span className="text-xs text-gray-300 font-mono">
                {formatDateTime(health.last_successful_cycle_at)}
              </span>
            </div>
          )}

          {/* Securities count */}
          {health && (
            <div className="hidden md:flex flex-col items-end">
              <span className="text-xs text-gray-500">Rated</span>
              <span className="text-xs text-gray-300 font-semibold">
                {health.securities_rated} securities
              </span>
            </div>
          )}

          {/* Auto-refresh toggle */}
          <button
            onClick={onToggleAutoRefresh}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium border transition-all duration-200 ${
              autoRefresh
                ? 'bg-emerald-500/10 border-emerald-500/40 text-emerald-400 hover:bg-emerald-500/20'
                : 'bg-gray-800 border-gray-700 text-gray-400 hover:bg-gray-700'
            }`}
          >
            <RefreshIcon
              size={12}
              className={loading && autoRefresh ? 'animate-spin' : ''}
            />
            {autoRefresh ? 'Auto 30s' : 'Auto Off'}
          </button>

          {/* Manual refresh */}
          <button
            onClick={onRefresh}
            disabled={loading}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-gray-800 border border-gray-700 text-gray-300 hover:bg-gray-700 hover:text-white transition-all duration-200 disabled:opacity-50"
          >
            <RefreshIcon size={12} className={loading ? 'animate-spin' : ''} />
            Refresh
          </button>
        </div>
      </div>
    </header>
  );
}
