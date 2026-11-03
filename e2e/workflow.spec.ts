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
  await expect(page.getByRole('complementary', { name: 'Обучение: Mandato' })).toBeVisible();
  await page.getByRole('button', { name: 'Далее', exact: true }).click();
  await expect(page.getByText('Аудит — что мешает оплате', { exact: true })).toBeVisible();
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

test('a confirmed contract shows its fixed number and cannot silently remove linked invoices', async ({
  page,
}, info) => {
  const session = await account(page, `contract-ui-${info.project.name}`);
  const headers = { 'X-CSRF-Token': session.csrf_token };
  for (const number of ['CON-1', 'CON-2', 'CON-3']) {
    const result = await page.request.post('/api/invoices', {
      headers,
      data: {
        company: 'Покупатель договора',
        inn: '9900000000',
        number,
        issued_on: '2026-10-01',
        due_on: '2026-10-15',
        amount: 100000,
      },
    });
    expect(result.status()).toBe(201);
  }
  await page.reload();
  await page
    .getByRole('button', { name: 'Открыть дело Покупатель договора', exact: true })
    .first()
    .click();
  const dialog = page.getByRole('dialog', { name: 'Карточка дела', exact: true });
  await dialog.getByRole('button', { name: 'Указать договор', exact: true }).click();
  await dialog.getByLabel('Номер договора', { exact: true }).fill('CON-2026');
  for (const checkbox of await dialog.getByRole('checkbox').all()) await checkbox.uncheck();
  await dialog.getByRole('checkbox', { name: /CON-1/ }).check();
  await dialog.getByRole('checkbox', { name: /CON-2/ }).check();
  await dialog.getByRole('button', { name: 'Сохранить договор', exact: true }).click();
  await expect(dialog.getByText('Договор CON-2026', { exact: true })).toBeVisible();
  await dialog.getByRole('button', { name: 'Счета договора', exact: true }).click();
  await expect(dialog.getByLabel('Номер договора', { exact: true })).toHaveAttribute(
    'readonly',
    ''
  );
  await expect(dialog.getByRole('checkbox', { name: /CON-1/ })).toBeChecked();
  await expect(dialog.getByRole('checkbox', { name: /CON-1/ })).toBeDisabled();
  await expect(dialog.getByRole('checkbox', { name: /CON-2/ })).toBeDisabled();
  await expect(dialog.getByRole('checkbox', { name: /CON-3/ })).toBeEnabled();
  await dialog.getByRole('checkbox', { name: /CON-3/ }).check();
  await dialog.getByRole('button', { name: 'Сохранить договор', exact: true }).click();
  await expect(
    dialog.getByRole('button', { name: 'Открыть счёт CON-1', exact: true })
  ).toBeVisible();
  await expect(
    dialog.getByRole('button', { name: 'Открыть счёт CON-2', exact: true })
  ).toBeVisible();
  await expect(
    dialog.getByRole('button', { name: 'Открыть счёт CON-3', exact: true })
  ).toBeVisible();
  let extraAssignments = 0;
  page.on('request', (request) => {
    if (request.method() === 'POST' && request.url().endsWith('/api/workflow/contracts'))
      extraAssignments++;
  });
  await dialog.getByRole('button', { name: 'Счета договора', exact: true }).click();
  await dialog.getByRole('button', { name: 'Сохранить договор', exact: true }).click();
  await expect(dialog.getByLabel('Номер договора', { exact: true })).toHaveCount(0);
  expect(extraAssignments).toBe(0);
});

test('management is readable, panels stack, and the compact header never overlaps', async ({page}, info) => {
  await account(page, `style-${info.project.name}`);
  await page.setViewportSize({width:1280,height:900});
  await page.getByRole('button',{name:'Управление',exact:true}).click();
  const panels=page.locator('.wf-management-grid > .wf-panel');
  await expect(panels).toHaveCount(2);
  const boxes=await panels.evaluateAll((els)=>els.map(el=>{const r=el.getBoundingClientRect();return {x:r.x,y:r.y,width:r.width,bottom:r.bottom}}));
  expect(boxes[1].y).toBeGreaterThan(boxes[0].bottom);
  expect(boxes[1].width).toBeCloseTo(boxes[0].width,0);
  const label=page.getByText('Выключены. Сначала проверьте канал и расписание.',{exact:true});
  expect(await label.evaluate(el=>parseFloat(getComputedStyle(el).fontSize))).toBeGreaterThanOrEqual(14);
  const help=await page.getByRole('button',{name:'Как работать в разделе',exact:true}).boundingBox();
  const ops=await page.getByRole('navigation',{name:'Операции с дебиторкой'}).boundingBox();
  const sync=await page.getByRole('button',{name:'Обновить данные',exact:true}).boundingBox();
  expect(help!.x+help!.width).toBeLessThanOrEqual(ops!.x);
  expect(ops!.x+ops!.width).toBeLessThanOrEqual(sync!.x);
  await page.getByRole('button',{name:'Прогноз и условия',exact:true}).click();
  await expect(page.locator('.ms-card').first()).toBeVisible();
  for(const color of await page.locator('.ms-card').evaluateAll(els=>els.map(el=>getComputedStyle(el).backgroundColor))) expect(color).toBe('rgb(255, 255, 255)');
});
