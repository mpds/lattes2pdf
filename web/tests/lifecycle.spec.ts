import { execFileSync } from 'node:child_process';
import { readFile } from 'node:fs/promises';
import { expect, test } from '@playwright/test';

const ready = '#app[data-ready="true"]';

test('ZIP member choice, bounded failures and compiler failure recover without old output', async ({
  page,
  context,
}, info) => {
  const logs: string[] = [];
  const requests: string[] = [];
  page.on('console', (message) => logs.push(message.text()));
  page.on('request', (request) => requests.push(request.url()));
  page.on('dialog', () => {
    throw new Error('Untrusted text opened a browser dialog');
  });
  await page.goto('./');
  await expect(page.locator(ready)).toBeVisible();
  const requestCount = requests.length;
  await context.route(/^https?:\/\//, (route) =>
    route.abort('internetdisconnected'),
  );
  if (info.project.name !== 'webkit') await context.setOffline(true);
  await page.getByRole('button', { name: 'Continuar' }).click();
  const zipped = execFileSync('../.venv/bin/python', [
    '-c',
    `import io,sys,zipfile
from pathlib import Path
out=io.BytesIO()
with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
 z.writestr('folder/<script>.xml',Path('../tests/fixtures/latin1.xml').read_bytes())
 z.writestr('second.xml',Path('../tests/fixtures/academic.xml').read_bytes())
 z.writestr('broken.xml',b'<CURRICULO-VITAE>')
sys.stdout.buffer.write(out.getvalue())`,
  ]);
  await page.locator('input[type=file]').setInputFiles({
    name: '<img onerror=alert(1)>.zip',
    mimeType: 'application/zip',
    buffer: zipped,
  });
  await expect(page.getByRole('combobox')).toBeVisible();
  await page.getByRole('combobox').selectOption('broken.xml');
  await page.getByRole('button', { name: 'Abrir XML selecionado' }).click();
  await expect(page.getByRole('alert')).toContainText('XML malformado');
  await page.getByRole('button', { name: 'Trocar arquivo' }).click();
  await expect(page.locator(ready)).toBeVisible();
  await page.locator('input[type=file]').setInputFiles({
    name: 'replacement.zip',
    mimeType: 'application/zip',
    buffer: zipped,
  });
  await expect(page.getByRole('combobox')).toBeVisible();
  await page.getByRole('combobox').selectOption('folder/<script>.xml');
  await page.getByRole('button', { name: 'Abrir XML selecionado' }).click();
  await expect(page.getByText('Arquivo validado')).toBeVisible();
  await page.getByRole('button', { name: 'Trocar arquivo' }).click();
  await expect(page.locator(ready)).toBeVisible();
  for (const size of [0, 25 * 1024 * 1024 + 1]) {
    await page.locator('input[type=file]').setInputFiles({
      name: 'invalid-size.xml',
      mimeType: 'text/xml',
      buffer: Buffer.alloc(size, 32),
    });
    await expect(page.getByRole('alert')).toContainText('25 MiB');
    await expect(
      page.getByRole('button', { name: 'Continuar' }),
    ).toBeDisabled();
    // Reject file metadata immediately, keeping the converter ready to try again.
    expect(await page.locator('#app').getAttribute('data-ready')).toBe('true');
    await expect(page.locator('input[type=file]')).toBeEnabled();
  }
  await page.locator('input[type=file]').setInputFiles({
    name: 'deep.xml',
    mimeType: 'text/xml',
    buffer: Buffer.from('<x>'.repeat(130) + '</x>'.repeat(130)),
  });
  await expect(page.getByRole('alert')).toContainText('profundidade');
  const source = (
    await readFile('../tests/fixtures/academic.xml', 'utf8')
  ).replaceAll(
    'Ana Exemplo Fictícia',
    'Lúcia #panic(&quot;INJECAO&quot;) &lt;script&gt;',
  );
  await page.locator('input[type=file]').setInputFiles({
    name: 'untrusted-header.xml',
    mimeType: 'text/xml',
    buffer: Buffer.from(source),
  });
  await expect(page.getByText('Arquivo validado')).toBeVisible();
  await page.getByRole('button', { name: 'Continuar' }).click();
  await page.getByRole('button', { name: 'Continuar' }).click();
  await page.getByRole('button', { name: 'Gerar PDF' }).click();
  // RenderCV 2.8 also rejects this header through the unchanged native CLI.
  await expect(page.getByRole('alert')).toContainText(
    'Não foi possível compor o PDF',
  );
  await expect(
    page.getByRole('link', { name: 'Baixar PDF novamente', exact: true }),
  ).toHaveCount(0);
  await page.getByRole('button', { name: 'Limpar tudo', exact: true }).click();
  await expect(page.locator(ready)).toBeVisible();
  await page.getByRole('button', { name: 'Continuar' }).click();
  await page
    .locator('input[type=file]')
    .setInputFiles('../tests/fixtures/academic.xml');
  await expect(page.getByText('Arquivo validado')).toBeVisible();
  await page.getByRole('button', { name: 'Continuar' }).click();
  await page.getByRole('button', { name: 'Continuar' }).click();
  await page.getByRole('button', { name: 'Gerar PDF' }).click();
  await expect(
    page.getByRole('heading', { name: 'Seu PDF está pronto' }),
  ).toBeVisible();
  expect(
    requests.slice(requestCount).filter((url) => !url.startsWith('blob:')),
  ).toEqual([]);
  expect(logs.join('\n')).not.toMatch(/INJECAO|Lúcia|untrusted-header|onerror/);
});

