# Exemplos sintéticos do Lattes

Estes arquivos foram criados com dados inteiramente fictícios para orientar
testes de importação, seleção e renderização. Nomes, documentos, instituições,
registros e publicações são exemplos. URLs usam `example.org`; o DOI demonstrativo
não identifica uma publicação real.

## Referência

A estrutura segue o [XSD disponibilizado pelo CNPq](https://memoria.cnpq.br/web/portal-lattes/extracoes-de-dados),
identificado no portal como atualizado em 12/09/2022. A cópia consultada em
06/09/2026 tem SHA-256:

```text
06b3976943f73b4e66f4ece70c5d9358d244fc080704c518a8d533d84eea6214
```

Os sete arquivos marcados como válidos representam, em conjunto, os **324 nomes
de elementos definidos nesse XSD**. Eles não exercitam todos os atributos,
enumerações, repetições ou combinações possíveis. Essa contagem não representa
cobertura de testes nem suporte já implementado pelo conversor.

## Arquivos

| Arquivo | Conteúdo e finalidade | Validação no XSD de referência |
| --- | --- | --- |
| [minimal.xml](minimal.xml) | Identificação mínima, sem produção ou formação; ausência de seções opcionais e de ID Lattes. | Válido |
| [general.xml](general.xml) | As 12 modalidades de formação, vínculos, atividades, projeto aninhado, idiomas, áreas, prêmios, afastamento e dados pessoais fictícios. Inclui doutorado em andamento e datas incompletas. | Válido |
| [bibliography.xml](bibliography.xml) | As 10 categorias bibliográficas: artigo publicado e aceito, trabalho em evento, livro, capítulo, texto em imprensa, outra produção, partitura, prefácio/pósfácio e tradução. | Válido |
| [technical.xml](technical.xml) | As 22 categorias técnicas: software, propriedade intelectual, cultivares, produtos, processos, trabalhos técnicos e as 12 outras modalidades. Inclui registro e histórico de patente. | Válido |
| [other.xml](other.xml) | As 11 modalidades artísticas/culturais, quatro modalidades de orientação concluída e demais trabalhos. | Válido |
| [complementary.xml](complementary.xml) | Quatro modalidades de formação complementar, seis de banca acadêmica, cinco de banca julgadora, nove de participação em evento, sete de orientação em andamento e tabelas auxiliares. | Válido |
| [latin1.xml](latin1.xml) | Bytes ISO-8859-1, acentos, entidades duplamente escapadas, campo vazio e caracteres significativos para linguagens de marcação. | Válido |
| [extensions.xml](extensions.xml) | Atributos posteriores ao XSD, mais um atributo e uma categoria futuros deliberadamente inventados. Exercita dados desconhecidos dentro e fora de entradas reconhecidas. | Inválido, intencionalmente |
| [unknown-namespace.xml](unknown-namespace.xml) | Namespace fictício `urn:cv-lattex:fixture:unknown`; não é um namespace oficial do CNPq. | Inválido, intencionalmente |
| [malformed.xml](malformed.xml) | Fechamento incorreto de elemento. | XML malformado, intencionalmente |
| [external-entity.xml](external-entity.xml) | DTD com referência externa a um arquivo fictício inexistente. Entrada para testar rejeição de entidades externas, sem tentar resolvê-las. | Fora dos exemplos válidos; não resolver a entidade |

## Casos que merecem atenção

- Em `general.xml`, `DISCIPLINA`, `TREINAMENTO` e `INTEGRANTES-DO-PROJETO`
  contêm texto. Informações do projeto também estão em elementos descendentes.
- No artigo de `bibliography.xml`, o autor com ordem `2` aparece antes do autor
  com ordem `1`. A ordem declarada e a posição no XML são diferentes.
- Categorias distintas reutilizam `SEQUENCIA-PRODUCAO="1"`. Esse valor sozinho
  não identifica globalmente uma produção.
- O artigo aceito não informa ano. O título em inglês está vazio, enquanto
  o artigo publicado possui título nos dois idiomas.
- Cultivares usam `DENOMINACAO` e `ANO-SOLICITACAO`. Outros registros usam
  diferentes atributos para título e ano.
- Os dados pessoais fictícios permitem verificar a seleção de campos sem usar
  documentos ou endereços de pessoas reais.
- `extensions.xml` contém `PCD`, os novos atributos de contato, atributos OASIS
  e atributos de certificado ausentes no XSD. `CAMPO-FUTURO`,
  `RECURSO-DIGITAL-FUTURO` e `DETALHE-FUTURO` são extensões inventadas.

## Uso nos testes

Escolha o menor exemplo que reproduza o comportamento testado e verifique o
resultado relevante: conteúdo preservado, seleção aplicada, ordem, data ou erro.
Monte arquivos ZIP temporários a partir desses XML quando precisar testar a
entrada compactada.

Preserve a codificação de `latin1.xml` ao editá-lo. Valide mudanças nos sete
exemplos válidos contra o XSD de referência; não transforme os exemplos inválidos
em válidos, pois suas falhas são intencionais.
