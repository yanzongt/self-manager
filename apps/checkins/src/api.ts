import type { Data } from "./model";

declare global {
  interface Window {
    CHECKINS_TOKEN: string | null;
  }
}

interface Snapshot {
  data: Data | null;
  revision: string | null;
}

async function request(
  method: "GET" | "POST",
  body?: unknown,
): Promise<Snapshot> {
  const response = await fetch("/api/checkins", {
    method,
    headers: {
      "X-PDCA-Token": window.CHECKINS_TOKEN || "",
      ...(body ? { "Content-Type": "application/json" } : {}),
    },
    body: body ? JSON.stringify(body) : undefined,
  });
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || "保存失败");
  return result as Snapshot;
}

export const loadCheckins = () => request("GET");
export const saveCheckins = (data: Data, revision: string | null) =>
  request("POST", { data, revision });
