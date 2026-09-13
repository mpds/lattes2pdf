import * as compilerWrapper from '@myriaddreamin/typst-ts-web-compiler';
import type { PyodideAPI } from 'pyodide';
import type { Bundle } from './assets';
import type { Result } from './engine';

let python: PyodideAPI;
let compiler: compilerWrapper.TypstCompiler;
const decoder = new TextDecoder();
const virtualBase = 'https://runtime.invalid/';

async function initialize(bundle: Bundle) {
  const { files, manifest } = bundle;
  const bytes = (path: string): Uint8Array<ArrayBuffer> => {
    const value = files.get(path);
    if (!value) throw new Error(`Recurso não incluído: ${path}`);
    return value as Uint8Array<ArrayBuffer>;
  };
  // Serve only trusted in-memory bytes. There is no network fallback, including
  // during restart after Cancel/Clear. Blob modules inherit the document CSP.
  globalThis.fetch = async (input) => {
    const url =
      typeof input === 'string'
        ? input
        : input instanceof URL
          ? input.href
          : input.url;
    if (!url.startsWith(virtualBase))
      throw new Error('Acesso externo bloqueado.');
    const path = url.slice(virtualBase.length);
    return new Response(bytes(path), {
      headers: {
        'Content-Type': path.endsWith('.wasm')
          ? 'application/wasm'
          : 'application/octet-stream',
      },
    });
  };
  const moduleUrls: string[] = [];
  const module = async (path: string) => {
    const url = URL.createObjectURL(
      new Blob([bytes(path)], { type: 'text/javascript' }),
    );
    moduleUrls.push(url);
    return import(/* @vite-ignore */ url);
  };
  try {
    const { loadPyodide } = await module('pyodide/pyodide.mjs');
    const { default: createPyodideModule } = await module(
      'pyodide/pyodide.asm.mjs',
    );
    python = await loadPyodide({
      indexURL: `${virtualBase}pyodide/`,
      packageBaseUrl: `${virtualBase}pyodide/`,
      lockFileContents: decoder.decode(bytes('pyodide/pyodide-lock.json')),
      createPyodideModule: (settings: object) =>
        createPyodideModule({
          ...settings,
          wasmBinary: bytes('pyodide/pyodide.asm.wasm'),
        }),
      stdout: () => {},
      stderr: () => {},
    });
    await python.loadPackage(manifest.packages, {
      messageCallback: () => {},
      errorCallback: () => {},
    });
    const site = python.runPython(
      'import site; site.getsitepackages()[0]',
    ) as string;
    for (const asset of manifest.assets.filter((a) => a.kind === 'wheel'))
      python.unpackArchive(bytes(asset.path), 'zip', { extractDir: site });
    python.unpackArchive(bytes('application.zip'), 'zip', { extractDir: site });
    python.runPython('import browser_adapter');
  } finally {
    for (const url of moduleUrls) URL.revokeObjectURL(url);
  }
  await compilerWrapper.default({ module_or_path: bytes('compiler.wasm') });
  const builder = new compilerWrapper.TypstCompilerBuilder();
  for (const asset of manifest.assets.filter((a) => a.kind === 'font'))
    await builder.add_raw_font(bytes(asset.path));
  const packages = new Map(
    manifest.assets
      .filter((a) => a.kind === 'typst-package')
      .map((a) => [`/${a.path}`, bytes(a.path)]),
  );
  await builder.set_access_model(
    packages,
    () => 0,
    (path: string) => packages.has(path),
    (path: string) => path,
    (path: string) => packages.get(path),
  );
  await builder.set_package_registry(
    packages,
    ({
      namespace,
      name,
      version,
    }: {
      namespace: string;
      name: string;
      version: string;
    }) => {
      const path = `/packages/${namespace}/${name}/${version}`;
      return packages.has(`${path}/typst.toml`) ? path : undefined;
    },
  );
  compiler = await builder.build();
  const adapter = python.pyimport('browser_adapter');
  try {
    postMessage({ type: 'ready', catalog: JSON.parse(adapter.catalog_data()) });
  } finally {
    adapter.destroy();
  }
}

globalThis.onmessage = async ({ data }) => {
  try {
    if (data.type === 'init') return await initialize(data.bundle);
    if (data.type !== 'request') return;
    const { id, method, payload } = data;
    const adapter = python.pyimport('browser_adapter');
    let result: Result & { error?: string; code?: string; typst?: string };
    try {
      if (method === 'generate')
        postMessage({ type: 'status', id, text: 'Preparando o currículo…' });
      result = JSON.parse(
        adapter.call(
          method === 'generate' ? 'prepare' : method,
          typeof payload === 'object' && !(payload instanceof Uint8Array)
            ? JSON.stringify(payload)
            : payload,
        ),
      );
    } finally {
      adapter.destroy();
    }
    if (result?.error) {
      postMessage({
        type: 'error',
        id,
        message: result.error,
        code: result.code,
      });
      return;
    }
    if (method === 'generate') {
      if (result.empty) {
        postMessage({
          type: 'error',
          id,
          code: 'empty',
          message:
            'Não há conteúdo nas categorias e períodos selecionados. Volte e ajuste suas escolhas.',
        });
        return;
      }
      postMessage({ type: 'status', id, text: 'Compondo o PDF…' });
      compiler.add_source('/main.typ', result.typst!);
      const world = compiler.snapshot(undefined, '/main.typ');
      let output: { result?: Uint8Array<ArrayBuffer> };
      try {
        output = world.get_artifact(1, 3);
      } finally {
        world.free();
      }
      delete result.typst;
      if (
        !output.result ||
        decoder.decode(output.result.subarray(0, 5)) !== '%PDF-'
      ) {
        postMessage({
          type: 'error',
          id,
          code: 'compile',
          message:
            'Não foi possível compor o PDF. Tente outro tema ou utilize a CLI.',
        });
        return;
      }
      result.pdf = output.result;
      postMessage(
        { type: 'result', id, result },
        { transfer: [result.pdf.buffer] },
      );
    } else postMessage({ type: 'result', id, result });
  } catch {
    // Python/compiler errors can contain CV content; never emit them to logs.
    postMessage({
      type: 'error',
      id: data.id,
      code: 'runtime',
      message:
        'Não foi possível concluir a operação. Selecione o arquivo novamente ou tente um navegador desktop atualizado.',
    });
  }
};
