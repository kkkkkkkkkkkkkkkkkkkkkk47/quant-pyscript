interface Props {
  message?: string;
}

export function EmptyState({ message = 'No ratings available' }: Props) {
  return (
    <div className="flex flex-col items-center justify-center py-24 text-gray-500">
      <svg
        width="80"
        height="80"
        viewBox="0 0 80 80"
        fill="none"
        className="mb-6 opacity-30"
      >
        <rect x="10" y="50" width="12" height="20" rx="2" fill="#6b7280" />
        <rect x="28" y="35" width="12" height="35" rx="2" fill="#6b7280" />
        <rect x="46" y="20" width="12" height="50" rx="2" fill="#6b7280" />
        <rect x="64" y="10" width="12" height="60" rx="2" fill="#6b7280" />
        <line x1="8" y1="72" x2="78" y2="72" stroke="#6b7280" strokeWidth="2" />
        <circle cx="40" cy="20" r="12" stroke="#6b7280" strokeWidth="2" fill="none" />
        <line x1="35" y1="15" x2="45" y2="25" stroke="#6b7280" strokeWidth="2" />
        <line x1="45" y1="15" x2="35" y2="25" stroke="#6b7280" strokeWidth="2" />
      </svg>
      <p className="text-lg font-medium text-gray-400">{message}</p>
      <p className="text-sm text-gray-600 mt-1">
        Check that the backend is running at localhost:8000
      </p>
    </div>
  );
}