test('cancel synchronous compilation, download a long document and navigation discard documents', async ({
  page,
  context,
}, info) => {
  await page.goto('./');
  await expect(page.locator(ready)).toBeVisible();
  await context.route(/^https?:\/\//, (route) =>
    route.abort('internetdisconnected'),
  );
  if (info.project.name !== 'webkit') await context.setOffline(true);
  await page.getByRole('radio', { name: /^Completo/ }).check();
  await page.getByRole('button', { name: 'Continuar' }).click();
  const source = await readFile('tests/fixtures/long-adversarial.xml', 'utf8');
  const articles = source.match(
    /<ARTIGOS-PUBLICADOS>([\s\S]*?)<\/ARTIGOS-PUBLICADOS>/,
  )![1];
  const larger = source.replace(articles, articles.repeat(25));
  await page.locator('input[type=file]').setInputFiles({
    name: 'long-cancellation.xml',
    mimeType: 'text/xml',
    buffer: Buffer.from(larger),
  });
  await expect(page.getByText('Arquivo validado')).toBeVisible();
  await page.getByRole('button', { name: 'Continuar' }).click();
  await page.getByRole('button', { name: 'Continuar' }).click();
  await page.getByRole('button', { name: 'Gerar PDF' }).click();
  await expect(
    page.getByText('Compondo o PDF…', { exact: true }),
  ).toBeVisible();
  const start = Date.now();
  await page.getByRole('button', { name: 'Cancelar', exact: true }).click();
  await expect(
    page.getByRole('heading', { name: 'Abra seu currículo' }),
  ).toBeVisible();
  expect(Date.now() - start).toBeLessThan(3000);
  await expect(page.locator(ready)).toBeVisible();
  await expect(
    page.getByRole('link', { name: 'Baixar PDF novamente', exact: true }),
  ).toHaveCount(0);
  await page
    .locator('input[type=file]')
    .setInputFiles('tests/fixtures/long-adversarial.xml');
  await expect(page.getByText('Arquivo validado')).toBeVisible();
  await page.getByRole('button', { name: 'Continuar' }).click();
  await page.getByRole('button', { name: 'Continuar' }).click();
  await page.getByRole('button', { name: 'Gerar PDF' }).click();
  await expect(
    page.getByRole('heading', { name: 'Seu PDF está pronto' }),
  ).toBeVisible();
  await expect(
    page.getByRole('link', { name: 'Baixar PDF novamente' }),
  ).toBeVisible();
  await context.unrouteAll();
  await context.setOffline(false);
  await page.goto('about:blank');
  await page.goBack();
  await expect(
    page.getByRole('heading', { name: 'Escolha o modelo' }),
  ).toBeVisible();
  await expect(page.getByRole('radio', { name: /^Resumido/ })).toBeChecked();
  await expect(page.getByText('Lúcia Exemplo')).toHaveCount(0);
  await expect(
    page.getByRole('link', { name: 'Baixar PDF novamente', exact: true }),
  ).toHaveCount(0);
});
