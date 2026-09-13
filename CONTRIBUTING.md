# Como contribuir

Use Python 3.12 ou superior. Na raiz do repositório, crie um ambiente virtual
e instale as ferramentas de desenvolvimento:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e . --group dev
```

No Windows, crie o ambiente com `py -3 -m venv .venv` e ative-o pelo PowerShell
com `.venv\Scripts\Activate.ps1`.

## Alterações e verificações

Mantenha cada mudança focada em um problema. Descreva o comportamento alterado
e como ele foi verificado. Ao corrigir uma falha, acrescente um teste de regressão
quando ele proteger um comportamento relevante. Use exemplos fictícios ou
anonimizados para reproduzir problemas de conversão.

Use Ruff para formatar e verificar o código:

```bash
ruff format .
ruff check .
ruff format --check .
pytest
python -m build
python -m twine check --strict dist/*
git diff --check
```

As configurações ficam no `pyproject.toml`. Consulte `lattes2pdf --help` e
o `--help` dos subcomandos para explorar a CLI.

## Commits e releases

Use [Conventional Commits](https://www.conventionalcommits.org/pt-br/v1.0.0/),
com mudanças agrupadas de forma lógica. Exemplos:

```text
feat: adicionar seleção de publicações
fix: preservar datas sem mês informado
docs: esclarecer a exportação do Lattes
```

Tags e títulos de releases devem conter somente a versão no formato `vX.Y.Z`,
por exemplo, `v0.1.0`. Descreva as mudanças no corpo da release. A versão do
pacote correspondente é `0.1.0`, sem o prefixo `v`.

O CI testa Python 3.12 e 3.14 em Linux e Python 3.14 em macOS. Em Python 3.14,
também instala o wheel em um ambiente limpo e gera PDFs fora do checkout, incluindo
um tema externo e a recompilação de um YAML editado. O script `.github/scripts/check_distribution.py`
também pode ser executado localmente, recebendo o wheel e um XML fictício.

### Publicação

Configure Trusted Publishing nas contas do PyPI e do TestPyPI: projeto
`lattes2pdf`, proprietário `mpds`, repositório `lattes2pdf`, workflow `release.yml`.
Use o ambiente GitHub `pypi` para PyPI e `testpypi` para TestPyPI. Não são necessários
tokens de API no repositório.

1. Atualize a versão em `pyproject.toml` e confira as alterações da release.
2. Execute manualmente o workflow **Publicação** para ensaiar no TestPyPI.
3. Confira a página e a instalação da versão no TestPyPI.
4. Crie a release com tag e título `vX.Y.Z`, descrevendo mudanças e limitações no corpo.

Publicar a release no GitHub dispara uma nova validação e a publicação no PyPI.
O workflow confere a versão da tag e publica somente os artefatos que passaram
nos testes; depois anexa wheel e sdist à release. Cada versão publicada é imutável:
para mudar seu conteúdo, incremente a versão. Um rascunho de release não publica
o pacote.
