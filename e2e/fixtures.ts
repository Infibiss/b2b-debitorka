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

/** Reach a section the way a user does: main menu, tools disclosure or settings tabs. */
const toolSections = [
  'Работа',
  'Аудит',
  'Счета',
  'Переписка',
  'Документы',
  'Прогноз и условия',
  'Претензии и суд',
  'Разбор ответов',
];
const settingsSections: Record<string, string> = {
  Подключения: 'Подключения',
  Управление: 'Команда',
  Настройки: 'Почта',
};
const aliases: Record<string, string> = {
  Финансы: 'Оплаты',
  'Поступления и сверка': 'Оплаты',
  'Оплаты и сверка': 'Оплаты',
  Реестр: 'Счета',
  Дела: 'Претензии и суд',
  'Юридическая работа': 'Претензии и суд',
  'Документы и голос': 'Документы',
  'Поступления и условия': 'Прогноз и условия',
  Письма: 'Переписка',
  Агент: 'Разбор ответов',
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
  if (toolSections.includes(target)) {
    const summary = page.getByText('Инструменты', { exact: true });
    const details = page.locator('details.workspace-more');
    if ((await details.getAttribute('open')) === null) await summary.click();
    await details.getByRole('button', { name: target, exact: true }).click();
    if (name === 'Документы и голос')
      await page.getByRole('button', { name: 'Распознавание', exact: true }).click();
    return;
  }
  await main.getByRole('button', { name: target, exact: true }).click();
}
