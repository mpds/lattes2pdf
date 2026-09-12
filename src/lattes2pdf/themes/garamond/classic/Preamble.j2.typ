{% include 'typst/Preamble.j2.typ' %}

// Soften emphasis without changing the regular face or the text color.
#show strong: it => text(weight: 600, it.body)

// Transform rendered text, never the escaped Typst source (#text, Unicode, etc.).
// Mechanical title case, like the author option: particles/acronyms also change.
#let title-case(body) = {
  show text: it => {
    let value = lower(it.text).replace(
      regex("\\p{L}[\\p{L}\\p{M}]*"),
      word => upper(word.text.first()) + word.text.slice(word.text.first().len()),
    )
    if value == it.text { it } else { value }
  }
  body
}
