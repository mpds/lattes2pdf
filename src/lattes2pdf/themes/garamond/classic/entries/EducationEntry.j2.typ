// Local RenderCV template: degree, subject, institution and dates in columns.
#regular-entry([ ], [ ], main-column-second-row: [
  #grid(
    columns: (1.2fr, 2.3fr, 3fr, 2.4cm),
    column-gutter: {{ design.entries.space_between_columns }},
    align: (left, left, left, right),
    [{{ entry.degree|default('') }}],
    [{{ entry.area|default('') }}],
    [{{ entry.institution|default('') }}],
    [{{ entry.date_and_location_column.splitlines()|join(' \\\n')|indent(4) }}],
  )
{% if entry.SUMMARY|default('') %}
  #v(0.1cm)
  {{ entry.SUMMARY|indent(2) }}
{% endif %}
{% if entry.HIGHLIGHTS|default('') %}
  {{ entry.HIGHLIGHTS|indent(2) }}
{% endif %}
])
