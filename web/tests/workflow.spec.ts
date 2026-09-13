import { resolve } from 'node:path';
import { expect, test } from '@playwright/test';

const evidence = resolve('../.local/browser-app-evidence');
test('progressive workflow, real downloads, offline reset, responsive and privacy', async ({
  page,
  context,
  browser,
}, info) => {
  const requests: string[] = [];
  const logs: string[] = [];
  page.on('request', (r) => requests.push(r.url()));
  page.on('console', (m) => logs.push(m.text()));
  await page.goto('./');
  await expect(page.getByRole('heading', { level: 1 })).toHaveText(
    'Escolha o modelo',
  );
  await expect(page.getByRole('radio', { name: /Resumido/ })).toBeChecked();
  await expect(page.getByRole('checkbox')).toHaveCount(0);
  await expect(
    page.getByRole('link', { name: 'Código no GitHub' }),
  ).toHaveAttribute('href', 'https://github.com/mpds/lattes2pdf');
  await expect(
    page.getByText('Recursos prontos · conversão disponível offline'),
  ).toBeVisible();
  console.log('Browser', info.project.name, browser.version());
  await page.screenshot({
    path: `${evidence}/${info.project.name}-modelo.png`,
    fullPage: true,
  });
  // Playwright WebKit's offline flag also blocks even a trivial Blob worker
  // (reproduced separately). Block all HTTP(S) transport for every engine;
  // Chromium/Firefox additionally exercise the browser's offline flag.
  await context.route(/^https?:\/\//, (route) =>
    route.abort('internetdisconnected'),
  );
  if (info.project.name !== 'webkit') await context.setOffline(true);
  const requestCount = requests.length;
  await page.getByRole('radio', { name: /Personalizado/ }).check();
  await expect(page.getByRole('checkbox')).toHaveCount(33);
  await page.getByRole('button', { name: 'Desmarcar todas' }).click();
  await expect(page.getByRole('button', { name: 'Continuar' })).toBeDisabled();
  await page
    .getByRole('checkbox', {
      name: 'Formação acadêmica/titulação',
      exact: true,
    })
    .check();
  await page.getByRole('radio', { name: /Ampliado/ }).check();
  await page.getByRole('radio', { name: /Personalizado/ }).check();
  await expect(page.getByRole('checkbox', { checked: true })).toHaveCount(1);
  await page.getByRole('radio', { name: /Resumido/ }).check();
  await page.getByRole('button', { name: 'Continuar' }).click();
  await page.getByRole('button', { name: 'Usar exemplo fictício' }).click();
  await expect(
    page.getByRole('heading', { name: 'Ana Exemplo Fictícia' }),
  ).toBeVisible();
  await page.getByRole('button', { name: 'Continuar' }).click();
  await expect(
    page.getByRole('radio', { name: 'Classic', exact: true }),
  ).toBeChecked();
  await expect(page.locator('.theme-option img')).toHaveCount(9);
  expect(
    await page
      .locator('.theme-option img')
      .evaluateAll((images) =>
        images.every(
          (img) =>
            (img as HTMLImageElement).complete &&
            (img as HTMLImageElement).naturalWidth > 0,
        ),
      ),
  ).toBe(true);
  await page.screenshot({
    path: `${evidence}/${info.project.name}-preferencias.png`,
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: `${evidence}/${info.project.name}-mobile.png`,
    fullPage: true,
  });
  await page.getByRole('radio', { name: 'Chicago', exact: true }).check();
  await page.getByRole('button', { name: 'Continuar' }).click();
  await page.getByRole('button', { name: 'Gerar PDF' }).click();
  await expect(
    page.getByRole('heading', { name: 'Seu PDF está pronto' }),
  ).toBeVisible();
  const downloadEvent = page.waitForEvent('download');
  await page.getByRole('link', { name: 'Baixar PDF', exact: true }).click();
  await (await downloadEvent).saveAs(`${evidence}/${info.project.name}-ui.pdf`);
  await page.getByRole('button', { name: 'Visualizar PDF' }).click();
  await expect(page.getByRole('dialog')).toBeVisible();
  await expect(
    page.getByRole('img', { name: 'Página 1 de 1 do currículo' }),
  ).toBeVisible();
  await page.screenshot({
    path: `${evidence}/${info.project.name}-preview.png`,
  });
  await page.getByRole('button', { name: 'Fechar', exact: true }).click();
  await page.getByRole('button', { name: 'Limpar tudo', exact: true }).click();
  await expect(
    page.getByRole('heading', { name: 'Escolha o modelo' }),
  ).toBeVisible();
  await expect(page.getByText('Ana Exemplo Fictícia')).toHaveCount(0);
  await expect(
    page.getByText('Recursos prontos · conversão disponível offline'),
  ).toBeVisible();
  await page.getByRole('button', { name: 'Continuar' }).click();
  await page
    .locator('input[type=file]')
    .setInputFiles(resolve('../tests/fixtures/latin1.xml'));
  await expect(
    page.getByRole('heading', { name: 'Ana Exemplo Fictícia' }),
  ).toBeVisible();
  expect(
    requests.slice(requestCount).filter((url) => !url.startsWith('blob:')),
  ).toEqual([]);
  expect(logs.join('\n')).not.toMatch(/Ana Exemplo|academic.xml|latin1.xml/);
  const storage = await page.evaluate(async () => ({
    local: localStorage.length,
    session: sessionStorage.length,
    cookies: document.cookie,
    databases: await indexedDB.databases(),
    caches: await caches.keys(),
  }));
  expect(storage).toEqual({
    local: 0,
    session: 0,
    cookies: '',
    databases: [],
    caches: [],
  });
});
