import {
  getDocument,
  type PDFDocumentProxy,
  PDFWorker,
  type RenderTask,
} from 'pdfjs-dist';
import workerSource from 'pdfjs-dist/build/pdf.worker.min.mjs?raw';

/** Only locally generated PDF bytes enter this viewer; no URLs or annotations. */
export function createPreview(bytes: Uint8Array<ArrayBuffer>) {
  const element = document.createElement('section');
  element.className = 'pdf-preview';
  const status = document.createElement('p');
  status.setAttribute('role', 'status');
  status.textContent = 'Preparando a prévia…';
  const canvas = document.createElement('canvas');
  canvas.setAttribute('role', 'img');
  const accessibleText = document.createElement('p');
  accessibleText.className = 'sr-only';
  const controls = document.createElement('div');
  controls.className = 'preview-controls';
  const previous = document.createElement('button');
  previous.type = 'button';
  previous.className = 'secondary';
  previous.textContent = 'Página anterior';
  previous.disabled = true;
  const next = document.createElement('button');
  next.type = 'button';
  next.className = 'secondary';
  next.textContent = 'Próxima página';
  next.disabled = true;
  controls.append(previous, next);
  element.append(status, canvas, accessibleText, controls);
  const sourceUrl = URL.createObjectURL(
    new Blob(
      [
        'globalThis.fetch = async () => { throw new Error("Recursos externos não são permitidos na prévia."); };\n',
        workerSource,
      ],
      { type: 'text/javascript' },
    ),
  );
  const port = new Worker(sourceUrl, { type: 'module' });
  const worker = PDFWorker.create({ port, verbosity: 0 });
  const loading = getDocument({
    data: new Uint8Array(bytes),
    worker,
    verbosity: 0,
    useWorkerFetch: false,
    useWasm: false,
    disableFontFace: true,
    useSystemFonts: false,
    isOffscreenCanvasSupported: false,
    isImageDecoderSupported: false,
    enableXfa: false,
    stopAtErrors: true,
  });
  let pdf: PDFDocumentProxy;
  let pageNumber = 1;
  let closed = false;
  let rendering: RenderTask | undefined;
  async function renderPage() {
    previous.disabled = next.disabled = true;
    status.textContent = 'Preparando a página…';
    try {
      const page = await pdf.getPage(pageNumber);
      if (closed) return;
      const viewport = page.getViewport({ scale: 1.5 });
      canvas.width = Math.ceil(viewport.width);
      canvas.height = Math.ceil(viewport.height);
      rendering = page.render({ canvas, viewport, annotationMode: 0 });
      await rendering.promise;
      if (closed) return;
      const content = await page.getTextContent();
      if (closed) return;
      accessibleText.textContent = content.items
        .map((item) => ('str' in item ? item.str : ''))
        .join(' ');
      canvas.setAttribute(
        'aria-label',
        `Página ${pageNumber} de ${pdf.numPages} do currículo`,
      );
      status.textContent = `Página ${pageNumber} de ${pdf.numPages}`;
      previous.disabled = pageNumber === 1;
      next.disabled = pageNumber === pdf.numPages;
      page.cleanup();
    } catch {
      if (!closed)
        status.textContent =
          'Não foi possível exibir a prévia. Baixe o PDF para abri-lo.';
    }
  }
  previous.onclick = () => {
    pageNumber--;
    void renderPage();
  };
  next.onclick = () => {
    pageNumber++;
    void renderPage();
  };
  void loading.promise
    .then((value) => {
      pdf = value;
      if (!closed) void renderPage();
    })
    .catch(() => {
      if (!closed)
        status.textContent =
          'Não foi possível exibir a prévia. Baixe o PDF para abri-lo.';
    });
  return {
    element,
    dispose() {
      closed = true;
      rendering?.cancel();
      void loading.destroy().catch(() => {});
      worker.destroy();
      port.terminate();
      URL.revokeObjectURL(sourceUrl);
      canvas.width = canvas.height = 0;
      accessibleText.textContent = '';
    },
  };
}
