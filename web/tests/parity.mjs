// Exercise production controls and capture fictitious native-comparison inputs.

import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { chromium } from 'playwright';

const output = resolve('../.local/browser-app-evidence/parity');
await mkdir(output, { recursive: true });
const browser = await chromium.launch();
const context = await browser.newContext({ acceptDownloads: true });
const page = await context.newPage();
const ready = () =>
  page.getByText('Recursos prontos · conversão disponível offline').waitFor();
const next = () =>
  page.getByRole('button', { name: 'Continuar', exact: true }).click();
let lastDownload = 0;
const save = async (label, path, role = 'link') => {
  // Pace this bulk audit like explicit user downloads; Chromium suppresses bursts.
  const delay = 1100 - (Date.now() - lastDownload);
  if (delay > 0) await new Promise((resolve) => setTimeout(resolve, delay));
  lastDownload = Date.now();
  const pending = page.waitForEvent('download');
  await page.getByRole(role, { name: label, exact: true }).click();
  await (await pending).saveAs(path);
};
const themes = [
  'Classic',
  'Ember',
  'Engineering Classic',
  'Engineering Resumes',
  'Harvard',
  'Ink',
  'ModernCV',
  'Opal',
  'Sb2nov',
];
const longOnly = process.argv.includes('--long-only');
const cases = longOnly
  ? JSON.parse(await readFile(`${output}/cases.json`, 'utf8'))
  : [];
try {
  await page.goto('http://127.0.0.1:4173/lattes2pdf/');
  await ready();
  await context.setOffline(true);
  for (const [model, fixture, style, themeList] of [
    ['Resumido', 'academic.xml', 'ABNT', themes],
    ['Ampliado', 'academic.xml', 'ABNT', themes],
    ['Completo', 'academic.xml', 'ABNT', themes],
    ['Completo', 'presentation.xml', 'Chicago', ['Classic', 'ModernCV']],
    ['Completo', 'author-controls.xml', 'Chicago', ['Harvard']],
    ['Completo', 'reference-styles.xml', 'ABNT', ['Classic']],
    ['Completo', 'periods.xml', 'Chicago', ['Opal']],
    ['Completo', 'long-adversarial.xml', 'Chicago', themes],
  ]) {
    if (longOnly && fixture !== 'long-adversarial.xml') continue;
    await page.getByRole('radio', { name: new RegExp(`^${model}`) }).check();
    await next();
    await page
      .locator('input[type=file]')
      .setInputFiles(
        resolve(
          fixture === 'long-adversarial.xml'
            ? 'tests/fixtures'
            : '../tests/fixtures',
          fixture,
        ),
      );
    await page.getByText('Arquivo validado', { exact: true }).waitFor();
    await next();
    await page.getByRole('radio', { name: style, exact: true }).check();
    if (fixture === 'author-controls.xml') {
      await page
        .getByRole('checkbox', {
          name: 'Utilizar abreviação et al.',
          exact: true,
        })
        .check();
      await page
        .getByRole('checkbox', {
          name: 'Utilizar Citação Bibliográfica Informada',
          exact: true,
        })
        .uncheck();
    }
    if (fixture === 'periods.xml') {
      for (const [legend, year] of [
        ['Período da atuação profissional', '2020'],
        ['Período da produção', '2024'],
      ]) {
        const group = page.getByRole('group', { name: legend, exact: true });
        await group.getByRole('radio', { name: 'A partir do ano' }).check();
        await group.getByRole('textbox').fill(year);
      }
    }
    for (const theme of themeList) {
      await page.getByRole('radio', { name: theme, exact: true }).check();
      await next();
      const started = Date.now();
      await page.getByRole('button', { name: 'Gerar PDF' }).click();
      await page
        .getByRole('heading', { name: 'Seu PDF está pronto' })
        .or(page.getByRole('alert'))
        .waitFor({ timeout: 120000 });
      if (await page.getByRole('alert').count())
        throw new Error(await page.getByRole('alert').innerText());
      await page
        .getByRole('heading', { name: 'Seu PDF está pronto' })
        .waitFor();
      const key = `${model.toLowerCase()}-${fixture.replace('.xml', '')}-${theme.toLowerCase().replaceAll(' ', '')}`;
      await save('Baixar PDF', `${output}/${key}.pdf`);
      await page.getByText('Outros arquivos', { exact: true }).click();
      await save('Baixar YAML', `${output}/${key}.yaml`);
      await save('Baixar relatório', `${output}/${key}.report.json`);
      await save(
        'Salvar configuração',
        `${output}/${key}.profile.yaml`,
        'button',
      );
      cases.push({
        key,
        model,
        fixture,
        style,
        theme,
        ms: Date.now() - started,
      });
      console.log('PARITY CAPTURE', key);
      await page.getByRole('button', { name: 'Voltar e ajustar' }).click();
    }
    await page
      .getByRole('button', { name: 'Limpar tudo', exact: true })
      .click();
    await ready();
  }
  await writeFile(`${output}/cases.json`, JSON.stringify(cases, null, 2));
} finally {
  await browser.close();
}
