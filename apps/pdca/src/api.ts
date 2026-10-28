import type { Database } from './types'
declare global {
  interface Window {
    PDCA_NATIVE_TOKEN: string | null
    webkitAudioContext?: typeof AudioContext
  }
}
export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message)
  }
}
export async function request<T>(
  path: string,
  body?: unknown,
  timeout = 12000,
): Promise<T> {
  const response = await fetch(path, {
    method: body === undefined ? 'GET' : 'POST',
    headers: {
      'X-PDCA-Token': window.PDCA_NATIVE_TOKEN || '',
      ...(body !== undefined ? { 'Content-Type': 'application/json' } : {}),
    },
    body: body === undefined ? undefined : JSON.stringify(body),
    signal: AbortSignal.timeout(timeout),
  })
  const value = await response.json()
  if (!response.ok)
    throw new ApiError(value.error || '本地服务请求失败', response.status)
  return value as T
}
export interface Snapshot {
  data: unknown
  revision: string | null
}
export const readData = () => request<Snapshot>('/api/data')
export const writeData = (data: Database, revision: string | null) =>
  request<{ revision: string }>('/api/data', { data, revision })
