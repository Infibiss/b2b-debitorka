import { locale, t } from './i18n';
export type User = {
  id: string;
  name: string;
  company: string;
  email: string;
  role?: 'manager' | 'accountant';
};
export type Session = { user: User; csrf_token: string };
export type Invoice = {
  id: string;
  company: string;
  inn: string;
  email: string;
  number: string;
  issued_on: string;
  due_on: string;
  amount: number;
  paid_amount: number;
  balance: number;
  days_overdue: number;
  status: 'open' | 'promised' | 'disputed' | 'paid' | 'paused';
  priority: 'high' | 'medium' | 'low';
  priority_reasons: string[];
  promise_date: string | null;
  notes: string;
};
export type Message = {
  id: string;
  invoice_id: string;
  subject: string;
  body: string;
  status: 'draft' | 'approved' | 'sent' | 'failed';
  recipient: string;
  source: string;
  created_at: string;
};
export type InvoiceEvent = {
  id: string;
  type: string;
  title: string;
  detail: string;
  created_at: string;
};
export type Payment = {
  id: string;
  amount: number;
  paid_on: string;
  reference: string;
  display_reference?: string;
  bank_payment_id?: string | null;
  reversed_amount?: number;
};
export type Detail = {
  invoice: Invoice;
  events: InvoiceEvent[];
  messages: Message[];
  payments: Payment[];
};
export type Overview = {
  total_outstanding: number;
  overdue_amount: number;
  collected_amount: number;
  bank_confirmed_amount: number;
  historical_paid_amount: number;
  manual_paid_amount: number;
  promised_amount: number;
  invoice_count: number;
  overdue_count: number;
  aging: { label: string; amount: number }[];
  weekly: { date: string; amount: number }[];
};
export type Settings = {
  company: string;
  sender_name: string;
  reply_to: string;
  bank_details: string;
  annual_rate: number;
  cooldown_days: number;
  smtp_configured: boolean;
  llm_configured: boolean;
};
let csrf = '';
export function setCsrf(token: string) {
  csrf = token;
}
export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}
export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`/api${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...(csrf ? { 'X-CSRF-Token': csrf } : {}),
      ...options.headers,
    },
    credentials: 'same-origin',
  });
  if (!response.ok) {
    let message = t('Не удалось выполнить действие. Попробуйте ещё раз.');
    try {
      const data = await response.json();
      message =
        typeof data.detail === 'string'
          ? data.detail
          : Array.isArray(data.detail)
            ? data.detail.map((x: { msg: string }) => x.msg).join('. ')
            : message;
    } catch {
      /* use readable fallback */
    }
    throw new ApiError(t(message), response.status);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}
export const post = <T>(path: string, body: unknown = {}) =>
  api<T>(path, { method: 'POST', body: JSON.stringify(body) });
export const patch = <T>(path: string, body: unknown) =>
  api<T>(path, { method: 'PATCH', body: JSON.stringify(body) });
export const put = <T>(path: string, body: unknown) =>
  api<T>(path, { method: 'PUT', body: JSON.stringify(body) });
export const del = <T>(path: string) => api<T>(path, { method: 'DELETE' });
export const money = (amount: number, compact = false) =>
  new Intl.NumberFormat(locale, {
    style: 'currency',
    currency: 'RUB',
    maximumFractionDigits: compact ? (amount >= 100000000 ? 1 : 0) : 2,
    minimumFractionDigits: 0,
    notation: compact && amount >= 100000000 ? 'compact' : 'standard',
  }).format(amount / 100);
export const dateText = (value: string) =>
  new Date(value.length === 10 ? `${value}T12:00:00` : value).toLocaleDateString(locale, {
    day: 'numeric',
    month: 'short',
  });
export const today = () => new Date().toLocaleDateString('en-CA', { timeZone: 'Europe/Moscow' });
export const toKopeks = (value: string) =>
  Math.round(Number(value.replace(/\s/g, '').replace(',', '.')) * 100);
