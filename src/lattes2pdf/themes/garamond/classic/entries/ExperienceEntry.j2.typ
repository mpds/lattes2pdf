// Local RenderCV template: role, organization and dates in columns.
{% set date_column = entry.date_and_location_column %}
{% set start_only = namespace(value='') %}
{% set prefix = 'Início: ' if locale.language_iso_639_1 == 'pt' else 'Start: ' %}
{% if entry.end_date|default('') == 'present' %}
{% set start_only.value = entry.START_DATE|default('') %}
{% elif entry.date|default('') is string and (entry.date|default('')).startswith(prefix) %}
{% set source_date = entry.date[prefix|length:] %}
{% set parts = source_date.split('-') %}
{% if parts|length in [1, 2] and parts[0]|length == 4 and parts[0].isdigit() %}
{% if parts|length == 1 %}
{% set start_only.value = parts[0] %}
{% elif parts[1]|length == 2 and parts[1].isdigit() and 1 <= parts[1]|int <= 12 %}
{% set start_only.value = locale.month_abbreviations[parts[1]|int - 1] ~ ' ' ~ parts[0] %}
{% endif %}
{% endif %}
{% endif %}
{% if start_only.value %}
{% set date_column = date_column.replace(entry.DATE, start_only.value) %}
{% endif %}
#regular-entry([ ], [ ], main-column-second-row: [
  #grid(
    columns: (2.4fr, 3.5fr, {{ design.entries.date_and_location_width }}),
    column-gutter: {{ design.entries.space_between_columns }},
    align: (left, left, right),
    [{{ entry.position|default('') }}],
    [#title-case[{{ entry.company|default('') }}]],
    [{{ date_column.splitlines()|join(' \\\n')|indent(4) }}],
  )
{% if entry.SUMMARY|default('') %}
  #v(0.1cm)
  {{ entry.SUMMARY|indent(2) }}
{% endif %}
{% if entry.HIGHLIGHTS|default('') %}
  {{ entry.HIGHLIGHTS|indent(2) }}
{% endif %}
])
