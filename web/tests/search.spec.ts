import { expect, test } from '@playwright/test';

test('public guidance is readable without JavaScript and matches the published URL', async ({
  browser,
  request,
}) => {
  const context = await browser.newContext({ javaScriptEnabled: false });
  const page = await context.newPage();
  const requests: string[] = [];
  page.on('request', (request) => requests.push(request.url()));
  try {
    await page.goto('http://127.0.0.1:4173/lattes2pdf/');
    await expect(page).toHaveTitle(/Converter Currículo Lattes em PDF/);
    await expect(page.getByRole('heading', { level: 1 })).toHaveText(
      'Seu Currículo Lattes em PDF',
    );
    await expect(page.getByText(/Ative o JavaScript/)).toBeVisible();
    const guide = page.getByRole('region', {
      name: 'Como usar o lattes2pdf',
    });
    await expect(guide.getByRole('listitem')).toHaveCount(3);
    await expect(
      guide.getByRole('link', { name: 'Plataforma Lattes do CNPq' }),
    ).toHaveAttribute('href', 'https://lattes.cnpq.br/');
    await page.getByRole('link', { name: 'Como exportar meu Lattes?' }).click();
    await expect(page).toHaveURL(/#como-exportar$/);
    await expect(page.locator('#como-exportar')).toBeInViewport();
    // Reading the guide should not depend on downloading the converter.
    expect(requests.some((url) => /\.(wasm|whl|zip)(?:$|\?)/.test(url))).toBe(
      false,
    );
    const canonical = await page
      .locator('link[rel="canonical"]')
      .getAttribute('href');
    expect(canonical).toBe('https://mpds.github.io/lattes2pdf/');
    await expect(page.locator('meta[property="og:url"]')).toHaveAttribute(
      'content',
      canonical!,
    );
    const sitemap = await request.get('sitemap.xml');
    expect(sitemap.ok()).toBe(true);
    expect(await sitemap.text()).toContain(`<loc>${canonical}</loc>`);
    const image = new URL(
      (await page
        .locator('meta[property="og:image"]')
        .getAttribute('content'))!,
    );
    expect(image.origin).toBe(new URL(canonical!).origin);
    expect((await request.get(image.pathname)).ok()).toBe(true);
  } finally {
    await context.close();
  }
});
