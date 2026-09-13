import { type Bundle, loadAssets } from './assets';
import ConversionWorker from './worker?worker&inline';

export interface Settings {
  model: string;
  basis: string;
  categories: string[];
  theme: string;
  bibliography: string;
  informed: boolean;
  etAl: boolean;
  professional: number | null;
  production: number | null;
  language: string;
}
export interface Catalog {
  categories: { key: string; label: string }[];
  presets: Record<string, string[]>;
  themes: string[];
}
export interface Result {
  name: string;
  yaml: string;
  report: { issues: { level: string; message: string }[] };
  empty: boolean;
  pdf: Uint8Array<ArrayBuffer>;
}
export class TaskError extends Error {
  constructor(
    message: string,
    readonly code = 'runtime',
  ) {
    super(message);
  }
}

/** One worker per document. Only trusted asset bytes survive its termination. */
export class Engine {
  private bundle?: Bundle;
  private worker?: Worker;
  private imageUrls = new Map<string, string>();
  private ready?: Promise<Catalog>;
  private generation = 0;
  private nextJob = 0;
  private pending = new Map<
    number,
    {
      resolve: (value: unknown) => void;
      reject: (error: Error) => void;
      timer: ReturnType<typeof setTimeout>;
    }
  >();
  private rejectReady?: (error: Error) => void;
  private initializationTimer?: ReturnType<typeof setTimeout>;
  private assets = loadAssets().then((bundle) => (this.bundle = bundle));
  onStatus: (text: string) => void = () => {};

  async start(): Promise<Catalog> {
    if (this.ready) return this.ready;
    const generation = this.generation;
    this.ready = this.assets.then(
      (bundle) =>
        new Promise<Catalog>((resolve, reject) => {
          if (generation !== this.generation)
            return reject(new TaskError('Operação cancelada.', 'cancelled'));
          this.rejectReady = reject;
          const worker = new ConversionWorker();
          this.worker = worker;
          const timer = setTimeout(() => {
            if (generation === this.generation)
              this.stop(
                new TaskError(
                  'O navegador demorou demais para preparar os recursos. Tente novamente.',
                  'timeout',
                ),
              );
          }, 120000);
          this.initializationTimer = timer;
          worker.onerror = () => {
            clearTimeout(timer);
            if (generation === this.generation)
              this.stop(
                new TaskError(
                  'O navegador não conseguiu executar a conversão. Tente um navegador desktop atualizado.',
                  'runtime',
                ),
              );
          };
          worker.onmessage = ({ data }) => {
            if (generation !== this.generation) return;
            if (data.type === 'ready') {
              clearTimeout(timer);
              this.rejectReady = undefined;
              resolve(data.catalog);
              return;
            }
            if (data.type === 'status') {
              if (this.pending.has(data.id)) this.onStatus(data.text);
              return;
            }
            const task = this.pending.get(data.id);
            if (data.type === 'error' && !task) {
              clearTimeout(timer);
              this.stop(new TaskError(data.message, data.code));
              return;
            }
            if (!task) return;
            clearTimeout(task.timer);
            this.pending.delete(data.id);
            if (data.type === 'error')
              task.reject(new TaskError(data.message, data.code));
            else task.resolve(data.result);
          };
          worker.postMessage({ type: 'init', bundle });
        }),
    );
    return this.ready;
  }

  async request<T>(method: string, payload?: unknown): Promise<T> {
    const generation = this.generation;
    await this.start();
    if (generation !== this.generation)
      throw new TaskError('Operação cancelada.', 'cancelled');
    if (this.pending.size) throw new TaskError('Aguarde a operação atual.');
    const id = ++this.nextJob;
    return new Promise<T>((resolve, reject) => {
      const timer = setTimeout(
        () =>
          this.stop(
            new TaskError(
              'A operação excedeu o tempo limite. Tente um arquivo menor ou utilize a CLI.',
              'timeout',
            ),
          ),
        method === 'generate' ? 120000 : 30000,
      );
      this.pending.set(id, {
        resolve: (value) => resolve(value as T),
        reject,
        timer,
      });
      const transferable =
        payload instanceof Uint8Array ? [payload.buffer as ArrayBuffer] : [];
      this.worker!.postMessage(
        { type: 'request', id, method, payload },
        transferable,
      );
    });
  }

  assetUrl(path: string): string {
    if (!this.bundle) return `${import.meta.env.BASE_URL}generated/${path}`;
    let value = this.imageUrls.get(path);
    if (!value) {
      const bytes = this.bundle.files.get(path);
      if (!bytes) throw new TaskError('Imagem de exemplo indisponível.');
      value = URL.createObjectURL(
        new Blob([bytes as Uint8Array<ArrayBuffer>], { type: 'image/png' }),
      );
      this.imageUrls.set(path, value);
    }
    return value;
  }

  example(): Uint8Array<ArrayBuffer> {
    return new Uint8Array(this.bundle!.files.get('example.xml')!);
  }

  stop(reason = new TaskError('Operação cancelada.', 'cancelled')) {
    this.generation++;
    clearTimeout(this.initializationTimer);
    this.initializationTimer = undefined;
    this.worker?.terminate();
    this.worker = undefined;
    this.rejectReady?.(reason);
    this.rejectReady = undefined;
    for (const task of this.pending.values()) {
      clearTimeout(task.timer);
      task.reject(reason);
    }
    this.pending.clear();
    this.ready = undefined;
  }
}
