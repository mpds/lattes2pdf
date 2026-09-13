export interface Asset {
  path: string;
  sha256: string;
  size: number;
  kind: string;
}
export interface Manifest {
  pyodide: string;
  packages: string[];
  assets: Asset[];
}
export interface Bundle {
  manifest: Manifest;
  files: Map<string, Uint8Array>;
}

export async function loadAssets(): Promise<Bundle> {
  const base = `${import.meta.env.BASE_URL}generated/`;
  const response = await fetch(`${base}manifest.json`, { credentials: 'omit' });
  if (!response.ok)
    throw new Error(
      'Não foi possível carregar os recursos. Reabra a página com conexão.',
    );
  const manifest: Manifest = await response.json();
  const files = new Map<string, Uint8Array>();
  // Bounded concurrency keeps initialization predictable on slower devices.
  const pending = [...manifest.assets];
  await Promise.all(
    Array.from({ length: 6 }, async () => {
      while (pending.length) {
        const asset = pending.shift()!;
        const result = await fetch(base + asset.path, { credentials: 'omit' });
        if (!result.ok)
          throw new Error(
            'Um recurso está indisponível. Reabra a página com conexão.',
          );
        const bytes = new Uint8Array(await result.arrayBuffer());
        const hash = Array.from(
          new Uint8Array(await crypto.subtle.digest('SHA-256', bytes)),
          (x) => x.toString(16).padStart(2, '0'),
        ).join('');
        if (hash !== asset.sha256)
          throw new Error(
            'Os recursos estão incompletos. Recarregue a página.',
          );
        files.set(asset.path, bytes);
      }
    }),
  );
  return { manifest, files };
}
