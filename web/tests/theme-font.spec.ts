import { execFileSync } from 'node:child_process';
import { resolve } from 'node:path';
import { expect, test } from '@playwright/test';

test('ModernCV shows its font note and generates XCharter PDFs offline', async ({
  page,
  context,
}, info) => {
  const requests: string[] = [];
  page.on('request', (request) => requests.push(request.url()));
  await page.goto('./');
  await expect(page.locator('#app[data-ready="true"]')).toBeVisible();
  expect(requests.some((url) => /fontin/i.test(url))).toBe(false);
  await context.route(/^https?:\/\//, (route) =>
    route.abort('internetdisconnected'),
  );
  await page.getByRole('button', { name: 'Continuar' }).click();
  await page
    .locator('input[type=file]')
    .setInputFiles('../examples/curriculo.xml');
  await expect(
    page.getByText('Arquivo validado', { exact: true }),
  ).toBeVisible();
  await page.getByRole('button', { name: 'Continuar' }).click();
  const note = page.getByRole('button', { name: 'Sobre a fonte do ModernCV' });
  await expect(note).toHaveCount(1);
  for (const width of [1280, 390, 320]) {
    await page.setViewportSize({ width, height: 844 });
    await note.focus();
    await page.keyboard.press('Enter');
    const dialog = page.getByRole('dialog', { name: 'Fonte do ModernCV' });
    await expect(dialog).toContainText('foi substituída pela XCharter');
    await page.keyboard.press('Escape');
    await expect(note).toBeFocused();
    await expect(
      page.getByRole('radio', { name: 'Classic', exact: true }),
    ).toBeChecked();
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
    await page
      .locator('.theme-card')
      .filter({ has: note })
      .screenshot({
        path: resolve(
          `../.local/browser-app-evidence/${info.project.name}-moderncv-${width}.png`,
        ),
      });
  }
  await page.getByRole('radio', { name: 'ModernCV', exact: true }).check();
  await page.getByRole('button', { name: 'Continuar' }).click();
  const download = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Gerar PDF' }).click();
  const pdf = resolve(
    `../.local/browser-app-evidence/${info.project.name}-moderncv.pdf`,
  );
  await (await download).saveAs(pdf);
  const fonts = execFileSync('pdffonts', [pdf], { encoding: 'utf8' });
  expect(fonts).toContain('XCharter');
  expect(fonts).not.toContain('Fontin');
  await page.getByRole('button', { name: 'Outros arquivos' }).click();
  const yaml = page.waitForEvent('download');
  await page.getByRole('link', { name: 'Baixar YAML' }).click();
  await (await yaml).saveAs(pdf.replace(/\.pdf$/, '.yaml'));
});
