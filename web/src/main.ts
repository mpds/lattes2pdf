import { text } from './i18n/pt';
import {
  type Catalog,
  Engine,
  type Result,
  type Settings,
  TaskError,
} from './runtime/engine';

const engine = new Engine();
const defaults = (): Settings => ({
  model: 'resumido',
  basis: 'resumido',
  categories: [],
  theme: 'classic',
  bibliography: 'abnt',
  informed: true,
  etAl: false,
  professional: null,
  production: null,
  language: 'pt',
});
let settings = defaults();
let catalog: Catalog | undefined;
let step = 0;
let custom: { categories: string[]; basis: string } | undefined;
let customPending = false;
let profileReused = false;
let loaded: { name: string; filename: string } | undefined;
let members: string[] | undefined;
let pendingFilename = '';
let busy = false;
let ready = false;
let message = '';
let error = '';
let result: Result | undefined;
let outdated = false;
let outputUrls: string[] = [];
let pdfUrl: string | undefined;
let operation = 0;
const root = document.querySelector<HTMLElement>('#app')!;
// Keep public content from the initial HTML when rebuilding the workflow.
const header = root.querySelector<HTMLElement>('.header')!;
const introduction = root.querySelector<HTMLElement>('#introduction')!;
const guide = root.querySelector<HTMLElement>('#guide')!;
const runtimeStatus = header.querySelector<HTMLElement>('#runtime-status')!;
header.querySelector('.privacy-short')!.prepend(icon('shield'));

