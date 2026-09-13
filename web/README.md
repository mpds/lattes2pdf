# lattes2pdf no navegador

Aplicação estática em português: Modelo → Arquivo → Tema e preferências → PDF.
Converte XML/ZIP com o core Python existente, RenderCV e Typst, inteiramente no
navegador. Os nove temas, seleção das 33 categorias, ABNT/Chicago, preferências
bibliográficas, períodos independentes, configurações simples, prévia e downloads
funcionam sem um servidor de conversão. O core e a CLI não foram alterados.

## Preparação local

Requisitos: Node **24** (testado 24.15.0 / npm 11.12.1), Python **3.12+**,
`venv` e Poppler com `pdftoppm` no PATH. A validação usou macOS 26.6.2 arm64.
Instale Poppler pelo gerenciador de pacotes do sistema, se necessário.
As primeiras instalações, o bundle e a geração das miniaturas precisam de rede.
Não use currículos reais como fixtures ou miniaturas.

Na raiz do repositório, seguindo `CONTRIBUTING.md`:

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -e . --group dev
.venv/bin/python -m build
cd web
npm ci
../.venv/bin/python -m venv .cache/native
.cache/native/bin/python -m pip install -r requirements-native.txt
.cache/native/bin/python -m pip install --no-deps ../dist/lattes2pdf-0.2.0-py3-none-any.whl
.cache/native/bin/python scripts/samples.py
npm run build
npm run preview
```

Abra **http://127.0.0.1:4173/lattes2pdf/**. `Ctrl+C` encerra a prévia.
Os comandos acima usam nomes de executáveis POSIX; no Windows, os executáveis
Python do ambiente ficam em `Scripts/`.

`npm run build` refaz o bundle do core/adaptador e produz `dist/`. Exige as nove
miniaturas geradas por `samples.py`; arquivos extras da pasta de miniaturas não
são incluídos. O servidor de prévia usa somente `dist/`, escuta em loopback e não
oferece conversão, cabeçalhos especiais ou fallback de rotas. A base é sempre
`/lattes2pdf/`. Não abra `index.html` diretamente por `file://`.

Para desenvolvimento, após a preparação:

```bash
npm run dev
```

O Vite fornece o endereço local, normalmente `http://127.0.0.1:5173/lattes2pdf/`.
Depois de editar Python ou recursos do core, execute `npm run bundle` e recarregue
a página. Alterações no conjunto de fontes/temas exigem refazer as miniaturas.
O script `bundle.py --refresh-lock` é reservado para revisão explícita de
atualizações de dependências; o build normal usa URLs e hashes fixados.

## Runtime e privacidade

- Pyodide **314.0.6**, Python **3.14.2**; RenderCV **2.8**, Pydantic **2.12.5**,
  pydantic-core **2.41.5**, rendercv-fonts **0.5.1**.
- `@myriaddreamin/typst-ts-web-compiler` **0.7.0**, com Typst **0.14.2**;
  pacotes Typst RenderCV **0.3.0** e fontawesome **0.6.0**. A base nativa usa
  Python **3.12.13**, `typst==0.14.8` (mesmo Typst 0.14.2), fontes e dependências
  Python de renderização alinhadas. `requirements-native.txt` fixa esse ambiente.
- Prévia local com PDF.js **6.3.289**, canvas e navegação por páginas; sem executar
  ações/anotações, buscar URLs do documento ou carregar fontes remotas.
- Vite **8.3.0**, TypeScript **5.9.3**, Biome **2.5.13**, Playwright **1.63.0**.
  Não há framework de interface, backend, serviço de análise ou service worker.

O build empacota o core sem editar uma cópia. `python/browser_adapter.py` reutiliza
parsing, seleção e exportação; chama as APIs internas de modelo/template do
RenderCV. Atualizações dessas dependências precisam repetir as comparações.
`scripts/compiler-csp.ts` substitui apenas callbacks fixos do wrapper WASM por
funções estáticas, com verificações que falham se o código upstream mudar.
A CSP permite execução WASM e workers Blob; bloqueia avaliação dinâmica de JS,
frames e objetos. Os workers do compilador e da prévia só resolvem bytes locais.

“Recursos prontos · conversão disponível offline” significa que o runtime,
todos os temas/fontes/pacotes e a prévia já estão disponíveis na sessão. Depois
disso, trocar de tema, cancelar, limpar, abrir outro arquivo e importar/exportar
configurações não precisam de rede. Reabrir ou recarregar pode exigir conexão.
O JavaScript inclui o worker da prévia antecipadamente por esse motivo; o aviso
de tamanho de chunk do Vite é esperado (aproximadamente 1,75 MB, 525 KB gzip).

Documentos entram apenas no worker e no filesystem em memória. A aplicação não
usa localStorage, sessionStorage, IndexedDB, cookies nem Cache Storage para
salvar dados. Downloads são ações explícitas. Cancelar/Limpar encerra o worker,
invalida trabalhos anteriores e remove resultados, prévias e URLs de download;
recursos públicos permanecem em memória para outra conversão offline. Não há
recuperação automática de currículo ao retornar pelo histórico.

## Limites e cobertura local

