# Exemplo fictício

O [currículo XML](curriculo.xml) e o [perfil de seleção](profile.yaml) representam um exemplo fictício de um currículo Lattes.

Todos os PDFs abaixo usam o mesmo conteúdo e o mesmo perfil, com RenderCV 2.8:

| Tema | Origem | PDF |
| --- | --- | --- |
| `classic` | RenderCV | [Visualizar](pdfs/classic.pdf) |
| `ember` | RenderCV | [Visualizar](pdfs/ember.pdf) |
| `engineeringclassic` | RenderCV | [Visualizar](pdfs/engineeringclassic.pdf) |
| `engineeringresumes` | RenderCV | [Visualizar](pdfs/engineeringresumes.pdf) |
| `harvard` | RenderCV | [Visualizar](pdfs/harvard.pdf) |
| `ink` | RenderCV | [Visualizar](pdfs/ink.pdf) |
| `moderncv` | RenderCV | [Visualizar](pdfs/moderncv.pdf) |
| `opal` | RenderCV | [Visualizar](pdfs/opal.pdf) |
| `sb2nov` | RenderCV | [Visualizar](pdfs/sb2nov.pdf) |

Para reproduzir a partir da raiz do repositório:

```bash
mkdir -p saida/moderncv
lattes2pdf render examples/curriculo.xml --profile examples/profile.yaml \
  --theme moderncv -o saida/moderncv/cv.pdf
```

Troque `moderncv` por qualquer nome da tabela, usando uma pasta de saída por tema.
