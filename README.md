# lattes2pdf

<p align="center">
  <img src="https://raw.githubusercontent.com/mpds/lattes2pdf/main/assets/social-preview.png" alt="lattes2pdf: uma xícara de café ao lado de um documento PDF" width="800">
</p>

Converta seu Currículo Lattes em um CV em PDF, escolhendo o que apresentar e como organizar as informações. Use perfis editáveis para criar versões acadêmicas ou resumidas e temas do [RenderCV](https://rendercv.com) para definir a aparência. O YAML gerado é compatível com o RenderCV e pode ser editado e renderizado diretamente, inclusive com temas personalizados como o [Garamond](https://github.com/mpds/lattes2pdf/tree/main/src/lattes2pdf/themes/garamond), incluído no projeto.

Veja exemplos fictícios: [ModernCV](https://github.com/mpds/lattes2pdf/blob/main/examples/pdfs/moderncv.pdf), nativo do RenderCV, e [Garamond](https://github.com/mpds/lattes2pdf/blob/main/examples/pdfs/garamond.pdf), um tema alternativo criado com o RenderCV e incluído no lattes2pdf.

## Instalação

Requer Python 3.12 ou superior. No Linux ou macOS, instale em um ambiente virtual:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install lattes2pdf
```

O RenderCV é instalado como dependência e a geração usa Typst.

## Do Lattes ao PDF

Na [Plataforma Lattes](https://lattes.cnpq.br/), acesse a edição do seu currículo e procure **Exportar**, escolhendo o formato **XML**. Salve o arquivo baixado: o lattes2pdf aceita tanto o XML quanto o ZIP que o contém, sem precisar descompactá-lo.

![Fluxo: XML ou ZIP do Lattes, perfil opcional e tema entram no lattes2pdf; saem PDF, YAML editável do RenderCV e relatório JSON. O YAML pode ser editado e recompilado pelo RenderCV.](https://raw.githubusercontent.com/mpds/lattes2pdf/main/examples/workflow.png)

O **perfil** seleciona e organiza o conteúdo e o **tema** define a aparência.

## Gerar um currículo

```bash
lattes2pdf render curriculo.xml -o cv.pdf
```

O comando usa o preset `academico`, com o tema `classic` por padrão. Para incluir todos os detalhes conhecidos do currículo sem aplicar o preset, use `--full`.

Isso gera três arquivos:

| Arquivo | Para que serve |
| --- | --- |
| `cv.pdf` | Currículo pronto para visualizar e compartilhar. |
| `cv.yaml` | Conteúdo e configuração visual no formato do RenderCV. |
| `cv.report.json` | Relatório das informações incluídas, omitidas e dos avisos de conversão. |

Para experimentar outro tema, use `--theme garamond` ou um nome listado em `lattes2pdf theme --help`. Use pastas separadas para comparar temas; com temas personalizados, templates e fontes também são copiados junto ao YAML.

Para testar sem o seu Lattes, baixe o [XML fictício](https://raw.githubusercontent.com/mpds/lattes2pdf/main/examples/curriculo.xml) e use-o no lugar de `curriculo.xml`.

## Comece com um perfil

O preset `academico` já é usado por padrão em `render` e `export`. Para escolher outro ou editar suas preferências, copie um preset e use o arquivo na geração:

```bash
lattes2pdf profile essencial -o profile.yaml  # gera o arquivo de configuração
lattes2pdf render curriculo.xml --profile profile.yaml -o essencial.pdf  # usa o perfil personalizado
```

| Preset | Ponto de partida |
| --- | --- |
| `academico` | Cobertura ampla, incluindo bio e informações do trabalho de formação. |
| `essencial` | Bio, formação, experiência e principais seções de produção. |
| `resumido` | Menos seções, sem bio e sem listas de autores. |

Os presets são arquivos YAML editáveis, podendo ser modificados conforme a necessidade.

## Editar o resultado no RenderCV

Abra o `cv.yaml` gerado, ajuste o texto ou a aparência e compile novamente:

```bash
rendercv render cv.yaml --pdf-path cv-editado.pdf
```

O caminho do PDF é relativo à pasta do YAML. Se houver pastas de templates e fontes ao lado dele, mantenha-as junto do arquivo.

Essa edição afeta o documento gerado. Para reaplicar escolhas a uma nova exportação do Lattes, salve-as no `profile.yaml`.

## Escolher o que aparece

Veja as seções e os registros do seu currículo:

```bash
lattes2pdf inspect curriculo.xml
lattes2pdf inspect curriculo.xml --section publications.articles
```

Por exemplo, a publicação do XML fictício aparece assim:

```text
publications.articles — Artigos publicados (1)
  publications.articles:5af5a2d20b36  Catálogos abertos & memória digital (2024)
```

Você pode excluir uma seção inteira ou copiar o ID de um registro específico:

```bash
lattes2pdf render curriculo.xml --exclude awards -o sem-premios.pdf
lattes2pdf render curriculo.xml \
  --exclude-id publications.articles:5af5a2d20b36 -o sem-artigo.pdf
```

Use os IDs retornados pelo seu próprio `inspect`. Eles podem mudar quando o registro é alterado ou ganha duplicatas. As opções `--exclude` e `--exclude-id` podem ser repetidas para remover mais itens.

## Guardar suas preferências

Edite o preset copiado ou crie um `profile.yaml` com apenas as escolhas de que precisa:

```yaml
include: [profile, education, experience, publications]
exclude: [publications.press]
order: [profile, experience, education, publications]
theme: garamond

sections:
  education:
    title: Formação acadêmica
    show_advisors: false
  publications.articles:
    show_authors: true
    show_links: true
```

Para guardar exclusões individuais, acrescente `exclude_ids` com os IDs do `inspect`:

```yaml
exclude_ids:
  - publications.articles:5af5a2d20b36
```

Depois, aplique o arquivo:

```bash
lattes2pdf render curriculo.xml --profile profile.yaml -o personalizado.pdf
```

Descubra os nomes das seções e as opções disponíveis sem precisar conhecer os atributos internos do XML:

```bash
lattes2pdf sections
lattes2pdf sections education
lattes2pdf sections publications.articles
```

Um `--profile` explícito substitui o preset padrão. As opções da linha de comando substituem as correspondentes no perfil. Para filtros por ano, ordenação e outros ajustes, consulte `lattes2pdf render --help`. Use `--force` quando quiser substituir saídas existentes.

## Personalizar um tema

Copie o Garamond para uma pasta editável:

```bash
lattes2pdf theme garamond -o meu-tema
lattes2pdf render curriculo.xml --profile profile.yaml \
  --theme meu-tema/design.yaml -o meu-cv.pdf
```

Edite `design.yaml` para ajustar fonte, margens e espaçamentos; os templates permitem alterar a composição das entradas. Para usar um tema externo, forneça um YAML com o mapa `design` e mantenha a pasta do tema e suas fontes ao lado dele, conforme a [estrutura de temas do RenderCV](https://docs.rendercv.com/user_guide/how_to/override_default_templates/).

Você também pode salvar `theme: meu-tema/design.yaml` no perfil. Nesse caso, o caminho é relativo ao `profile.yaml`.

## Exportação e limites

Para gerar somente o YAML e o relatório, use `lattes2pdf export curriculo.xml -o cv.yaml`. O modo `--full` inclui todos os registros e detalhes conhecidos permitidos pela ferramenta, podendo produzir um documento extenso; ele não é um preset de apresentação e não aceita filtros de seleção.

Dados privados, como documentos pessoais e endereço residencial, não são exportados. Conteúdo desconhecido e omissões aparecem no relatório; no modo `--full`, campos não mapeados impedem a exportação por padrão.

A integração atual usa RenderCV 2.8. Veja [como contribuir](https://github.com/mpds/lattes2pdf/blob/main/CONTRIBUTING.md) e a [licença MIT](https://github.com/mpds/lattes2pdf/blob/main/LICENSE).