XML/ZIP: **25 MiB**, inclusive XML descompactado; ZIP: **1.000 entradas**, somente
armazenamento/Deflate, sem senha, links simbólicos ou caminhos inseguros. XML:
**200.000 elementos**, profundidade máxima **128** conforme o core, sem DTD ou
entidades. Perfis: **64 KiB**, somente o subconjunto representável pela interface;
opções avançadas são recusadas com indicação da CLI. Preparação e composição:
**120 segundos**; leitura/validação: **30 segundos**. Cancelar termina trabalho
síncrono sem bloquear a interface.

Esses limites são tetos de segurança, não garantia de conversão de todo arquivo
nesse tamanho. No Mac17,4 / Apple M5 / 32 GiB, Chromium 153, uma medição local
registrou 2,36 s até prontidão, 2,3–2,6 s para abrir arquivo incluindo reinício do
worker, e 207–311 ms para PDFs de exemplo de uma a três páginas. A soma do RSS
dos processos do navegador ficou em aproximadamente **1,0–1,3 GB**, incluindo o
navegador e possível memória compartilhada contada mais de uma vez. O ensaio de
5 MiB continha um comentário XML grande; não simula milhares de registros. A
coleta de memória do navegador não é imediata após Limpar.

O artefato medido tem cerca de **71,25 MB** sem compressão e **36,36 MB** estimados
com gzip por arquivo. A prévia Python serve sem compressão; esses tempos de
loopback não estimam o tempo de download pela internet.

Verificados Chromium **153.0.8010.12**, Firefox **155.0** e WebKit **26.6** via
Playwright, com largura desktop e 390 px, foco/teclado, downloads e prévia real.
WebKit automatizado **não é Safari**. Safari nativo, Edge e aparelhos Android/iOS
não foram verificados neste ambiente; desempenho móvel permanece experimental.
O controle nativo de aplicativos estava indisponível por permissão do ambiente.

Nos três motores, os testes bloqueiam todo HTTP(S) após a prontidão. Chromium e
Firefox também usam o modo offline do navegador. No WebKit do Playwright, esse
modo bloqueia até um worker Blob trivial; nele o teste usa bloqueio de transporte,
sem bloquear execução local. `tests/webkit-probe.mjs` preserva a reprodução.

Há uma limitação herdada de RenderCV 2.8/CLI: certos símbolos de marcação no nome
usado no cabeçalho produzem erro de composição. O teste com `#panic(...)` confirma
falha segura e recuperação, sem execução nem PDF antigo. Não foi alterado o core
para corrigir essa limitação. Texto semelhante a código em títulos longos aparece
literalmente nos PDFs comparados.

## Validação

Com a prévia de produção em execução, a partir de `web/`:

```bash
npm run lint
npm run typecheck
PLAYWRIGHT_BROWSERS_PATH=.cache/browsers npx playwright install chromium firefox webkit
PLAYWRIGHT_BROWSERS_PATH=.cache/browsers npm test
../.venv/bin/pytest tests/test_adapter.py -q
PLAYWRIGHT_BROWSERS_PATH=.cache/browsers npm run test:parity
.cache/native/bin/python scripts/check_parity.py
npm run check:artifacts
```

`tests/parity.mjs` captura downloads reais offline da interface: 3 presets × 9
temas, casos de autores/referências/períodos e documento longo nos nove temas.
`check_parity.py` recompila os YAMLs pela CLI, compara YAML/relatório/texto, ações
PDF, tamanho e número de páginas, e imagens de **todas** as páginas a 100 dpi.
O conjunto local teve **41 PDFs / 63 páginas**, sem pixels diferentes. Os testes
web também cobrem ZIP com escolha de XML, Latin-1, erros/limites, CSP, perfis,
cancelamento durante composição, segunda conversão offline, histórico e armazenamento.
A inspeção visual complementa essas verificações.

Os resultados, PDFs fictícios, PNGs e medições ficam em
`../.local/browser-app-evidence/`; relatórios temporários de testes e runtimes
ficam em pastas ignoradas. `tests/measure.mjs` mede tempos e RSS em macOS usando
somente fixtures fictícias e processos do navegador que ele próprio iniciou.

Na raiz, execute também os checks de `CONTRIBUTING.md`:

```bash
.venv/bin/ruff check .
.venv/bin/ruff format --check .
.venv/bin/pytest -q
.venv/bin/python -m build
.venv/bin/python -m twine check --strict dist/*
git diff --check
```

## Arquivos e distribuição

Somente `web/dist/` é o artefato estático. O build usa uma lista explícita de
fontes, recursos do core, exemplo fictício, branding e miniaturas. O manifesto
registra hashes/tamanhos; `check:artifacts` confere conteúdo e ausência de arquivos
locais no site e nas distribuições Python. Nenhuma dependência web integra o
pacote da CLI. Não há workflow de publicação neste trabalho.

Os avisos de terceiros acompanham `dist/generated/licenses/`, os wheels e fontes.
Veja [third-party/README.md](third-party/README.md) para origens e limites do
levantamento. A licença Fontin permite embedding e restringe redistribuição;
não foi encontrada autorização separada para servir seus OTF a terceiros. Isso
precisa ser resolvido **antes de eventual publicação**, que está fora deste
trabalho local. Cabeçalhos, conta, origem e comportamento de um host público
não foram configurados ou verificados.
