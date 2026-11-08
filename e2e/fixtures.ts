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

/** Reach a section the way a user does: main menu or settings tabs. */
const settingsSections: Record<string, string> = {
  Подключения: 'Подключения',
  Управление: 'Команда',
  Настройки: 'Почта',
};
const aliases: Record<string, string> = {
  Финансы: 'Оплаты',
  'Поступления и сверка': 'Оплаты',
  'Оплаты и сверка': 'Оплаты',
  Агент: 'Ответы должников',
  'Разбор ответов': 'Ответы должников',
};

export async function navigate(page: import('@playwright/test').Page, name: string) {
  const main = page.getByRole('navigation', { name: 'Разделы кабинета' });
  await expect(main).toBeVisible();
  const target = aliases[name] || name;
  if (settingsSections[target]) {
    await main.getByRole('button', { name: 'Настройки', exact: true }).click();
    await page.getByRole('button', { name: settingsSections[target], exact: true }).click();
    return;
  }
  await main.getByRole('button', { name: target, exact: true }).click();
}
