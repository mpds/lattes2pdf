== #text(weight: {{ 600 if design.typography.bold.section_titles else 400 }})[{{ section_title }}]
{% if entry_type in ["ReversedNumberedEntry"] %}

#reversed-numbered-entries(
  [
{% endif %}
