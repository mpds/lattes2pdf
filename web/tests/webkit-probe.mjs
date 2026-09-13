import { webkit } from 'playwright';

const browser = await webkit.launch();
const context = await browser.newContext();
const page = await context.newPage();
await page.goto('http://127.0.0.1:4173/lattes2pdf/');
const probe = () =>
  page.evaluate(
    () =>
      new Promise((resolve) => {
        const url = URL.createObjectURL(
          new Blob(['postMessage("ok")'], { type: 'text/javascript' }),
        );
        const worker = new Worker(url, { type: 'module' });
        worker.onmessage = (e) => {
          worker.terminate();
          URL.revokeObjectURL(url);
          resolve(e.data);
        };
        worker.onerror = (e) => {
          worker.terminate();
          URL.revokeObjectURL(url);
          resolve({ error: e.message, file: e.filename });
        };
      }),
  );
console.log('online blob worker', await probe());
await context.setOffline(true);
console.log('offline blob worker', await probe());
await browser.close();
