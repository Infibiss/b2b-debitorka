import { test, expect } from './fixtures';

async function account(page: import('@playwright/test').Page, suffix: string) {
  const response = await page.request.post('/api/auth/register', {
    data: {
      name: 'Руководитель',
      company: 'Поставщик',
      email: `workflow-${suffix}-${Date.now()}@example.ru`,
      password: 'Mandato-workflow-2026!',
    },
  });
  expect(response.status()).toBe(201);
  const session = await response.json();
  await page.goto('/app');
  return session;
}

test('unified workspace offers optional learning, skip and replay without creating debts', async ({
  page,
}, info) => {
  await account(page, info.project.name);
  await expect(
    page.getByRole('heading', { name: 'Работа по дебиторке', exact: true })
  ).toBeVisible();
  await expect(page.getByText('Показать, как устроена работа?', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Позже', exact: true }).click();
  await expect(page.getByText('Показать, как устроена работа?', { exact: true })).toHaveCount(0);
  await page.getByRole('button', { name: 'Обучение', exact: true }).click();
  await expect(page.getByRole('complementary', { name: 'Обучение: Работа' })).toBeVisible();
  await page.getByRole('button', { name: 'Далее', exact: true }).click();
  await expect(page.getByText('Откройте дело', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Закрыть обучение', exact: true }).click();
  expect((await (await page.request.get('/api/invoices')).json()).items).toHaveLength(0);
  await page.reload();
  await expect(page.getByText('Показать, как устроена работа?', { exact: true })).toHaveCount(0);
  await expect(page.locator('.workspace-nav > button')).toHaveCount(4);
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth > window.innerWidth + 2
  );
  expect(overflow).toBe(false);
  await page.screenshot({ path: info.outputPath('workflow-empty.png'), fullPage: true });
});

test('grouped case opens invoice work in context and policy has explicit enablement', async ({
  page,
}, info) => {
  const session = await account(page, `case-${info.project.name}`);
  const headers = { 'X-CSRF-Token': session.csrf_token };
  const response = await page.request.post('/api/invoices', {
    headers,
    data: {
      company: 'ООО Покупатель',
      inn: '7701234567',
      number: 'WF-42',
      issued_on: '2026-01-10',
      due_on: '2026-02-10',
      amount: 250000,
    },
  });
  expect(response.status()).toBe(201);
  await page.reload();
  await page.getByRole('button', { name: /Открыть дело.*Покупатель/ }).click();
  const drawer = page.getByRole('dialog', { name: 'Карточка дела' });
  await expect(drawer).toBeVisible();
  await expect(drawer.getByText('WF-42', { exact: true })).toBeVisible();
  await drawer.getByRole('button', { name: /Открыть счёт WF-42/ }).click();
  await expect(page.getByRole('dialog', { name: 'Карточка счёта' })).toBeVisible();
  await page.getByRole('button', { name: 'Закрыть карточку', exact: true }).click();
  await page.getByRole('button', { name: 'Управление', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Правила и команда', exact: true })).toBeVisible();
  await expect(page.getByLabel('Автоматические напоминания', { exact: true })).not.toBeChecked();
  await expect(page.getByRole('region', { name: 'Входящая почта', exact: true })).toContainText(
    'Входящая почта не настроена'
  );
  await page.screenshot({ path: info.outputPath('workflow-policy.png'), fullPage: true });
});

test('accountant invitation joins the same organization and cannot enable policy', async ({
  page,
}, info) => {
  const session = await account(page, `invite-${info.project.name}`);
  const invite = await page.request.post('/api/workflow/invitations', {
    headers: { 'X-CSRF-Token': session.csrf_token },
    data: { email: `bookkeeper-${info.project.name}-${Date.now()}@example.ru` },
  });
  expect(invite.status()).toBe(201);
  const { token } = await invite.json();
  await page.request.post('/api/auth/logout', { headers: { 'X-CSRF-Token': session.csrf_token } });
  await page.goto(`/app#invite=${token}`);
  await expect(
    page.getByRole('heading', { name: 'Присоединиться к команде', exact: true })
  ).toBeVisible();
  await page.getByLabel('Ваше имя', { exact: true }).fill('Бухгалтер');
  await page.getByLabel('Пароль', { exact: true }).fill('Mandato-Accountant-2026!');
  await page.getByRole('button', { name: 'Присоединиться', exact: true }).click();
  await expect(
    page.getByRole('heading', { name: 'Работа по дебиторке', exact: true })
  ).toBeVisible();
  await expect(page.locator('.user-block')).toContainText('Бухгалтер');
  await page.getByRole('button', { name: 'Управление', exact: true }).click();
  await expect(page.getByLabel('Автоматические напоминания', { exact: true })).toBeDisabled();
});
