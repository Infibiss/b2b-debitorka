import { test as base, expect } from '@playwright/test';

// Each test models an independent client behind the local trusted test proxy.
// Keep production rate limits active without pooling 24 users into one IP bucket.
export const test = base.extend({
  extraHTTPHeaders: async ({ extraHTTPHeaders }, use, info) => {
    const ip = `198.18.${info.project.name === 'mobile' ? 2 : 1}.${info.testId.split('').reduce((value, char) => (value * 31 + char.charCodeAt(0)) % 250, 0) + 1}`;
    await use({ ...extraHTTPHeaders, 'X-Forwarded-For': ip });
  },
});
export { expect };

export type { Page } from '@playwright/test';

/** Exercise the compact navigation as a user would: open tools when needed. */
export async function navigate(page: import('@playwright/test').Page, name: string) {
  await expect(page.getByRole('navigation', { name: 'Разделы кабинета' })).toBeVisible();
  const labels: Record<string, string> = {
    Финансы: 'Поступления и сверка',
    Агент: 'Разбор ответов',
    Дела: 'Юридическая работа',
    'Поступления и условия': 'Прогноз и условия',
    Письма: 'Переписка',
  };
  const button = page.getByRole('button', { name: labels[name] || name, exact: true });
  if (!(await button.isVisible())) {
    if (name === 'Настройки') {
      await page.getByRole('button', { name: 'Управление', exact: true }).click();
      await page.getByRole('button', { name: 'Реквизиты и почта', exact: true }).click();
      return;
    }
    await page.getByRole('button', { name: 'Работа', exact: true }).click();
    await page.getByText('Операции с дебиторкой', { exact: true }).click();
  }
  await button.click();
}
