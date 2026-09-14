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
    'Seu Currículo Lattes em PDF',
  );
  await expect(
    page.getByRole('main').getByRole('heading', { level: 2 }),
  ).toHaveText('Escolha o modelo');
  await expect(page.getByRole('radio', { name: /Resumido/ })).toBeChecked();
  await expect(page.getByRole('checkbox')).toHaveCount(0);
  await expect(
    page.getByRole('link', { name: 'Código no GitHub' }),
  ).toHaveAttribute('href', 'https://github.com/mpds/lattes2pdf');
  await expect(page.locator('#app[data-ready="true"]')).toBeVisible();
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
  await page.getByRole('button', { name: 'Concluir seleção' }).click();
  await expect(page.getByRole('button', { name: 'Continuar' })).toBeDisabled();
  await page.getByRole('button', { name: 'Escolher categorias' }).click();
  await page
    .getByRole('checkbox', {
      name: 'Formação acadêmica/titulação',
      exact: true,
    })
    .check();
  await page.getByRole('button', { name: 'Concluir seleção' }).click();
  await page.getByRole('radio', { name: /Ampliado/ }).check();
  await page.getByRole('radio', { name: /Personalizado/ }).check();
  await expect(page.getByRole('checkbox', { checked: true })).toHaveCount(1);
  await page.getByRole('button', { name: 'Concluir seleção' }).click();
  await page.getByRole('radio', { name: /Resumido/ }).check();
  await page.getByRole('button', { name: 'Continuar' }).click();
  await page
    .locator('input[type=file]')
    .setInputFiles('../tests/fixtures/academic.xml');
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
  // Put the action in view before measuring: clicking an offscreen button
  // scrolls the test browser, independently of the application's layout.
  await page
    .getByRole('button', { name: 'Gerar PDF' })
    .scrollIntoViewIfNeeded();
  const downloadEvent = page.waitForEvent('download');
  const actionPosition = await page
    .getByRole('button', { name: 'Gerar PDF' })
    .boundingBox();
  const navigationPosition = await page
    .getByRole('button', { name: 'Voltar e ajustar' })
    .boundingBox();
  await page.getByRole('button', { name: 'Gerar PDF' }).click();
  await expect(
    page.getByRole('heading', { name: 'Seu PDF está pronto' }),
  ).toBeVisible();
  await (await downloadEvent).saveAs(`${evidence}/${info.project.name}-ui.pdf`);
  await expect(page.getByText('PDF gerado com sucesso')).toBeVisible();
  await expect(
    page.getByRole('button', { name: 'Visualizar PDF' }),
  ).toHaveCount(0);
  expect(
    await page.getByRole('button', { name: 'Gerar PDF' }).boundingBox(),
  ).toEqual(actionPosition);
  expect(
    await page.getByRole('button', { name: 'Voltar e ajustar' }).boundingBox(),
  ).toEqual(navigationPosition);
  const retryDownload = page.waitForEvent('download');
  await page.getByRole('link', { name: 'Baixar PDF novamente' }).click();
  expect((await retryDownload).suggestedFilename()).toBe('curriculo.pdf');
  await page.getByRole('button', { name: 'Outros arquivos' }).click();
  await expect(page.getByRole('dialog')).toBeVisible();
  const reportDownload = page.waitForEvent('download');
  await page.getByRole('link', { name: 'Baixar relatório' }).click();
  expect((await reportDownload).suggestedFilename()).toBe(
    'curriculo.report.json',
  );
  await page.keyboard.press('Escape');
  await expect(
    page.getByRole('button', { name: 'Outros arquivos' }),
  ).toBeFocused();
  await page.screenshot({
    path: `${evidence}/${info.project.name}-result.png`,
    fullPage: true,
  });
  for (const width of [390, 1280]) {
    await page.setViewportSize({ width, height: 844 });
    const card = page.locator('.delivery.complete');
    const bottomSpace = await card.evaluate((node) => {
      const contentBottom = Math.max(
        ...Array.from(
          node.children,
          (child) => child.getBoundingClientRect().bottom,
        ),
      );
      return node.getBoundingClientRect().bottom - contentBottom;
    });
    expect(bottomSpace).toBeLessThanOrEqual(24);
    await page.locator('.panel').screenshot({
      path: `${evidence}/${info.project.name}-success-panel-${width}.png`,
    });
  }
  await page.setViewportSize({ width: 320, height: 740 });
  await page.getByRole('button', { name: 'Voltar e ajustar' }).click();
  await page.getByRole('radio', { name: 'ABNT', exact: true }).check();
  await page.getByRole('button', { name: 'Continuar' }).click();
  await expect(
    page.getByText('As escolhas mudaram. Gere novamente para atualizar o PDF.'),
  ).toBeVisible();
  const position = () =>
    page
      .getByRole('button', { name: 'Gerar PDF' })
      .evaluate((node) => node.getBoundingClientRect().top + window.scrollY);
  const previousPosition = await position();
  const updatedDownload = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Gerar PDF' }).click();
  expect((await updatedDownload).suggestedFilename()).toBe('curriculo.pdf');
  await expect(page.getByText('PDF gerado com sucesso')).toBeVisible();
  expect(await position()).toBeCloseTo(previousPosition, 2);
  await page.getByRole('button', { name: 'Limpar tudo', exact: true }).click();
  await expect(
    page.getByRole('heading', { name: 'Escolha o modelo' }),
  ).toBeVisible();
  await expect(page.getByText('Ana Exemplo Fictícia')).toHaveCount(0);
  await expect(page.locator('#app[data-ready="true"]')).toBeVisible();
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

