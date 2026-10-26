import { navigate, test, expect, type Page } from './fixtures';

async function openConnections(page: Page) {
  const response = await page.request.post('/api/auth/register', {
    data: {
      name: 'Сотрудник',
      company: 'ООО Источники',
      email: `connections-${Date.now()}-${Math.random().toString(16).slice(2)}@example.ru`,
      password: 'Connections-testing-2026!',
    },
  });
  expect(response.status()).toBe(201);
  await page.route('**/api/integrations', (route) =>
    route.fulfill({
      json: {
        items: ['one_c', 'diadoc', 'tbank', 'dadata'].map((provider) => ({
          provider,
          configured: provider === 'one_c',
          status: provider === 'one_c' ? 'completed' : 'unconfigured',
          checked_at: provider === 'one_c' ? new Date().toISOString() : null,
          coverage: {},
        })),
      },
    })
  );
  await page.goto('/app');
  await navigate(page, 'Подключения');
}

test('source catalogue shows actual status and only the selected source tools', async ({
  page,
}) => {
  await openConnections(page);
  const catalogue = page.getByRole('group', { name: 'Источники', exact: true });
  await expect(catalogue.getByRole('button')).toHaveCount(5);
  await expect(catalogue.getByRole('button', { name: '1С', exact: true })).toContainText(
    'Данные получены'
  );
  await expect(catalogue.getByRole('button', { name: 'ЭДО', exact: true })).toContainText(
    'Не подключено'
  );
  await expect(
    catalogue.getByRole('button', { name: '1С', exact: true })
  ).toHaveAccessibleDescription('Счета и задолженность Данные получены');
  await expect(
    catalogue.getByRole('button', { name: 'ЭДО', exact: true })
  ).toHaveAccessibleDescription('Документы Диадока Не подключено');
  await expect(page.getByRole('region', { name: 'Источник: 1С', exact: true })).toBeVisible();
  await expect(page.getByLabel('Файл банковской выписки')).toHaveCount(0);
  await expect(page.getByLabel('Точный ИНН', { exact: true })).toHaveCount(0);
  await expect(page.getByRole('heading', { name: 'Проверка прочитанных данных' })).toHaveCount(0);

  await catalogue.getByRole('button', { name: 'Реестры', exact: true }).click();
  await expect(page.getByRole('region', { name: 'Источник: 1С', exact: true })).toHaveCount(0);
  await expect(page.getByLabel('Точный ИНН', { exact: true })).toBeVisible();
  await expect(
    page.getByRole('button', { name: 'Проверить должника', exact: true })
  ).toBeDisabled();
  await expect(page.getByRole('link', { name: 'Картотека арбитражных дел' })).toHaveAttribute(
    'href',
    'https://kad.arbitr.ru/'
  );
  await expect(page.getByRole('link', { name: 'ФССП', exact: true })).toBeVisible();
  await expect(page.getByRole('link', { name: 'ЕФРСБ', exact: true })).toBeVisible();
  await expect(page.getByLabel('Файл банковской выписки')).toHaveCount(0);
  expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1)).toBe(
    false
  );
});

test('IT instructions open on request and stay scoped to the selected source', async ({ page }) => {
  await openConnections(page);
  await expect(page.getByText('Что подготовить', { exact: true })).toHaveCount(0);
  await expect(page.getByText(/Опубликовать стандартный OData/)).toHaveCount(0);
  await page.getByText('Для IT-специалиста', { exact: true }).click();
  await expect(page.getByText('Что подготовить', { exact: true })).toBeVisible();
  await expect(page.getByText(/Опубликовать стандартный OData/)).toBeVisible();
  await expect(page.getByRole('button', { name: 'Скачать задание · TXT' })).toBeVisible();
  await expect(page.getByText(/Выпустить токен в Т-Бизнесе/)).toHaveCount(0);

  await page
    .getByRole('group', { name: 'Источники', exact: true })
    .getByRole('button', { name: 'ЭДО', exact: true })
    .click();
  await expect(page.getByText('Что подготовить', { exact: true })).toHaveCount(0);
  await page.getByText('Для IT-специалиста', { exact: true }).click();
  await expect(page.getByText(/Подтвердить действующий ящик вашей организации/)).toBeVisible();
  await expect(page.getByText(/Опубликовать стандартный OData/)).toHaveCount(0);
});

test('bank file import is contextual and public sandbox requires developer disclosure', async ({
  page,
}) => {
  await openConnections(page);
  await page
    .getByRole('group', { name: 'Источники', exact: true })
    .getByRole('button', { name: 'Банк', exact: true })
    .click();
  await expect(page.getByLabel('Файл банковской выписки')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Проверить выписку', exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Прочитать публичную песочницу' })).toHaveCount(0);
  await page.getByText('Для разработчика', { exact: true }).click();
  await expect(page.getByRole('button', { name: 'Прочитать публичную песочницу' })).toBeVisible();
  await page
    .getByRole('group', { name: 'Источники', exact: true })
    .getByRole('button', { name: '1С', exact: true })
    .click();
  await expect(page.getByLabel('Файл банковской выписки')).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Прочитать публичную песочницу' })).toHaveCount(0);
});
