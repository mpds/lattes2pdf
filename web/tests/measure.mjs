// Local measurements use only repository fictitious fixtures; no production hooks.
import { execFileSync } from 'node:child_process';
import { readFile, writeFile } from 'node:fs/promises';
import { chromium } from 'playwright';

const server = await chromium.launchServer();
const browser = await chromium.connect(server.wsEndpoint());
const context = await browser.newContext();
const page = await context.newPage();
const ready = () => page.locator('#app[data-ready="true"]').waitFor();
const next = () =>
  page.getByRole('button', { name: 'Continuar', exact: true }).click();
const hardware = Object.fromEntries(
  ['hw.model', 'machdep.cpu.brand_string', 'hw.memsize'].map((key) => [
    key,
    execFileSync('/usr/sbin/sysctl', ['-n', key], { encoding: 'utf8' }).trim(),
  ]),
);
function rss() {
  const rows = execFileSync('/bin/ps', ['-axo', 'pid,ppid,rss'], {
    encoding: 'utf8',
  })
    .trim()
    .split('\n')
    .slice(1)
    .map((line) => line.trim().split(/\s+/).map(Number));
  const pids = new Set([server.process().pid]);
  for (let n = 0; n < 10; n++)
    for (const [pid, parent] of rows) if (pids.has(parent)) pids.add(pid);
  return rows
    .filter(([pid]) => pids.has(pid))
    .reduce((total, row) => total + row[2] * 1024, 0);
}
const result = {
  hardware,
  browser: browser.version(),
  initMs: 0,
  readyRss: 0,
  conversions: [],
};
try {
  const start = Date.now();
  await page.goto('http://127.0.0.1:4173/lattes2pdf/');
  await ready();
  result.initMs = Date.now() - start;
  result.readyRss = rss();
  await context.setOffline(true);
  for (const fixture of [
    'academic',
    'long-adversarial',
    'academic',
    'five-mib',
  ]) {
    await page.getByRole('radio', { name: /^Completo/ }).check();
    await next();
    const loadStart = Date.now();
    let raw = await readFile(
      fixture === 'long-adversarial'
        ? 'tests/fixtures/long-adversarial.xml'
        : '../tests/fixtures/academic.xml',
    );
    if (fixture === 'five-mib')
      raw = Buffer.from(
        raw
          .toString()
          .replace(
            '</CURRICULO-VITAE>',
            `<!--${'x'.repeat(5 * 1024 * 1024)}--></CURRICULO-VITAE>`,
          ),
      );
    await page.locator('input[type=file]').setInputFiles({
      name: 'fictitious.xml',
      mimeType: 'text/xml',
      buffer: raw,
    });
    await page.getByText('Arquivo validado', { exact: true }).waitFor();
    const parseMs = Date.now() - loadStart;
    await next();
    await next();
    const renderStart = Date.now();
    await page.getByRole('button', { name: 'Gerar PDF' }).click();
    await page.getByRole('heading', { name: 'Seu PDF está pronto' }).waitFor();
    const generatedMs = Date.now() - renderStart;
    const afterRss = rss();
    await page
      .getByRole('button', { name: 'Limpar tudo', exact: true })
      .click();
    await ready();
    result.conversions.push({
      fixture,
      inputBytes: raw.length,
      parseWithWorkerRestartMs: parseMs,
      generatedMs,
      afterRss,
      resetRss: rss(),
    });
  }
  await writeFile(
    '../.local/browser-app-evidence/measurements.json',
    `${JSON.stringify(result, null, 2)}\n`,
  );
  console.log(JSON.stringify(result));
} finally {
  await browser.close();
  await server.close();
}
