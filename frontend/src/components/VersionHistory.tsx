import type { ArtifactVersion } from "../types";

interface Props {
  versions: ArtifactVersion[];
  fromVersion: number;
  toVersion: number;
  onFromVersionChange: (version: number) => void;
  onToVersionChange: (version: number) => void;
}

export function VersionHistory({
  versions,
  fromVersion,
  toVersion,
  onFromVersionChange,
  onToVersionChange,
}: Props) {
  if (versions.length === 0) return null;

  const label = (version: ArtifactVersion) =>
    `v${version.version}${version.version === 1 ? " (原始)" : " (重新生成)"}`;

  return (
    <div className="flex flex-wrap items-center gap-2 text-xs">
      <label className="flex items-center gap-1 text-slate-600">
        起点
        <select
          value={fromVersion}
          onChange={(event) => onFromVersionChange(Number(event.target.value))}
          className="rounded-md border border-slate-200 bg-white px-2 py-1 text-xs text-slate-700 focus:outline-none focus:ring-2 focus:ring-blue-500"
        >
          {versions.map((version) => (
            <option key={version.id} value={version.version}>{label(version)}</option>
          ))}
        </select>
      </label>
      <label className="flex items-center gap-1 text-slate-600">
        目标
        <select
          value={toVersion}
          onChange={(event) => onToVersionChange(Number(event.target.value))}
          className="rounded-md border border-slate-200 bg-white px-2 py-1 text-xs text-slate-700 focus:outline-none focus:ring-2 focus:ring-blue-500"
        >
          {versions.map((version) => (
            <option key={version.id} value={version.version}>{label(version)}</option>
          ))}
        </select>
      </label>
    </div>
  );
}
