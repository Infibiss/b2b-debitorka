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
  const button = page.getByRole('button', { name, exact: true });
  if (!(await button.isVisible())) await page.getByText('Инструменты', { exact: true }).click();
  await button.click();
}