function el<K extends keyof HTMLElementTagNameMap>(
  tag: K,
  className = '',
  ...children: (Node | string | undefined)[]
): HTMLElementTagNameMap[K] {
  const node = document.createElement(tag);
  node.className = className;
  node.append(
    ...children.filter((child): child is Node | string => child !== undefined),
  );
  return node;
}
function button(
  label: string,
  action: () => void,
  className = 'secondary',
): HTMLButtonElement {
  const node = el('button', className, label);
  node.type = 'button';
  node.onclick = () => {
    // WebKit does not focus buttons on pointer clicks. Keep dialog return focus consistent.
    node.focus({ preventScroll: true });
    action();
  };
  return node;
}
function icon(
  name:
    | 'check'
    | 'upload'
    | 'download'
    | 'file'
    | 'arrow'
    | 'settings'
    | 'shield'
    | 'refresh'
    | 'close',
) {
  const paths = {
    check: 'm5 12 4 4L19 6',
    upload: 'M12 16V4m-5 5 5-5 5 5M4 16v4h16v-4',
    download: 'M12 4v12m-5-5 5 5 5-5M4 17v3h16v-3',
    file: 'M14 3H5v18h14V8l-5-5v5h5M8 12h8M8 16h6',
    arrow: 'M5 12h14m-6-6 6 6-6 6',
    settings: 'M4 7h16M4 17h16M9 4v6m6 4v6',
    shield: 'M12 3 4 6v6c0 5 8 9 8 9s8-4 8-9V6l-8-3Zm-4 9 3 3 5-6',
    refresh:
      'M3 11a9 9 0 0 1 15.4-6.4L21 7M21 3v4h-4M21 13a9 9 0 0 1-15.4 6.4L3 17M3 21v-4h4',
    close: 'm6 6 12 12M6 18 18 6',
  };
  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  svg.setAttribute('viewBox', '0 0 24 24');
  svg.setAttribute('fill', 'none');
  svg.setAttribute('stroke', 'currentColor');
  svg.setAttribute('stroke-width', '1.7');
  svg.setAttribute('stroke-linecap', 'round');
  svg.setAttribute('stroke-linejoin', 'round');
  svg.setAttribute('aria-hidden', 'true');
  svg.classList.add('icon');
  const path = document.createElementNS(svg.namespaceURI, 'path');
  path.setAttribute('d', paths[name]);
  svg.append(path);
  return svg;
}
function triggerDownload(href: string, filename: string) {
  const link = download('', href, filename);
  document.body.append(link);
  link.click();
  link.remove();
}
function invalidate() {
  if (result) outdated = true;
  result = undefined;
  outputUrls.forEach(URL.revokeObjectURL);
  outputUrls = [];
  if (pdfUrl) URL.revokeObjectURL(pdfUrl);
  pdfUrl = undefined;
}
function url(bytes: BlobPart, type: string) {
  const value = URL.createObjectURL(new Blob([bytes], { type }));
  outputUrls.push(value);
  return value;
}
function download(
  label: string,
  href: string,
  filename: string,
  className = 'secondary',
) {
  const link = el('a', className, label);
  link.href = href;
  link.download = filename;
  return link;
}
function modelName() {
  return text.models.find((model) => model[0] === settings.model)![1];
}
function selectModel(model: string) {
  profileReused = false;
  if (model === 'personalizado') {
    if (!catalog) customPending = true;
    custom ??= {
      basis: settings.model === 'personalizado' ? 'resumido' : settings.model,
      categories: [
        ...(catalog?.presets[settings.model] ??
          catalog?.presets.resumido ??
          []),
      ],
    };
    settings = {
      ...settings,
      model,
      basis: custom.basis,
      categories: [...custom.categories],
    };
  } else settings = { ...settings, model };
  invalidate();
  error = '';
  render();
  if (model === 'personalizado' && catalog) showCategories();
}
function go(next: number) {
  step = next;
  error = '';
  render(true);
}
async function run<T>(
  work: () => Promise<T>,
  done: (value: T) => void,
  status: string,
) {
  const id = ++operation;
  busy = true;
  error = '';
  message = status;
  render();
  try {
    const value = await work();
    if (id === operation) done(value);
  } catch (cause) {
    if (id !== operation) return;
    if (!(cause instanceof TaskError && cause.code === 'cancelled'))
      error =
        cause instanceof Error
          ? cause.message
          : 'Não foi possível concluir a operação.';
    if (
      cause instanceof TaskError &&
      ['runtime', 'timeout'].includes(cause.code)
    ) {
      discardDocument();
      engine.stop();
      ready = false;
      step = 1;
      void initialize();
    }
  } finally {
    if (id === operation) {
      busy = false;
      message = '';
      render(true);
    }
  }
}
function discardDocument() {
  document.querySelectorAll('dialog').forEach((dialog) => {
    dialog.close();
    dialog.remove();
  });
  loaded = undefined;
  members = undefined;
  pendingFilename = '';
  invalidate();
  outdated = false;
}
function cancel() {
  operation++;
  busy = false;
  engine.stop();
  ready = false;
  discardDocument();
  step = 1;
  error = '';
  message = 'Operação cancelada. Selecione o arquivo novamente.';
  render(true);
  void initialize();
}
function clear() {
  operation++;
  busy = false;
  engine.stop();
  ready = false;
  discardDocument();
  settings = defaults();
  custom = undefined;
  customPending = false;
  profileReused = false;
  step = 0;
  error = '';
  message = '';
  render(true);
  void initialize();
}
async function initialize() {
  try {
    catalog = await engine.start();
    const openCategories = customPending && step === 0;
    if (customPending && custom) {
      custom.categories = [...catalog.presets[custom.basis]];
      settings.categories = [...custom.categories];
      customPending = false;
    }
    ready = true;
    render();
    if (openCategories) showCategories();
  } catch (cause) {
    if (!(cause instanceof TaskError && cause.code === 'cancelled')) {
      error =
        'Não foi possível preparar os recursos. Reabra a página com conexão em um navegador desktop atualizado.';
      ready = false;
      render();
    }
  }
}
engine.onStatus = (status) => {
  message = status;
  const node = document.querySelector('#operation-status');
  if (node) node.textContent = status;
};

