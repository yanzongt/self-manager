export const API_BASE = location.pathname.startsWith("/investment/")
  ? "/investment"
  : "";
export function createApi(getToken: () => string) {
  return async function api<T>(path: string, body?: unknown): Promise<T> {
    const response = await fetch(
      API_BASE + path,
      body === undefined
        ? {}
        : {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
              "X-Local-Token": getToken(),
            },
            body: JSON.stringify(body),
          },
    );
    const data = await response.json().catch(() => {
      throw Error("服务返回异常，请检查终端或刷新页面");
    });
    if (!response.ok)
      throw Error(data.error || `请求失败 (${response.status})`);
    return data as T;
  };
}
