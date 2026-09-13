# lattes2pdf

<p align="center">
  <img src="https://raw.githubusercontent.com/mpds/lattes2pdf/main/assets/social-preview.png" alt="lattes2pdf: uma xícara de café ao lado de um documento PDF" width="800">
</p>

Converta seu Currículo Lattes em um CV em PDF, escolhendo o que apresentar e como organizar as informações. Use perfis editáveis para criar versões acadêmicas ou resumidas e temas do [RenderCV](https://rendercv.com) para definir a aparência. O YAML gerado é compatível com o RenderCV e pode ser editado e renderizado diretamente, inclusive com temas personalizados pelo usuário.

Veja [exemplos fictícios nos nove temas do RenderCV](https://github.com/mpds/lattes2pdf/blob/main/examples/README.md).

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

O comando usa o preset `resumido`, com o tema `classic` por padrão. Para incluir todos os detalhes conhecidos do currículo sem aplicar um preset, use `--full`.

Esse comando gera três arquivos:

| Arquivo | Para que serve |
| --- | --- |
| `cv.pdf` | Currículo pronto para visualizar e compartilhar. |
| `cv.yaml` | Conteúdo e configuração visual no formato do RenderCV. |
| `cv.report.json` | Relatório das informações incluídas, omitidas e dos avisos de conversão. |

Para experimentar outro tema, use `--theme moderncv` ou um nome listado em `lattes2pdf theme --help`. Todos os nove temas nativos do RenderCV 2.8 estão disponíveis. Use pastas separadas para comparar temas; com temas personalizados, templates e fontes também são copiados junto ao YAML.

Para testar sem o seu Lattes, baixe o [XML fictício](https://raw.githubusercontent.com/mpds/lattes2pdf/main/examples/curriculo.xml) e use-o no lugar de `curriculo.xml`.

## Comece com um perfil

O preset `resumido` já é usado por padrão em `render` e `export`. Os presets seguem a seleção de categorias dos modelos de exportação presentes na plataforma Lattes. Para escolher outro ou editar suas preferências, copie um preset e use o arquivo na geração:

```bash
lattes2pdf profile ampliado -o profile.yaml  # gera o arquivo de configuração
lattes2pdf render curriculo.xml --profile profile.yaml -o ampliado.pdf  # usa o perfil personalizado
```

| Preset | Ponto de partida |
| --- | --- |
| `resumido` | Formação, atuação profissional e categorias de produção do modelo Resumido do Lattes; sem endereço. É o padrão. |
| `ampliado` | Resumido com endereço, idiomas, prêmios e áreas de atuação. |
| `completo` | Todas as categorias de conteúdo, incluindo licenças, projetos, patentes, inovação e divulgação científica; com endereço. |

* Os três são arquivos YAML editáveis e aceitam exclusões, filtros e ajustes por seção.
* O preset `completo` é diferente de `--full`.
* Nenhum preset limita páginas, anos ou quantidade de registros.

## Categorias do Lattes

Liste as seções do currículo e consulte os grupos e possíveis ajustes de cada uma delas:

```bash
lattes2pdf sections
lattes2pdf sections lattes.formacao
```

Por exemplo, `lattes.formacao` reúne `education` (formação acadêmica) e `training` (formação complementar). Veja os grupos e registros presentes no seu currículo:

```bash
lattes2pdf inspect curriculo.xml --section lattes.formacao
```

Você pode combinar categorias e grupos no arquivo de configuração do perfil. Para manter a formação acadêmica e omitir a complementar:

```yaml
include: [profile, lattes.formacao, lattes.atuacao, lattes.artigos]
exclude: [training]
```

Endereço também é uma categoria: use `lattes.endereco` em `include` ou `exclude`. Por exemplo, para gerar um currículo sem endereço a partir do seu perfil:

```bash
lattes2pdf render curriculo.xml --profile profile.yaml --exclude lattes.endereco -o cv.pdf
```

## Editar o resultado no RenderCV

Abra o `cv.yaml` gerado, ajuste o texto ou a aparência e compile novamente:

```bash
rendercv render cv.yaml --pdf-path cv-editado.pdf
```

O caminho do PDF é relativo à pasta do YAML. Se houver pastas de templates e fontes ao lado dele, mantenha-as junto do arquivo.

Essa edição afeta o documento gerado. Para repetir as escolhas em novas exportações, salve as de conteúdo no `profile.yaml` e as visuais no `design.yaml`.

## Escolher o que aparece

Veja as seções e os registros do seu currículo:

```bash
lattes2pdf inspect curriculo.xml
lattes2pdf inspect curriculo.xml --section lattes.artigos
```

Por exemplo, a publicação do XML fictício aparece assim:

```text
publications.articles — Artigos publicados (1)
  publications.articles:5af5a2d20b36  Catálogos abertos & memória digital (2024)
```

Use o nome de um grupo para excluí-lo inteiro ou copie o ID de um registro específico:

```bash
lattes2pdf render curriculo.xml --exclude training -o sem-formacao-complementar.pdf
lattes2pdf render curriculo.xml \
  --exclude-id publications.articles:5af5a2d20b36 -o sem-artigo.pdf
```

Use os IDs retornados pelo seu próprio `inspect`. As opções `--exclude` e `--exclude-id` podem ser repetidas para remover mais itens.

## Guardar suas preferências

Edite o preset copiado ou crie um `profile.yaml` com apenas as escolhas de que precisa:

```yaml
include: [profile, lattes.formacao, lattes.atuacao, lattes.artigos]
exclude: [training]
order: [profile, lattes.atuacao, lattes.formacao, lattes.artigos]
theme: moderncv

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

Consulte os possíveis ajustes de uma categoria ou diretamente de um grupo mostrado pelo `inspect`:

```bash
# exemplos
lattes2pdf sections lattes.formacao
lattes2pdf sections publications.articles
lattes2pdf sections profile
lattes2pdf sections lattes.anais
lattes2pdf sections lattes.patentes
```

Um `--profile` explícito substitui o preset padrão, e as opções da linha de comando tem precedência sobre o arquivo de perfil. Para filtros por ano, ordenação e outros ajustes, consulte `lattes2pdf render --help`. Use `--force` quando quiser substituir saídas existentes.

## Mensagens e diagnósticos

As mensagens usam os níveis `DEBUG`, `INFO`, `WARNING` e `ERROR`, com padrão `INFO`. Elas vão para `stderr`; o resultado do comando, como o inventário ou JSON, fica em `stdout`.

Use `--log-level DEBUG` para detalhes técnicos e caminhos XML, ou `--log-level ERROR` para mostrar somente erros. O nível não remove diagnósticos do JSON ou do relatório.

```bash
lattes2pdf inspect curriculo.zip --section lattes.formacao --log-level DEBUG
lattes2pdf render curriculo.zip -o cv.pdf --log-level ERROR
```

No `inspect`, `--section` filtra os registros e seus diagnósticos, preservando problemas globais do arquivo. O relatório de `export`/`render` mantém todos os diagnósticos, inclusive os de registros excluídos.

## Temas personalizados com RenderCV

O perfil e o tema podem ser usados juntos. Escolha onde fazer cada ajuste:

| Quero modificar… | Onde ajustar |
| --- | --- |
| Registros incluídos, filtros por ano, ordem e títulos das seções, exibição de orientadores ou autores | `profile.yaml` |
| Fontes, cores, margens e espaçamentos | `design.yaml` do tema |
| Composição dos blocos e estrutura visual além das opções de design | Templates de um tema personalizado do RenderCV |

Para começar com a configuração de um tema nativo:

```bash
lattes2pdf theme classic -o meu-tema
```

Consulte as [opções de design](https://docs.rendercv.com/user_guide/yaml_input_structure/design/) e o [guia oficial para criar temas e personalizar templates](https://docs.rendercv.com/user_guide/how_to/override_default_templates/) do RenderCV.

Para usar seu tema no lattes2pdf, o `design.yaml` deve conter somente o mapa `design`. Se houver templates personalizados, mantenha a pasta com o nome indicado em `design.theme` ao lado desse arquivo, assim como a pasta `fonts`, se usada.

```bash
lattes2pdf render curriculo.xml --profile profile.yaml \
  --theme meu-tema/design.yaml -o meu-cv.pdf
```

Você também pode salvar `theme: meu-tema/design.yaml` no perfil. Nesse caso, o caminho é relativo ao `profile.yaml`.

## Exportação e limites

Para gerar somente o YAML e o relatório, use `lattes2pdf export curriculo.xml -o cv.yaml`. O modo `--full` inclui todos os registros e detalhes conhecidos permitidos pela ferramenta, podendo produzir um documento extenso.


A integração atual usa RenderCV 2.8. Veja [como contribuir](https://github.com/mpds/lattes2pdf/blob/main/CONTRIBUTING.md) e a [licença MIT](https://github.com/mpds/lattes2pdf/blob/main/LICENSE).