function fileInput(
  label: string,
  accept: string,
  handler: (file: File) => void,
  className = 'primary',
) {
  const input = el('input');
  input.type = 'file';
  input.accept = accept;
  input.className = 'file-input';
  input.disabled = busy || !ready;
  const labelNode = el(
    'label',
    `file-label ${className}`,
    icon('upload'),
    label,
    input,
  );
  input.onchange = () => {
    const file = input.files?.[0];
    input.value = '';
    if (file) handler(file);
  };
  return labelNode;
}
function openFile(file: File) {
  if (file.size === 0 || file.size > 25 * 1024 * 1024) {
    error = 'Selecione um XML ou ZIP de até 25 MiB.';
    render();
    return;
  }
  discardDocument();
  engine.stop();
  ready = false;
  pendingFilename = file.name;
  void run(
    async () => {
      await engine.start();
      ready = true;
      return engine.request<{ name?: string; members?: string[] }>(
        'load',
        new Uint8Array(await file.arrayBuffer()),
      );
    },
    (value) => {
      if (value.members) members = value.members;
      else loaded = { name: value.name!, filename: pendingFilename };
    },
    'Lendo e validando o arquivo…',
  );
}
function replaceFile() {
  discardDocument();
  engine.stop();
  ready = false;
  error = '';
  render();
  void initialize();
}
function saveProfile() {
  void run(
    () => engine.request<string>('profile-export', settings),
    (contents) => {
      const href = url(contents, 'application/yaml');
      triggerDownload(href, 'lattes2pdf.profile.yaml');
    },
    'Preparando a configuração…',
  );
}
function importProfile(file: File) {
  if (file.size > 65536) {
    error = 'A configuração excede o limite de 64 KiB.';
    render();
    return;
  }
  void run(
    async () =>
      engine.request<Settings>(
        'profile-import',
        new Uint8Array(await file.arrayBuffer()),
      ),
    (value) => {
      settings = value;
      custom =
        value.model === 'personalizado'
          ? { basis: value.basis, categories: [...value.categories] }
          : undefined;
      invalidate();
      profileReused = true;
    },
    'Validando a configuração…',
  );
}
function checkbox(
  label: string,
  checked: boolean,
  action: (value: boolean) => void,
) {
  const input = el('input');
  input.type = 'checkbox';
  input.checked = checked;
  input.dataset.focus = label;
  input.onchange = () => action(input.checked);
  return el('label', 'check-row', input, el('span', '', label));
}
function radios(
  title: string,
  options: [string, string][],
  value: string,
  change: (value: string) => void,
  name: string,
) {
  const fieldset = el('fieldset', 'choice-group', el('legend', '', title));
  for (const [key, label] of options) {
    const input = el('input');
    input.type = 'radio';
    input.name = name;
    input.value = key;
    input.checked = value === key;
    input.onchange = () => change(key);
    fieldset.append(el('label', 'radio-pill', input, label));
  }
  return fieldset;
}
function showDialog(
  title: string,
  content: Node,
  onClose?: () => void,
  className = '',
  closeLabel = 'Fechar',
) {
  const opener = document.activeElement;
  const dialog = el('dialog');
  dialog.className = className;
  const heading = el('h2', '', title);
  heading.id = 'dialog-title';
  dialog.setAttribute('aria-labelledby', heading.id);
  const close = button('', () => dialog.close(), 'icon-button');
  close.setAttribute('aria-label', 'Fechar janela');
  close.append(icon('close'));
  dialog.append(
    el('div', 'dialog-header', heading, close),
    el('div', 'dialog-body', content),
    el(
      'div',
      'dialog-footer',
      button(closeLabel, () => dialog.close(), 'primary'),
    ),
  );
  dialog.onclose = () => {
    dialog.remove();
    if (onClose) onClose();
    else if (
      opener instanceof HTMLElement &&
      opener !== document.body &&
      opener.isConnected
    )
      opener.focus({ preventScroll: true });
  };
  document.body.append(dialog);
  dialog.showModal();
}

