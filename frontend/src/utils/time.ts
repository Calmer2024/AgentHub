const CHINA_TIME_ZONE = "Asia/Shanghai";
const TIMEZONE_SUFFIX_RE = /(Z|[+-]\d{2}:?\d{2})$/i;

export function parseChinaDateTime(value: string): Date {
  const normalized = value.includes("T") && !TIMEZONE_SUFFIX_RE.test(value)
    ? `${value}+08:00`
    : value;
  return new Date(normalized);
}

export function formatChinaDateTime(
  value: string,
  options: Intl.DateTimeFormatOptions = {},
): string {
  if (!value) return "";
  const date = parseChinaDateTime(value);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleString("zh-CN", {
    timeZone: CHINA_TIME_ZONE,
    ...options,
  });
}

export function formatChinaTime(
  value: string,
  options: Intl.DateTimeFormatOptions = {},
): string {
  if (!value) return "";
  const date = parseChinaDateTime(value);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleTimeString("zh-CN", {
    timeZone: CHINA_TIME_ZONE,
    ...options,
  });
}

export function chinaNowIso(): string {
  const parts = new Intl.DateTimeFormat("zh-CN", {
    timeZone: CHINA_TIME_ZONE,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  }).formatToParts(new Date());
  const value = (type: Intl.DateTimeFormatPartTypes) =>
    parts.find((part) => part.type === type)?.value ?? "00";
  const milliseconds = String(new Date().getMilliseconds()).padStart(3, "0");
  return `${value("year")}-${value("month")}-${value("day")}T${value("hour")}:${value("minute")}:${value("second")}.${milliseconds}+08:00`;
}
