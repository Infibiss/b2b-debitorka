import { test, expect, navigate, type Page } from './fixtures';
async function signup(page: Page, suffix: string) {
  await page.getByLabel('Ваше имя', { exact: true }).fill('Анна');
  await page.getByLabel('Компания', { exact: true }).fill('ООО Практика');
  await page
    .getByLabel('Рабочая почта', { exact: true })
    .fill(`commercial-${suffix}-${Date.now()}@example.ru`);
  await page.getByLabel('Пароль', { exact: true }).fill('Mandato-commercial-2026!');
  for (const box of await page.getByRole('checkbox').all()) await box.check();
  await page.getByRole('button', { name: 'Создать аккаунт и продолжить' }).click();
}
test('demo and custom forms persist an acknowledged request without purchasing', async ({
  page,
}) => {
  for (const kind of ['demo', 'custom']) {
    await page.goto(kind === 'custom' ? '/demo?kind=custom' : '/demo');
    await page.getByLabel('Ваше имя', { exact: true }).fill('Анна');
    await page.getByLabel('Рабочая почта', { exact: true }).fill('demo@mandato.invalid');
    for (const box of await page.getByRole('checkbox').all()) await box.check();
    await page.getByRole('button', { name: 'Отправить заявку' }).click();
    await expect(page.getByRole('heading', { name: 'Заявка принята' })).toBeVisible();
    await expect(page.getByText('Номер заявки:', { exact: false })).toBeVisible();
    await expect(page.getByRole('link', { name: 'Попробовать самостоятельно' })).toHaveAttribute(
      'href',
      '/start?plan=trial'
    );
  }
});
test('free trial survives signup and reload and leads into the workspace', async ({
  page,
}, info) => {
  await page.goto('/start?plan=trial');
  await signup(page, info.project.name);
  await expect(page.getByRole('heading', { name: '14 дней бесплатно', exact: true })).toBeVisible();
  for (const box of await page.getByRole('checkbox').all()) await box.check();
  await page.getByRole('button', { name: 'Начать бесплатный период', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Можно начинать работу' })).toBeVisible();
  await page.reload();
  await expect(page.getByRole('heading', { name: 'Можно начинать работу' })).toBeVisible();
  await page.getByRole('link', { name: 'Перейти в кабинет' }).click();
  await expect(page.getByRole('heading', { name: 'Главная' })).toBeVisible();
});
test('all paid tiers retain a pending order, explicitly bypass payment and support account cancellation', async ({
  page,
}, info) => {
  for (const [i, plan] of ['start', 'team', 'scale'].entries()) {
    await page.goto(`/start?plan=${plan}`);
    if (i === 0) await signup(page, `paid-${info.project.name}`);
    await expect(page.getByRole('heading', { name: /Подключить «/ })).toBeVisible();
    for (const box of await page.getByRole('checkbox').all()) await box.check();
    await page.getByRole('button', { name: 'Продолжить оформление' }).click();
    await expect(page.getByRole('heading', { name: 'Подтвердите подключение' })).toBeVisible();
    const order = new URL(page.url()).searchParams.get('order');
    expect(order).toBeTruthy();
    await page.reload();
    await expect(page.getByRole('heading', { name: 'Подтвердите подключение' })).toBeVisible();
    await expect(page.locator('input[autocomplete="cc-number"]')).toHaveCount(0);
    await page.getByRole('button', { name: 'Подключить и получить счёт' }).click();
    await expect(page.getByRole('heading', { name: 'Можно начинать работу' })).toBeVisible();
    await page.goto('/account');
    await expect(page.getByText('Подключён', { exact: true })).toBeVisible();
    await page.getByRole('button', { name: 'Отменить подписку или пробный период' }).click();
    await page.getByRole('button', { name: 'Подтвердить отмену' }).click();
    await expect(page.getByText('Отменён', { exact: true })).toBeVisible();
  }
  await expect(page.getByRole('button', { name: 'Запросить удаление данных' })).toHaveCount(0, {
    timeout: 1500,
  });
  await page.getByRole('link', { name: 'Управлять данными в настройках' }).click();
  await expect(page).toHaveURL('/app?mode=login&section=settings&settingsTab=mail#workspace-data');
  const data = page.getByRole('region', { name: 'Данные организации' });
  await expect(data).toBeVisible();
  await expect(page.getByRole('navigation', { name: 'Разделы кабинета' })).toBeVisible();
  await expect(data).toContainText('вручную');
  await data.getByRole('button', { name: 'Запросить удаление данных' }).click();
  await expect(data.getByRole('checkbox')).not.toBeChecked();
  await expect(data.getByRole('button', { name: 'Отправить запрос', exact: true })).toBeDisabled();
  await data.getByLabel('Введите УДАЛИТЬ').fill('УДАЛИТЬ');
  await data.getByRole('checkbox').check();
  await data.getByRole('button', { name: 'Отправить запрос', exact: true }).click();
  await expect(
    page.getByText('Запрос на удаление зарегистрирован.', { exact: false })
  ).toBeVisible();
  await page.reload();
  await expect(
    page.getByRole('region', { name: 'Данные организации' }).getByRole('status')
  ).toContainText('Номер запроса:');
  await expect(page.getByRole('button', { name: 'Запросить удаление данных' })).toHaveCount(0);
  await navigate(page, 'Должники');
  await expect(page.getByRole('heading', { name: 'Должники', exact: true })).toBeVisible();
});

test('data request page leads to workspace settings', async ({ page }) => {
  await page.goto('/data-request');
  await expect(page.getByRole('link', { name: 'Открыть настройки данных' })).toHaveAttribute(
    'href',
    '/app?mode=login&section=settings&settingsTab=mail#workspace-data'
  );
  await page.getByRole('link', { name: 'Открыть настройки данных' }).click();
  await expect(page.getByRole('heading', { name: 'Войти в Mandato', exact: true })).toBeVisible();
});

test('accountant sees data settings without permission to request deletion', async ({
  page,
}, info) => {
  const stamp = `${info.project.name}-${Date.now()}`;
  const registration = await page.request.post('/api/auth/register', {
    data: {
      name: 'Анна',
      company: 'ООО Практика',
      email: `data-manager-${stamp}@example.ru`,
      password: 'Mandato-commercial-2026!',
    },
  });
  expect(registration.status()).toBe(201);
  const manager = await registration.json();
  const email = `data-accountant-${stamp}@example.ru`;
  const invitation = await page.request.post('/api/workflow/invitations', {
    headers: { 'X-CSRF-Token': manager.csrf_token },
    data: { email },
  });
  expect(invitation.status()).toBe(201);
  const { token } = await invitation.json();
  await page.request.post('/api/auth/logout', { headers: { 'X-CSRF-Token': manager.csrf_token } });
  const accepted = await page.request.post('/api/workflow/invitations/accept', {
    data: { token, name: 'Бухгалтер', password: 'Mandato-commercial-2026!' },
  });
  expect(accepted.status()).toBe(201);
  const login = await page.request.post('/api/auth/login', {
    data: { email, password: 'Mandato-commercial-2026!' },
  });
  expect(login.status()).toBe(200);
  await page.goto('/app?mode=login&section=settings&settingsTab=mail#workspace-data');
  const data = page.getByRole('region', { name: 'Данные организации' });
  await expect(data).toContainText('только администратор организации');
  await expect(data.getByRole('button', { name: 'Запросить удаление данных' })).toHaveCount(0);
  await expect(data.getByRole('form')).toHaveCount(0);
});
