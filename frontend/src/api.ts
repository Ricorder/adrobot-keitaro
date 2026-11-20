import type {
  CampaignQuery,
  CampaignView,
  CreateCampaignPayload,
  MetaView,
  OfferOption,
  OfferRowView,
  PushResult,
  SyncStats
} from './api.types';

const API_BASE = '/api';

export class ApiError extends Error {
  readonly status: number;
  readonly detail: string;

  constructor(status: number, detail: string) {
    super(detail);
    this.name = 'ApiError';
    this.status = status;
    this.detail = detail;
  }
}

export function isApiError(error: unknown): error is ApiError {
  return error instanceof ApiError;
}

export function errorText(error: unknown): string {
  if (error instanceof ApiError) return error.detail;
  if (error instanceof Error) return error.message;
  return String(error);
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null;
}

function formatValidationItem(item: unknown): string {
  if (!isRecord(item)) return typeof item === 'string' ? item : '';
  const message = typeof item.msg === 'string' ? item.msg : '';
  const path = Array.isArray(item.loc) ? item.loc.map(String).filter((part) => part !== 'body') : [];
  const field = path.join('.');
  if (field && message) return `${field}: ${message}`;
  return field || message;
}

function detailFrom(payload: unknown, status: number): string {
  if (isRecord(payload) && 'detail' in payload) {
    const detail = payload.detail;
    if (typeof detail === 'string' && detail.length > 0) return detail;
    if (Array.isArray(detail)) {
      const parts = detail.map(formatValidationItem).filter((part) => part.length > 0);
      if (parts.length > 0) return parts.join('; ');
    }
  }
  // backend всегда отдаёт detail; пустой ответ значит что-то пошло не так до приложения
  return `backend вернул ${status}`;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, init);
  } catch {
    throw new ApiError(0, 'backend недоступен: проверьте, что FastAPI запущен на 127.0.0.1:8000');
  }

  if (response.status === 204) return undefined as T;

  const payload: unknown = await response.json().catch(() => null);
  if (!response.ok) throw new ApiError(response.status, detailFrom(payload, response.status));
  return payload as T;
}

function jsonInit(method: 'POST' | 'PUT', body: unknown, headers?: HeadersInit): RequestInit {
  return {
    method,
    headers: { 'Content-Type': 'application/json', ...headers },
    body: JSON.stringify(body)
  };
}

function queryString(params: CampaignQuery | { q?: string }): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null) continue;
    search.set(key, String(value));
  }
  const line = search.toString();
  return line.length > 0 ? `?${line}` : '';
}

export function fetchMeta(): Promise<MetaView> {
  return request<MetaView>('/meta');
}

export function runSync(): Promise<SyncStats> {
  return request<SyncStats>('/sync', { method: 'POST' });
}

export function listCampaigns(params: CampaignQuery = {}): Promise<CampaignView[]> {
  return request<CampaignView[]>(`/campaigns${queryString(params)}`);
}

export function fetchCampaign(campaignId: number): Promise<CampaignView> {
  return request<CampaignView>(`/campaigns/${campaignId}`);
}

export function createCampaign(
  payload: CreateCampaignPayload,
  idempotencyKey?: string
): Promise<CampaignView> {
  const headers = idempotencyKey ? { 'Idempotency-Key': idempotencyKey } : undefined;
  return request<CampaignView>('/campaigns', jsonInit('POST', payload, headers));
}

export function searchOffers(q?: string): Promise<OfferOption[]> {
  return request<OfferOption[]>(`/offers${queryString({ q })}`);
}

export function addStreamOffer(streamId: number, offerId: number): Promise<OfferRowView[]> {
  return request<OfferRowView[]>(`/streams/${streamId}/offers`, jsonInit('POST', { offer_id: offerId }));
}

export function removeOfferRow(rowId: number): Promise<void> {
  return request<void>(`/streams/offers/${rowId}`, { method: 'DELETE' });
}

export function restoreOfferRow(rowId: number): Promise<void> {
  return request<void>(`/streams/offers/${rowId}/restore`, { method: 'POST' });
}

export function pinOfferRow(rowId: number, share: number | null): Promise<void> {
  return request<void>(`/streams/offers/${rowId}/pin`, jsonInit('PUT', { share }));
}

export function pushStream(streamId: number): Promise<PushResult> {
  return request<PushResult>(`/streams/${streamId}/push`, { method: 'POST' });
}