function showCategories() {
  if (!catalog) return;
  const checklist = el(
    'fieldset',
    'checklist',
    el('legend', 'sr-only', 'Categorias disponíveis'),
  );
  const count = el('p', 'selection-count');
  count.setAttribute('role', 'status');
  const inputs = new Map<string, HTMLInputElement>();
  const update = (categories: string[]) => {
    custom = { basis: settings.basis, categories };
    settings.categories = [...categories];
    invalidate();
    error = '';
    count.textContent = `${categories.length} de ${catalog!.categories.length} categorias selecionadas`;
    for (const [key, input] of inputs) input.checked = categories.includes(key);
  };
  const toolbar = el(
    'div',
    'category-toolbar',
    button(
      'Selecionar todas',
      () => update(catalog!.categories.map((item) => item.key)),
      'secondary compact',
    ),
    button('Desmarcar todas', () => update([]), 'secondary compact'),
  );
  const rows = el('div', 'category-grid');
  for (const item of catalog.categories) {
    const row = checkbox(
      item.label,
      settings.categories.includes(item.key),
      (checked) =>
        update(
          checked
            ? [...settings.categories, item.key]
            : settings.categories.filter((key) => key !== item.key),
        ),
    );
    inputs.set(item.key, row.querySelector('input')!);
    rows.append(row);
  }
  update(settings.categories);
  checklist.append(toolbar, count, rows);
  showDialog(
    'Categorias do currículo',
    checklist,
    () => {
      render();
      // Let the browser release the modal's inert state before focusing the rebuilt page.
      requestAnimationFrame(() =>
        root
          .querySelector<HTMLButtonElement>('[data-focus="customize"]')
          ?.focus({ preventScroll: true }),
      );
    },
    'categories-dialog',
    'Concluir seleção',
  );
}
function modelStage() {
  const fieldset = el(
    'fieldset',
    'model-grid',
    el('legend', 'sr-only', 'Modelo de currículo'),
  );
  for (const [key, title, detail] of text.models) {
    const radio = el('input');
    radio.type = 'radio';
    radio.name = 'model';
    radio.value = key;
    radio.checked = settings.model === key;
    radio.disabled = busy;
    radio.onchange = () => selectModel(key);
    fieldset.append(
      el(
        'label',
        `model-card ${radio.checked ? 'selected' : ''}`,
        radio,
        el(
          'span',
          'card-content',
          el('strong', '', title),
          el('span', 'muted', detail),
        ),
      ),
    );
  }
  const reuse = el(
    'div',
    'reuse-config',
    fileInput(
      'Reutilizar configuração',
      '.yaml,.yml',
      importProfile,
      'secondary',
    ),
    el(
      'p',
      'muted small',
      profileReused
        ? 'Configuração carregada.'
        : 'Abra uma configuração salva aqui.',
    ),
  );
  const customize = button('Escolher categorias', showCategories, 'secondary');
  customize.prepend(icon('settings'));
  customize.dataset.focus = 'customize';
  customize.disabled = !catalog || busy;
  const selection = el(
    'div',
    'custom-selection',
    customize,
    el(
      'p',
      'muted small',
      `${settings.categories.length} categorias selecionadas`,
    ),
  );
  selection.classList.toggle('invisible', settings.model !== 'personalizado');
  const next = button('Continuar', () => go(1), 'primary');
  next.append(icon('arrow'));
  next.disabled =
    busy || (settings.model === 'personalizado' && !settings.categories.length);
  return el(
    'div',
    'stage',
    el(
      'div',
      'stage-body',
      fieldset,
      el('div', 'model-tools', reuse, selection),
    ),
    el('div', 'navigation end', next),
  );
}
function fileStage() {
  const body = el('div', 'stage-body');
  const changeFile = button('Trocar arquivo', replaceFile);
  changeFile.prepend(icon('refresh'));
  if (!loaded && !members) {
    const zone = el(
      'div',
      'file-zone',
      el('div', 'file-symbol', icon('upload')),
      fileInput('Selecionar XML ou ZIP', '.xml,.zip', openFile),
      el('p', 'muted small', 'XML ou ZIP · até 25 MiB'),
    );
    body.append(zone);
  } else if (members) {
    const select = el('select');
    select.id = 'member';
    for (const member of members) {
      const option = el('option', '', member);
      option.value = member;
      select.append(option);
    }
    body.append(
      el(
        'div',
        'file-zone member-zone',
        el(
          'label',
          'stack',
          'Este ZIP contém mais de um XML. Escolha o currículo:',
          select,
        ),
        el(
          'div',
          'inline-actions',
          button(
            'Abrir XML selecionado',
            () => {
              void run(
                () => engine.request<{ name: string }>('member', select.value),
                (value) => {
                  loaded = { name: value.name, filename: pendingFilename };
                  members = undefined;
                },
                'Validando o XML…',
              );
            },
            'primary',
          ),
          changeFile,
        ),
      ),
    );
  } else {
    body.append(
      el(
        'div',
        'file-confirmation',
        el('div', 'file-symbol success-symbol', icon('check')),
        el(
          'div',
          'file-identity',
          el('span', 'eyebrow', 'Arquivo validado'),
          el('h3', '', loaded!.name),
          el('p', 'filename muted', loaded!.filename),
          el('span', 'badge', `Modelo ${modelName()}`),
        ),
        changeFile,
      ),
    );
  }
  const next = button('Continuar', () => go(2), 'primary');
  next.append(icon('arrow'));
  next.disabled = !loaded || busy;
  return el(
    'div',
    'stage',
    body,
    el(
      'div',
      'navigation',
      button('Voltar', () => go(0)),
      next,
    ),
  );
}
function period(title: string, key: 'professional' | 'production') {
  const group = radios(
    title,
    [
      ['all', 'Todo o período'],
      ['since', 'A partir do ano'],
    ],
    settings[key] === null ? 'all' : 'since',
    (value) => {
      settings[key] = value === 'all' ? null : new Date().getFullYear() - 5;
      invalidate();
      render();
    },
    key,
  );
  if (settings[key] !== null) {
    const input = el('input');
    input.type = 'text';
    input.inputMode = 'numeric';
    input.pattern = '[1-9][0-9]{3}';
    input.maxLength = 4;
    input.name = `${key}-year`;
    input.value = String(settings[key]);
    input.required = true;
    const help = el('span', 'field-error');
    help.id = `error-${key}`;
    input.setAttribute('aria-describedby', help.id);
    input.oninput = () => {
      const valid = /^[1-9][0-9]{3}$/.test(input.value);
      settings[key] = valid ? Number(input.value) : 0;
      input.setAttribute('aria-invalid', String(!valid));
      help.textContent = valid ? '' : 'Informe um ano com quatro dígitos.';
      invalidate();
    };
    group.append(
      el('label', 'year-input', 'Ano inicial (inclusive)', input, help),
    );
  }
  return group;
}
function preferencesStage() {
  const section = el('div', 'stage preferences-stage');
  const themes = el('fieldset', 'theme-grid', el('legend', '', 'Tema do PDF'));
  for (const theme of catalog?.themes ?? Object.keys(text.themes)) {
    const radio = el('input');
    radio.type = 'radio';
    radio.name = 'theme';
    radio.value = theme;
    radio.checked = settings.theme === theme;
    radio.onchange = () => {
      settings.theme = theme;
      invalidate();
      render();
    };
    const image = el('img');
    image.src = engine.assetUrl(`themes/${theme}.png`);
    image.alt = '';
    image.width = 180;
    image.height = 254;
    const card = el(
      'div',
      'theme-card',
      el(
        'label',
        `theme-option ${radio.checked ? 'selected' : ''}`,
        image,
        el('span', 'theme-label', radio, text.themes[theme]),
      ),
    );
    const sample = button(
      'Ampliar exemplo',
      () => {
        const large = el('img', 'sample');
        large.src = image.src;
        large.alt = `Primeira página do currículo de exemplo no tema ${text.themes[theme]}`;
        showDialog(text.themes[theme], large, undefined, 'sample-dialog');
      },
      'sample-button',
    );
    sample.setAttribute('aria-label', `Ampliar ${text.themes[theme]}`);
    card.append(sample);
    if (theme === 'moderncv') {
      const fontNote = button(
        '',
        () =>
          showDialog(
            'Fonte do ModernCV',
            el(
              'p',
              '',
              'Nesta versão, a fonte do ModernCV foi substituída pela XCharter.',
            ),
          ),
        'theme-help',
      );
      fontNote.append(el('span', 'help-mark', '?'));
      fontNote.setAttribute('aria-label', 'Sobre a fonte do ModernCV');
      fontNote.setAttribute('aria-haspopup', 'dialog');
      card.append(fontNote);
    }
    themes.append(card);
  }
  section.append(themes);
  const refs = el('section', 'preferences', el('h3', '', 'Referências'));
  refs.append(
    radios(
      'Estilo das referências',
      [
        ['abnt', 'ABNT'],
        ['chicago', 'Chicago'],
      ],
      settings.bibliography,
      (value) => {
        settings.bibliography = value;
        invalidate();
      },
      'bibliography',
    ),
    checkbox(
      'Utilizar Citação Bibliográfica Informada',
      settings.informed,
      (value) => {
        settings.informed = value;
        invalidate();
      },
    ),
    checkbox('Utilizar abreviação et al.', settings.etAl, (value) => {
      settings.etAl = value;
      invalidate();
    }),
  );
  section.append(
    refs,
    el(
      'section',
      'preferences',
      el('h3', '', 'Períodos'),
      el(
        'div',
        'period-grid',
        period('Período da atuação profissional', 'professional'),
        period('Período da produção', 'production'),
      ),
      el(
        'p',
        'muted small',
        'Datas desconhecidas são mantidas. Os períodos não alteram formação, prêmios, projetos, orientações, eventos ou bancas.',
      ),
    ),
    radios(
      'Idioma do PDF',
      [
        ['pt', 'Português'],
        ['en', 'Inglês'],
      ],
      settings.language,
      (value) => {
        settings.language = value;
        invalidate();
      },
      'language',
    ),
  );
  section.append(
    el(
      'div',
      'navigation',
      button('Voltar', () => go(1)),
      button(
        'Continuar',
        () => {
          if (settings.professional === 0 || settings.production === 0) {
            error =
              'Informe um ano com quatro dígitos para cada período selecionado.';
            render();
            return;
          }
          go(3);
        },
        'primary',
      ),
    ),
  );
  return section;
}
function pdfStage() {
  const summary = el(
    'div',
    'summary-box',
    el('span', 'eyebrow', 'Seu currículo'),
    el('h3', '', loaded!.name),
    el(
      'div',
      'summary-tags',
      ...[
        modelName(),
        text.themes[settings.theme],
        settings.bibliography.toUpperCase(),
        settings.language === 'pt' ? 'Português' : 'Inglês',
      ].map((label) => el('span', 'badge', label)),
    ),
  );
  const periods = el('dl', 'summary-periods');
  for (const [label, value] of [
    ['Atuação profissional', settings.professional],
    ['Produção', settings.production],
  ] as const) {
    periods.append(
      el(
        'div',
        '',
        el('dt', '', label),
        el('dd', '', value ? `A partir de ${value}` : 'Todo o período'),
      ),
    );
  }
  summary.append(periods);
  const generate = button(
    'Gerar PDF',
    () => {
      invalidate();
      void run(
        () => engine.request<Result>('generate', settings),
        (value) => {
          result = value;
          outdated = false;
          // Keep this URL alive through renders so asynchronous downloads work in all engines.
          pdfUrl = URL.createObjectURL(
            new Blob([value.pdf], { type: 'application/pdf' }),
          );
          triggerDownload(pdfUrl, 'curriculo.pdf');
        },
        'Preparando o currículo…',
      );
    },
    'primary',
  );
  generate.prepend(icon('download'));
  generate.disabled = busy || !ready;
  const save = button('Salvar configuração', saveProfile, 'secondary');
  save.prepend(icon('settings'));
  save.disabled = busy || !ready;
  const actions = el('div', 'export-actions', generate, save);
  const body = el('div', 'stage-body', summary);
  const delivery = el('div', `delivery ${result ? 'complete' : ''}`);
  if (result && pdfUrl) {
    const retry = download(
      'Baixar PDF novamente',
      pdfUrl,
      'curriculo.pdf',
      'secondary',
    );
    retry.prepend(icon('download'));
    delivery.append(
      el(
        'div',
        'delivery-heading',
        el('div', 'success-symbol', icon('check')),
        el(
          'div',
          '',
          el('h3', '', 'PDF gerado com sucesso'),
          el(
            'p',
            'muted small',
            'O download foi iniciado. Se precisar, baixe novamente.',
          ),
        ),
      ),
      retry,
    );
    const warnings = result.report.issues.filter(
      (issue) => issue.level === 'WARNING',
    );
    if (warnings.length)
      delivery.append(
        el(
          'p',
          'notice small',
          `${warnings.length} aviso(s) sobre os dados do currículo. Veja os detalhes no relatório.`,
        ),
      );
  } else {
    delivery.append(
      el(
        'p',
        'muted small',
        outdated
          ? 'As escolhas mudaram. Gere novamente para atualizar o PDF.'
          : 'O PDF será baixado automaticamente ao terminar.',
      ),
    );
  }
  body.append(actions, el('div', 'delivery-slot', delivery));
  const others = button(
    'Outros arquivos',
    () => {
      if (!result) return;
      const downloads = el('div', 'download-list');
      for (const [label, href, filename, detail] of [
        [
          'Baixar YAML',
          url(result.yaml, 'application/yaml'),
          'curriculo.yaml',
          'Versão editável para usar no RenderCV.',
        ],
        [
          'Baixar relatório',
          url(JSON.stringify(result.report, null, 2), 'application/json'),
          'curriculo.report.json',
          'Conteúdo exportado, avisos e omissões.',
        ],
      ])
        downloads.append(
          el(
            'div',
            'download-row',
            el(
              'div',
              '',
              download(label, href, filename, 'secondary'),
              el('p', 'muted small', detail),
            ),
          ),
        );
      showDialog('Outros arquivos', downloads);
    },
    'secondary',
  );
  others.prepend(icon('file'));
  others.disabled = !result || busy;
  return el(
    'div',
    'stage',
    body,
    el(
      'div',
      'navigation',
      button('Voltar e ajustar', () => go(2)),
      others,
    ),
  );
}

