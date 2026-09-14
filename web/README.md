# lattes2pdf no navegador

Converta exportações XML ou ZIP do Currículo Lattes em PDF, escolhendo o conteúdo
e o tema. O processamento acontece no navegador, sem enviar o currículo a um servidor.

## Executar localmente

Requisitos: Node 24, Python 3.12+ e Poppler (`pdftoppm` no PATH).
Prepare o ambiente `.venv` conforme [CONTRIBUTING.md](../CONTRIBUTING.md).
Depois, na raiz do repositório:

```bash
cd web
npm ci
../.venv/bin/python scripts/samples.py
npm run dev
```

Abra o endereço indicado pelo Vite, normalmente
[http://127.0.0.1:5173/lattes2pdf/](http://127.0.0.1:5173/lattes2pdf/).
A primeira preparação precisa de conexão. Após alterar o código Python,
execute `npm run bundle` e recarregue a página.

## Build e prévia

A partir de `web/`:

```bash
npm run build
npm run preview
```

A prévia fica em [http://127.0.0.1:4173/lattes2pdf/](http://127.0.0.1:4173/lattes2pdf/).
Os arquivos estáticos são gerados em `web/dist/`.

## Validação

Com a prévia em execução, em outro terminal dentro de `web/`:

```bash
npm run lint
npm run typecheck
PLAYWRIGHT_BROWSERS_PATH=.cache/browsers npx playwright install chromium firefox webkit
PLAYWRIGHT_BROWSERS_PATH=.cache/browsers npm test
../.venv/bin/pytest tests/test_adapter.py -q
```

Consulte os [avisos de terceiros](third-party/README.md) para informações sobre licenças.
