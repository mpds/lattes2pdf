import { expect, test } from '@playwright/test';

const ready = 'Recursos prontos · conversão disponível offline';
test('page and Blob-worker CSP reject script evaluation and external transport', async ({
  page,
}) => {
  await page.goto('./');
  await expect(page.getByText(ready)).toBeVisible();
  // DevTools evaluation itself bypasses CSP. Run the probe as an ordinary
  // permitted Blob script so the browser applies the document policy.
  expect(
    await page.evaluate(
      () =>
        new Promise<boolean>((resolve) => {
          const script = document.createElement('script');
          const source = `globalThis.__cspEvalBlocked = false; try { new Function('return 1')(); } catch { globalThis.__cspEvalBlocked = true; }`;
          const url = URL.createObjectURL(
            new Blob([source], { type: 'text/javascript' }),
          );
          script.src = url;
          script.onload = () => {
            const result = (
              globalThis as unknown as { __cspEvalBlocked: boolean }
            ).__cspEvalBlocked;
            script.remove();
            URL.revokeObjectURL(url);
            resolve(result);
          };
          document.head.append(script);
        }),
    ),
  ).toBe(true);
  const checks = await page.evaluate(
    () =>
      new Promise<{ evalBlocked: boolean; fetchBlocked: boolean }>(
        (resolve) => {
          const source = `let evalBlocked = false; try { new Function('return 1')(); } catch { evalBlocked = true; }
      fetch('https://blocked.invalid/csp-probe').then(() => postMessage({evalBlocked, fetchBlocked: false})).catch(() => postMessage({evalBlocked, fetchBlocked: true}));`;
          const url = URL.createObjectURL(
            new Blob([source], { type: 'text/javascript' }),
          );
          const worker = new Worker(url, { type: 'module' });
          worker.onmessage = ({ data }) => {
            worker.terminate();
            URL.revokeObjectURL(url);
            resolve(data);
          };
        },
      ),
  );
  expect(checks).toEqual({ evalBlocked: true, fetchBlocked: true });
});

test('invalid input, cancellation, reset and keyboard selection cannot restore an old document', async ({
  page,
  context,
}, info) => {
  await page.goto('./');
  await expect(page.getByText(ready)).toBeVisible();
  await context.route(/^https?:\/\//, (route) =>
    route.abort('internetdisconnected'),
  );
  if (info.project.name !== 'webkit') await context.setOffline(true);
  const first = page.getByRole('radio', { name: /^Resumido/ });
  await first.focus();
  await page.keyboard.press('ArrowRight');
  await expect(page.getByRole('radio', { name: /^Ampliado/ })).toBeChecked();
  await expect(page.getByRole('radio', { name: /^Ampliado/ })).toBeFocused();
  await page.keyboard.press('ArrowRight');
  await expect(page.getByRole('radio', { name: /^Completo/ })).toBeChecked();
  await page.getByRole('button', { name: 'Continuar' }).click();
  await page.locator('input[type=file]').setInputFiles({
    name: '<img onerror=alert(1)>.xml',
    mimeType: 'text/xml',
    buffer: Buffer.from(
      '<!DOCTYPE x [<!ENTITY e "marker">]><CURRICULO-VITAE/>',
    ),
  });
  await expect(page.getByRole('alert')).toContainText('DTD ou entidades');
  await expect(page.getByRole('button', { name: 'Continuar' })).toBeDisabled();
  await page.getByRole('button', { name: 'Usar exemplo fictício' }).click();
  await page.getByRole('button', { name: 'Cancelar', exact: true }).click();
  await expect(page.getByText(ready)).toBeVisible();
  await expect(page.getByText('Ana Exemplo Fictícia')).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Continuar' })).toBeDisabled();
  await page.getByRole('button', { name: 'Usar exemplo fictício' }).click();
  await expect(page.getByText('Arquivo validado')).toBeVisible();
  await page.getByRole('button', { name: 'Limpar tudo', exact: true }).click();
  await expect(page.getByText(ready)).toBeVisible();
  await expect(page.getByText('Ana Exemplo Fictícia')).toHaveCount(0);
  await expect(page.getByRole('radio', { name: /^Resumido/ })).toBeChecked();
});

test('downloaded simple configuration restores visible controls offline and rejects advanced input', async ({
  page,
  context,
}, info) => {
  await page.goto('./');
  await expect(page.getByText(ready)).toBeVisible();
  await context.route(/^https?:\/\//, (route) =>
    route.abort('internetdisconnected'),
  );
  if (info.project.name !== 'webkit') await context.setOffline(true);
  await page.getByRole('radio', { name: /^Personalizado/ }).check();
  await page.getByRole('button', { name: 'Desmarcar todas' }).click();
  await page
    .getByRole('checkbox', {
      name: 'Formação acadêmica/titulação',
      exact: true,
    })
    .check();
  await page.getByRole('button', { name: 'Continuar' }).click();
  await page.getByRole('button', { name: 'Usar exemplo fictício' }).click();
  await expect(page.getByText('Arquivo validado')).toBeVisible();
  await page.getByRole('button', { name: 'Continuar' }).click();
  await page.getByRole('radio', { name: 'Opal', exact: true }).check();
  await page.getByRole('radio', { name: 'Chicago', exact: true }).check();
  const professional = page.getByRole('group', {
    name: 'Período da atuação profissional',
    exact: true,
  });
  await professional.getByRole('radio', { name: 'A partir do ano' }).check();
  await professional.getByRole('textbox').fill('2020');
  await page.getByRole('button', { name: 'Continuar' }).click();
  const pending = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Salvar configuração' }).click();
  const file = await (await pending).path();
  await page.getByRole('button', { name: 'Limpar tudo', exact: true }).click();
  await expect(page.getByText(ready)).toBeVisible();
  await page.getByText('Reutilizar configuração', { exact: true }).click();
  await page.locator('input[type=file]').setInputFiles(file!);
  await expect(
    page.getByRole('radio', { name: /^Personalizado/ }),
  ).toBeChecked();
  await expect(page.getByRole('checkbox', { checked: true })).toHaveCount(1);
  await page.getByRole('button', { name: 'Continuar' }).click();
  await page.getByRole('button', { name: 'Usar exemplo fictício' }).click();
  await expect(page.getByText('Arquivo validado')).toBeVisible();
  await page.getByRole('button', { name: 'Continuar' }).click();
  await expect(
    page.getByRole('radio', { name: 'Opal', exact: true }),
  ).toBeChecked();
  await expect(
    page.getByRole('radio', { name: 'Chicago', exact: true }),
  ).toBeChecked();
  await expect(professional.getByRole('textbox')).toHaveValue('2020');
  await expect(
    page
      .getByRole('group', { name: 'Período da produção', exact: true })
      .getByRole('radio', { name: 'Todo o período' }),
  ).toBeChecked();
  await professional.getByRole('radio', { name: 'Todo o período' }).check();
  await expect(professional.getByRole('textbox')).toHaveCount(0);
  await page.getByRole('button', { name: 'Limpar tudo', exact: true }).click();
  await expect(page.getByText(ready)).toBeVisible();
  await page.getByText('Reutilizar configuração', { exact: true }).click();
  await page.locator('input[type=file]').setInputFiles({
    name: 'advanced.yaml',
    mimeType: 'text/yaml',
    buffer: Buffer.from('include_ids: [fictitious-record]\n'),
  });
  await expect(page.getByRole('alert')).toContainText('CLI');
  await expect(page.getByRole('radio', { name: /^Resumido/ })).toBeChecked();
});