test('custom categories stay inside the dialog and preserve the page layout on small screens', async ({
  page,
}, info) => {
  await page.setViewportSize({ width: 320, height: 740 });
  await page.goto('./');
  await expect(page.locator('#app[data-ready="true"]')).toBeVisible();
  const next = page.getByRole('button', { name: 'Continuar' });
  await next.scrollIntoViewIfNeeded();
  const position = () =>
    next.evaluate((node) => node.getBoundingClientRect().top + window.scrollY);
  const original = await position();
  await page.getByRole('radio', { name: /^Personalizado/ }).check();
  const dialog = page.getByRole('dialog', { name: 'Categorias do currículo' });
  await expect(dialog).toBeVisible();
  await page.getByRole('button', { name: 'Selecionar todas' }).click();
  await expect(page.getByRole('checkbox', { checked: true })).toHaveCount(33);
  await page.getByRole('button', { name: 'Desmarcar todas' }).click();
  await expect(page.getByRole('checkbox', { checked: true })).toHaveCount(0);
  expect(
    await dialog.evaluate((node) => node.scrollWidth <= node.clientWidth),
  ).toBe(true);
  const bounds = await dialog.boundingBox();
  for (const label of ['Selecionar todas', 'Desmarcar todas']) {
    const control = await page
      .getByRole('button', { name: label })
      .boundingBox();
    expect(control!.x).toBeGreaterThanOrEqual(bounds!.x);
    expect(control!.x + control!.width).toBeLessThanOrEqual(
      bounds!.x + bounds!.width,
    );
  }
  await page.screenshot({
    path: `${evidence}/${info.project.name}-categories-mobile.png`,
  });
  await page.keyboard.press('Escape');
  await expect(
    page.getByRole('button', { name: 'Escolher categorias' }),
  ).toBeFocused();
  await expect(next).toBeDisabled();
  await next.scrollIntoViewIfNeeded();
  expect(await position()).toBeCloseTo(original, 2);
  await page.getByRole('button', { name: 'Escolher categorias' }).click();
  await page.getByRole('button', { name: 'Selecionar todas' }).click();
  await page.getByRole('button', { name: 'Concluir seleção' }).click();
  await expect(next).toBeEnabled();
  const chooserEvent = page.waitForEvent('filechooser');
  await page.getByText('Reutilizar configuração', { exact: true }).click();
  await chooserEvent;
  await next.scrollIntoViewIfNeeded();
  expect(await position()).toBeCloseTo(original, 2);
  await expect(page.locator('details')).toHaveCount(0);
  await expect(
    page.getByRole('button', { name: 'Limpar tudo', exact: true }),
  ).toHaveCount(1);
  await expect(
    page.getByRole('link', { name: 'Encontrou um problema?' }),
  ).toHaveAttribute('href', 'https://github.com/mpds/lattes2pdf/issues/new');
  await page.getByRole('button', { name: 'Privacidade', exact: true }).click();
  await expect(page.getByRole('dialog', { name: 'Privacidade' })).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(
    page.getByRole('button', { name: 'Privacidade', exact: true }),
  ).toBeFocused();
  for (const label of ['Continuar', 'Voltar']) {
    const navigation = page.getByRole('button', { name: label, exact: true });
    await navigation.scrollIntoViewIfNeeded();
    const scrollBefore = await page.evaluate(() => window.scrollY);
    await navigation.click();
    expect(await page.evaluate(() => window.scrollY)).toBeCloseTo(
      scrollBefore,
      2,
    );
  }
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
});