function render(focus = false) {
  const active = document.activeElement;
  let restoreFocus: (() => HTMLElement | undefined) | undefined;
  if (!focus && active instanceof HTMLInputElement) {
    const name = active.name,
      value = active.value,
      key = active.dataset.focus;
    restoreFocus = () =>
      [...root.querySelectorAll('input')].find((input) =>
        key
          ? input.dataset.focus === key
          : input.name === name && input.value === value,
      );
  } else if (!focus && active instanceof HTMLButtonElement) {
    const label = active.textContent;
    restoreFocus = () =>
      [...root.querySelectorAll('button')].find(
        (node) => node.textContent === label,
      );
  }
  root.dataset.ready = String(ready);
  runtimeStatus.classList.toggle('invisible', ready || busy);
  runtimeStatus.textContent = error
    ? 'Não foi possível preparar o conversor'
    : 'Preparando conversor…';
  const steps = el('ol', 'steps');
  text.stages.forEach((title, index) => {
    const item = el(
      'li',
      index === step ? 'active' : index < step ? 'done' : '',
      el('span', 'step-number', String(index + 1)),
      el('span', '', title),
    );
    if (index === step) item.setAttribute('aria-current', 'step');
    steps.append(item);
  });
  const heading = el(
    'h2',
    'stage-title',
    [
      'Escolha o modelo',
      'Abra seu currículo',
      'Dê forma ao seu PDF',
      result ? 'Seu PDF está pronto' : 'Gere seu PDF',
    ][step],
  );
  heading.tabIndex = -1;
  const content = [modelStage, fileStage, preferencesStage, pdfStage][step]();
  const panel = el('main', 'panel', heading);
  if (error) {
    const alert = el('p', 'error', error);
    alert.setAttribute('role', 'alert');
    panel.append(alert);
  }
  if (busy) {
    const locked = el('fieldset', 'busy-content', content);
    locked.disabled = true;
    locked.inert = true;
    panel.append(locked);
    const progress = el('p', '', message);
    progress.id = 'operation-status';
    progress.setAttribute('role', 'status');
    const spinner = el('span', 'spinner');
    spinner.setAttribute('aria-hidden', 'true');
    panel.append(
      el(
        'div',
        'operation',
        spinner,
        progress,
        el('p', 'muted small', 'Seu arquivo permanece neste navegador.'),
        button('Cancelar', cancel),
      ),
    );
  } else {
    if (message) {
      const note = el('p', 'notice', message);
      note.setAttribute('role', 'status');
      panel.append(note);
    }
    panel.append(content);
  }
  const github = el('a', '', 'Código no GitHub');
  github.href = 'https://github.com/mpds/lattes2pdf';
  github.rel = 'noreferrer noopener';
  github.target = '_blank';
  const feedback = el('a', '', 'Encontrou um problema?');
  feedback.href = 'https://github.com/mpds/lattes2pdf/issues/new';
  feedback.rel = 'noreferrer noopener';
  feedback.target = '_blank';
  const privacy = button(
    'Privacidade',
    () => showDialog('Privacidade', el('p', '', text.privacy)),
    'text-button',
  );
  privacy.prepend(icon('shield'));
  const footer = el(
    'footer',
    '',
    el('div', 'footer-links', github, feedback),
    el(
      'div',
      'footer-tools',
      el('span', 'version', 'v0.3.0'),
      privacy,
      button('Limpar tudo', clear, 'text-button'),
    ),
  );
  const nav = el('nav', '', steps);
  nav.setAttribute('aria-label', 'Etapas da conversão');
  root.replaceChildren(header, introduction, nav, panel, guide, footer);
  if (busy)
    panel
      .querySelector<HTMLButtonElement>('.operation button')
      ?.focus({ preventScroll: true });
  else if (focus) heading.focus({ preventScroll: true });
  else restoreFocus?.()?.focus({ preventScroll: true });
}
window.addEventListener('pagehide', () => {
  operation++;
  engine.stop();
  discardDocument();
  settings = defaults();
  custom = undefined;
  customPending = false;
  profileReused = false;
  step = 0;
  ready = false;
  busy = false;
  message = error = '';
  render();
});
window.addEventListener('pageshow', (event) => {
  if (event.persisted) {
    render();
    void initialize();
  }
});
render();
void initialize();
