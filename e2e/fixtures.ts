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

/** Use the same persistent commands and profile menu as the user. */
export async function navigate(page: import('@playwright/test').Page, name: string) {
  await expect(page.getByRole('navigation', { name: 'Разделы кабинета' })).toBeVisible();
  const labels: Record<string, string> = {
    Финансы: 'Оплаты и сверка',
    'Поступления и сверка': 'Оплаты и сверка',
    Реестр: 'Счета',
    Дела: 'Претензии и суд',
    'Юридическая работа': 'Претензии и суд',
    'Документы и голос': 'Документы',
    'Поступления и условия': 'Прогноз и условия',
    Письма: 'Переписка',
  };
  if (name === 'Настройки') {
    await page.getByRole('button', { name: 'Профиль и настройки', exact: true }).click();
    await page.getByRole('menuitem', { name: 'Настройки', exact: true }).click();
    return;
  }
  const menu = page.getByRole('button', { name: /^Операции ·/ });
  if ((await menu.isVisible()) && (await menu.getAttribute('aria-expanded')) === 'false')
    await menu.click();
  if (name === 'Агент' || name === 'Разбор ответов') {
    await page.getByRole('button', { name: 'Переписка', exact: true }).click();
    await page.getByRole('button', { name: 'Разобрать ответ', exact: true }).click();
    return;
  }
  await page.getByRole('button', { name: labels[name] || name, exact: true }).click();
  if (name === 'Документы и голос')
    await page.getByRole('button', { name: 'Распознавание', exact: true }).click();
}
