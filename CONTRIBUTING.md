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
