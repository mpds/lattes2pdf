// Count structured authors; commas inside names are not separators to parse.
{% set authors = entry.authors|default([]) %}
{% if authors|length > 3 %}
{% set author_text = authors[0] ~ ' et al.' %}
{% elif authors %}
{% set author_text = authors|join(', ') ~ '.' %}
{% else %}
{% set author_text = '' %}
{% endif %}
{% set lines = entry.main_column.splitlines() %}
{% set venue = ' #emph[#title-case[' ~ entry.journal ~ ']]' if entry.journal|default('') else '' %}
{% set date = ' (' ~ entry.DATE ~ ')' if entry.DATE|default('') else '' %}
{% set link = ' ' ~ entry.URL if entry.URL|default('') else '' %}
// Use the entire line for a bibliographic reference.
#regular-entry([ ], [ ], main-column-second-row: [
  {{ author_text }} “{{ entry.title }}”.{{ venue }}{{ date }}{{ '.' if venue or date else '' }}{{ link }}

{% for line in lines %}
  {{ line|indent(2) }}

{% endfor %}
])
