import { test, expect, type Page } from './fixtures';
async function signup(page: Page, suffix: string) {
  await page.getByLabel('Ваше имя', { exact: true }).fill('Анна');
  await page.getByLabel('Компания', { exact: true }).fill('ООО Практика');
  await page
    .getByLabel('Рабочая почта', { exact: true })
    .fill(`commercial-${suffix}-${Date.now()}@example.ru`);
  await page.getByLabel('Пароль', { exact: true }).fill('Mandato-commercial-2026!');
  await page.getByRole('checkbox').check();
  await page.getByRole('button', { name: 'Создать аккаунт и продолжить' }).click();
}
test('demo and custom forms persist an acknowledged request without purchasing', async ({
  page,
}) => {
  for (const kind of ['demo', 'custom']) {
    await page.goto(kind === 'custom' ? '/demo?kind=custom' : '/demo');
    await page.getByLabel('Ваше имя', { exact: true }).fill('Анна');
    await page.getByLabel('Рабочая почта', { exact: true }).fill('demo@mandato.invalid');
    await page.getByRole('checkbox').check();
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
  await page.getByRole('checkbox').check();
  await page.getByRole('button', { name: 'Начать бесплатный период', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Можно начинать работу' })).toBeVisible();
  await page.reload();
  await expect(page.getByRole('heading', { name: 'Можно начинать работу' })).toBeVisible();
  await page.getByRole('link', { name: 'Перейти в кабинет' }).click();
  await expect(page.getByRole('button', { name: 'Работа', exact: true })).toBeVisible();
});
test('all paid tiers retain a pending order, explicitly bypass payment and support account cancellation', async ({
  page,
}, info) => {
  for (const [i, plan] of ['start', 'team', 'scale'].entries()) {
    await page.goto(`/start?plan=${plan}`);
    if (i === 0) await signup(page, `paid-${info.project.name}`);
    await expect(page.getByRole('heading', { name: /Подключить «/ })).toBeVisible();
    await page.getByRole('checkbox').check();
    await page.getByRole('button', { name: 'Продолжить оформление' }).click();
    await expect(page.getByRole('heading', { name: 'Подтвердите подключение' })).toBeVisible();
    const order = new URL(page.url()).searchParams.get('order');
    expect(order).toBeTruthy();
    await page.reload();
    await expect(page.getByRole('heading', { name: 'Подтвердите подключение' })).toBeVisible();
    await expect(page.locator('input[autocomplete="cc-number"]')).toHaveCount(0);
    await page.getByRole('button', { name: 'Продолжить без оплаты' }).click();
    await expect(page.getByRole('heading', { name: 'Можно начинать работу' })).toBeVisible();
    await page.goto('/account');
    await expect(page.getByText('Открыт без оплаты', { exact: true })).toBeVisible();
    await page.getByRole('button', { name: 'Отменить подписку или пробный период' }).click();
    await page.getByRole('button', { name: 'Подтвердить отмену' }).click();
    await expect(page.getByText('Отменён', { exact: true })).toBeVisible();
  }
  await page.getByRole('button', { name: 'Запросить удаление данных' }).click();
  await page.getByLabel('Введите УДАЛИТЬ').fill('УДАЛИТЬ');
  await page.getByRole('checkbox').check();
  await page.getByRole('button', { name: 'Отправить запрос', exact: true }).click();
  await expect(
    page.getByText('Запрос на удаление зарегистрирован.', { exact: false })
  ).toBeVisible();
});
