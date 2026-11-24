import { test, expect } from './fixtures';
test('home explains the stages and is readable without waiting for scripts', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.goto('/');
  await expect(page.getByRole('heading', { level: 1 })).toContainText('Долги');
  const stages = page.getByRole('region', { name: /Претензии|Суд|Взыскание/ });
  await expect(stages.getByRole('figure')).toContainText('Досудебная работа');
  await stages.getByRole('button', { name: 'Вперёд' }).click();
  await expect(stages.getByRole('figure')).toContainText('Пошлина');
  await expect(page.getByRole('contentinfo')).toContainText('ОГРНИП 326265100166493');
  await expect(page.getByRole('contentinfo')).not.toContainText('18+');
  await expect(page.getByRole('contentinfo')).not.toContainText('Муртазалиев');
});
test('public pages ship real html, meta tags and a sitemap', async ({ request }) => {
  const home = await (await request.get('/')).text();
  expect(home).toContain('<h1 id="hero-title">');
  expect(home).toContain('rel="canonical" href="https://mandato.ru/"');
  expect(home).toContain('application/ld+json');
  const product = await (await request.get('/product')).text();
  expect(product).toContain('Реестр должников'.slice(0, 6));
  expect(product).toContain('rel="canonical" href="https://mandato.ru/product"');
  expect(await (await request.get('/robots.txt')).text()).toContain(
    'Sitemap: https://mandato.ru/sitemap.xml'
  );
  expect(await (await request.get('/sitemap.xml')).text()).toContain(
    '<loc>https://mandato.ru/pricing</loc>'
  );
  expect(await (await request.get('/app')).text()).not.toContain('hero-title');
  expect((await request.get('/nope')).status()).toBe(404);
});
test('plan comparison shows pre-trial terms and court packages per plan', async ({ page }) => {
  await page.goto('/pricing');
  const table = page.getByRole('table', { name: 'Состав тарифов' });
  const pretrial = table.getByRole('row', { name: /Досудебная работа/ });
  await expect(pretrial).toContainText('7% от поступлений');
  await expect(pretrial).toContainText('Включено');
  const packages = table.getByRole('row', { name: /Судебные пакеты/ });
  await expect(packages).toContainText('2 в месяц');
  await expect(packages).toContainText('Без лимита');
  await expect(table.getByRole('row')).toHaveCount(9);
});

test('workspace screens can be explored with buttons and keyboard at every width', async ({
  page,
}) => {
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.goto('/');
  const carousel = page.getByRole('region', { name: 'Экраны кабинета' });
  await carousel.scrollIntoViewIfNeeded();
  await expect(carousel.getByRole('heading')).toHaveText('Должники и следующий шаг');
  const next = carousel.getByRole('button', { name: 'Посмотреть следующий экран' });
  await next.click();
  await expect(carousel.getByRole('heading')).toHaveText('Каждый договор — отдельное дело');
  await next.press('ArrowRight');
  await expect(carousel.getByRole('heading')).toHaveText('Главное о деньгах');
  await next.press('ArrowLeft');
  await expect(carousel.getByRole('heading')).toHaveText('Каждый договор — отдельное дело');
  await expect(carousel.getByRole('button')).toHaveCount(1);
  for (const width of [390, 768, 1024, 1440]) {
    await page.setViewportSize({ width, height: 1000 });
    await carousel.scrollIntoViewIfNeeded();
    const dimensions = [];
    for (let slide = 0; slide < 3; slide++) {
      await next.click();
      dimensions.push(
        await carousel.evaluate((root) => {
          const frame = root.querySelector('.is-active')!.getBoundingClientRect();
          const caption = root.querySelector('.product-carousel-bottom')!.getBoundingClientRect();
          return {
            width: frame.width,
            height: frame.height,
            caption: caption.height,
            total: root.getBoundingClientRect().height,
          };
        })
      );
    }
    for (const value of dimensions) {
      expect(value.width).toBeGreaterThan(width < 640 ? 250 : 450);
      for (const field of ['width', 'height', 'caption', 'total'] as const) {
        expect(
          Math.abs(value[field] - dimensions[0][field]),
          `${width}px stable ${field}`
        ).toBeLessThan(1);
      }
    }
    const layout = await carousel.evaluate((root) => ({
      overflow: document.documentElement.scrollWidth - innerWidth,
      readable: parseFloat(getComputedStyle(root.querySelector('h3')!).fontSize) >= 20,
      noClipping: [...root.querySelectorAll('h3, p')].every(
        (item) => item.scrollWidth <= item.clientWidth + 1
      ),
    }));
    expect(layout.overflow, `${width}px page width`).toBeLessThanOrEqual(2);
    expect(layout.readable, `${width}px caption size`).toBe(true);
    expect(layout.noClipping, `${width}px caption clipping`).toBe(true);
    const separated = await carousel.evaluate((root) => {
      const preview = root.querySelector('.is-next')!.getBoundingClientRect();
      const button = root.querySelector('.product-carousel-peek')!.getBoundingClientRect();
      return button.left >= preview.right + 8 || button.top >= preview.bottom + 8;
    });
    expect(separated, `${width}px arrow stays outside the preview`).toBe(true);
  }
});

test('workspace slideshow advances automatically, pauses and respects reduced motion', async ({
  page,
}) => {
  await page.clock.install();
  await page.goto('/');
  await page.waitForLoadState('networkidle');
  await page.clock.runFor(1100);
  await expect(page.locator('html')).not.toHaveClass(/scroll-locked/);
  const carousel = page.getByRole('region', { name: 'Экраны кабинета' });
  await carousel.scrollIntoViewIfNeeded();
  await page.mouse.move(0, 0);
  await expect
    .poll(() =>
      carousel
        .locator('img')
        .evaluateAll((images) => images.every((img) => (img as HTMLImageElement).complete))
    )
    .toBe(true);
  await page.clock.runFor(8500);
  await expect(carousel.getByRole('heading')).toHaveText('Каждый договор — отдельное дело');
  await carousel.getByRole('button', { name: 'Посмотреть следующий экран' }).click();
  // Move focus outside too: manual navigation must stop autoplay independently of focus pause.
  await page.locator('#views-title').click();
  await page.mouse.move(0, 0);
  await page.clock.runFor(17000);
  await expect(carousel.getByRole('heading')).toHaveText('Главное о деньгах');
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.reload();
  await carousel.scrollIntoViewIfNeeded();
  await page.clock.runFor(17000);
  await expect(carousel.getByRole('heading')).toHaveText('Должники и следующий шаг');
});

test('workspace image failure keeps the title and route into the product available', async ({
  page,
}) => {
  await page.route('**/product/debtors*', (route) => route.abort());
  await page.goto('/');
  const carousel = page.getByRole('region', { name: 'Экраны кабинета' });
  await carousel.scrollIntoViewIfNeeded();
  await expect(carousel.getByRole('link', { name: 'Открыть свой кабинет' })).toHaveAttribute(
    'href',
    '/start?plan=trial'
  );
  await carousel.getByRole('button', { name: 'Посмотреть следующий экран', exact: true }).click();
  await expect(carousel.locator('figure.is-active img')).toBeVisible();
});
