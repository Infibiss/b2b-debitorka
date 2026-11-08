import { test, expect } from './fixtures';
test('one invoice moves through documents, promise and actual payment evidence', async ({
  page,
}) => {
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.goto('/');
  const process = page.getByRole('region', { name: 'Как проходит работа со счётом' });
  await process.getByRole('tab', { name: /Документы/ }).click();
  await expect(process.getByRole('tabpanel')).toContainText('Нужен акт');
  await process.getByRole('tab', { name: /Договорённость/ }).click();
  await expect(process.getByRole('tabpanel')).toContainText('Обещание оплаты');
  await process.getByRole('tab', { name: /Закрытие/ }).click();
  await expect(process.getByRole('tabpanel')).toContainText('Остаток обнулён');
  await expect(
    page.getByRole('contentinfo').getByRole('link', { name: 'Удаление данных', exact: true })
  ).toHaveCount(0);
});
test('subscription comparison adds capabilities with each tier', async ({ page }) => {
  await page.goto('/pricing');
  const table = page.getByRole('table', { name: 'Состав подписки по тарифам' });
  await expect(table.getByRole('row', { name: /Юридические дела/ })).toContainText('—');
  await expect(table.getByRole('row', { name: /Подготовка претензии/ })).toContainText('Включено');
  await expect(table.getByRole('row')).toHaveCount(11);
});
