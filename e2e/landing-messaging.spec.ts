import { test, expect } from './fixtures';

test('landing explains credit interest and calculates only the entered financing cost', async ({
  page,
}) => {
  await page.goto('/');
  const calculator = page.getByRole('region', { name: 'Стоимость задержки оплаты', exact: true });
  await calculator.scrollIntoViewIfNeeded();
  await expect(calculator).toContainText('Если покрываете неоплаченные счета кредитом');
  await expect(page.getByText('Стоимость денег в год', { exact: true })).toHaveCount(0);
  await calculator.getByLabel('Задержка оплаты').fill('73');
  await calculator.getByLabel('Ставка по кредиту, годовых').fill('12');
  await calculator.getByLabel('Сумма неоплаченных счетов').focus();
  await calculator.getByLabel('Сумма неоплаченных счетов').press('Home');
  await expect(calculator.locator('output')).toHaveText(/2\s?400\s?₽/);
  await calculator.getByLabel('Задержка оплаты').fill('365');
  await expect(calculator.locator('output')).toHaveText(/12\s?000\s?₽/);
  await expect(calculator).toContainText('Проценты за время ожидания');
  await expect(calculator).not.toContainText('Вы сэкономите');
});

test('FAQ and final action use readable aligned layouts on each viewport', async ({
  page,
}, info) => {
  await page.goto('/');
  const faq = page.getByRole('region', { name: 'Вопросы и ответы', exact: true });
  await faq.scrollIntoViewIfNeeded();
  const heading = faq.getByRole('heading', { name: 'Вопросы и ответы', exact: true });
  const question = faq.getByRole('button', { name: 'Как начать работу?', exact: true });
  await question.click();
  await expect(faq.getByText('Загрузите реестр счетов в CSV из Excel или 1С.')).toHaveCount(0);
  await question.click();
  await expect(faq.getByText('Загрузите реестр счетов в CSV из Excel или 1С.')).toBeVisible();
  const faqBox = await faq.boundingBox();
  const headingBox = await heading.boundingBox();
  expect(headingBox!.width).toBeLessThanOrEqual(faqBox!.width);
  const fontSize = await heading.evaluate((el) => parseFloat(getComputedStyle(el).fontSize));
  expect(fontSize).toBeLessThanOrEqual(40);
  if (info.project.name === 'desktop') {
    expect(headingBox!.height).toBeLessThan(fontSize * 2);
  }
  const finalAction = page.getByRole('region', { name: 'Начните со своего реестра', exact: true });
  await finalAction.scrollIntoViewIfNeeded();
  const titleBox = await finalAction.getByRole('heading').boundingBox();
  const buttonBox = await finalAction.getByRole('link', { name: 'Загрузить реестр' }).boundingBox();
  expect(Math.abs(titleBox!.x - buttonBox!.x)).toBeLessThanOrEqual(2);
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)
  ).toBeLessThanOrEqual(2);
  await page.screenshot({
    path: info.outputPath('landing-final-action.png'),
    animations: 'disabled',
  });
});
