# Avisos de terceiros

Textos oficiais que faltavam nas distribuições instaladas dos componentes do
runtime web. `index.json` registra a versão, origem e SHA-256 de cada texto.
Os arquivos marcados `upstream-original` preservam exatamente os bytes baixados.
O texto RenderCV teve somente finais de linha normalizados para LF; o índice
preserva também o hash original. A licença gratuita Fontin foi extraída como texto da seção correspondente da
página oficial; o índice também registra o hash do HTML consultado.

Pyodide é distribuído sob MPL-2.0; o campo `source_url` aponta para seu código
fonte da versão utilizada. O aviso `typst-ts-MODIFICATIONS.txt` descreve a
transformação local do wrapper JavaScript; a licença Apache original permanece.

Fontin: os três OTF de rendercv-fonts 0.5.1 correspondem byte a byte aos arquivos
do ZIP OpenType oficial consultado. A licença gratuita permite embedding, mas
também restringe redistribuição sem permissão. Nem o ZIP oficial nem o wheel
trazem autorização separada para redistribuição dos OTF. Preservar este texto
não equivale a confirmar autorização para disponibilizar esses arquivos a
terceiros. Este levantamento não modifica nem substitui a fonte.

O bundle também deve preservar os avisos já presentes nos wheels Python,
`pdfjs-dist/LICENSE`, a licença do pacote rendercv-fonts e LICENSE/NOTICE de
typst-assets. A coleta se limita aos componentes identificados; não é uma
auditoria completa de todas as dependências transitivas dos binários WASM.
