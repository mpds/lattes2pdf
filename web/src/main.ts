import './styles/app.css';
import { text } from './i18n/pt';
import {
  type Catalog,
  Engine,
  type Result,
  type Settings,
  TaskError,
} from './runtime/engine';
import { createPreview } from './runtime/preview';

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
let operation = 0;
const root = document.querySelector<HTMLElement>('#app')!;

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
  node.onclick = action;
  return node;
}
function invalidate() {
  if (result) outdated = true;
  result = undefined;
  outputUrls.forEach(URL.revokeObjectURL);
  outputUrls = [];
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
  step = 0;
  error = '';
  message = '';
  render(true);
  void initialize();
}
async function initialize() {
  try {
    catalog = await engine.start();
    if (customPending && custom) {
      custom.categories = [...catalog.presets[custom.basis]];
      settings.categories = [...custom.categories];
      customPending = false;
    }
    ready = true;
    render();
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
) {
  const input = el('input');
  input.type = 'file';
  input.accept = accept;
  input.className = 'file-input';
  input.disabled = busy || !ready;
  const labelNode = el('label', 'file-label primary', label, input);
  input.onchange = () => {
    const file = input.files?.[0];
    input.value = '';
    if (file) handler(file);
  };
  return labelNode;
}
function openFile(file?: File) {
  discardDocument();
  engine.stop();
  ready = false;
  if (file && (file.size === 0 || file.size > 25 * 1024 * 1024)) {
    error = 'Selecione um XML ou ZIP de até 25 MiB.';
    render();
    void initialize();
    return;
  }
  pendingFilename = file?.name ?? 'exemplo-ficticio.xml';
  void run(
    async () => {
      await engine.start();
      ready = true;
      return engine.request<{ name?: string; members?: string[] }>(
        'load',
        file ? new Uint8Array(await file.arrayBuffer()) : engine.example(),
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
      const link = download('', href, 'lattes2pdf.profile.yaml');
      document.body.append(link);
      link.click();
      link.remove();
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
      message = 'Configuração reutilizada.';
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
function showDialog(title: string, content: Node, dispose?: () => void) {
  const dialog = el('dialog');
  const heading = el('h2', '', title);
  heading.id = 'dialog-title';
  dialog.setAttribute('aria-labelledby', heading.id);
  dialog.append(
    heading,
    content,
    button('Fechar', () => dialog.close()),
  );
  dialog.onclose = () => {
    dispose?.();
    dialog.remove();
  };
  document.body.append(dialog);
  dialog.showModal();
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
  const section = el('div', '', fieldset);
  if (settings.model === 'personalizado') {
    const checklist = el(
      'fieldset',
      'checklist',
      el('legend', '', 'Categorias do currículo'),
    );
    if (!catalog)
      checklist.append(el('p', 'muted', 'Preparando a lista de categorias…'));
    else {
      if (
        !custom?.categories.length &&
        settings.categories.length === 0 &&
        custom === undefined
      )
        custom = {
          basis: 'resumido',
          categories: [...catalog.presets.resumido],
        };
      const update = (categories: string[]) => {
        custom = { basis: settings.basis, categories };
        settings.categories = [...categories];
        invalidate();
        error = '';
        render();
      };
      checklist.append(
        el(
          'div',
          'inline-actions',
          button(
            'Selecionar todas',
            () => update(catalog!.categories.map((c) => c.key)),
            'text-button',
          ),
          button('Desmarcar todas', () => update([]), 'text-button'),
        ),
      );
      const rows = el('div', 'category-grid');
      for (const item of catalog.categories)
        rows.append(
          checkbox(
            item.label,
            settings.categories.includes(item.key),
            (checked) =>
              update(
                checked
                  ? [...settings.categories, item.key]
                  : settings.categories.filter((key) => key !== item.key),
              ),
          ),
        );
      checklist.append(
        rows,
        el(
          'p',
          'muted',
          `${settings.categories.length} de 33 categorias selecionadas. As escolhas serão mantidas mesmo quando o arquivo não tiver dados nessas categorias.`,
        ),
      );
    }
    section.append(checklist);
  }
  const reuse = el(
    'details',
    'subtle',
    el('summary', '', 'Reutilizar configuração'),
  );
  reuse.append(
    el(
      'p',
      'muted',
      'Abra uma configuração salva aqui. Perfis com opções avançadas devem ser usados na CLI.',
    ),
    fileInput('Selecionar configuração', '.yaml,.yml', importProfile),
  );
  section.append(reuse);
  const next = button('Continuar', () => go(1), 'primary');
  next.disabled =
    busy || (settings.model === 'personalizado' && !settings.categories.length);
  section.append(el('div', 'navigation end', next));
  return section;
}
function fileStage() {
  const section = el('div');
  if (!loaded && !members) {
    section.append(
      el(
        'div',
        'file-zone',
        el('p', '', 'Selecione a exportação do seu Currículo Lattes.'),
        fileInput('Selecionar XML ou ZIP', '.xml,.zip', openFile),
        el(
          'p',
          'muted small',
          'Até 25 MiB. Processamento local, sem enviar seu currículo.',
        ),
        button('Usar exemplo fictício', () => openFile(), 'text-button'),
      ),
    );
  } else if (members) {
    const select = el('select');
    select.id = 'member';
    for (const member of members) {
      const option = el('option', '', member);
      option.value = member;
      select.append(option);
    }
    section.append(
      el(
        'label',
        'stack',
        'Este ZIP contém mais de um XML. Escolha o currículo:',
        select,
      ),
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
      button('Trocar arquivo', replaceFile, 'text-button'),
    );
  } else {
    section.append(
      el(
        'div',
        'file-confirmation',
        el('span', 'eyebrow', 'Arquivo validado'),
        el('h3', '', loaded!.name),
        el('p', 'filename', loaded!.filename),
        el('p', 'muted', `Modelo ${modelName()}`),
        button('Trocar arquivo', replaceFile, 'text-button'),
      ),
    );
  }
  const next = button('Continuar', () => go(2), 'primary');
  next.disabled = !loaded || busy;
  section.append(
    el(
      'div',
      'navigation',
      button('Voltar', () => go(0)),
      next,
    ),
  );
  return section;
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
  const section = el('div');
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
      `Ampliar ${text.themes[theme]}`,
      () => {
        const large = el('img', 'sample');
        large.src = image.src;
        large.alt = `Exemplo fictício no tema ${text.themes[theme]}`;
        showDialog(text.themes[theme], large);
      },
      'sample-button',
    );
    card.append(sample);
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
  const section = el('div');
  section.append(
    el(
      'div',
      'summary-box',
      el('strong', '', loaded!.name),
      el(
        'p',
        '',
        `${modelName()} · ${text.themes[settings.theme]} · ${settings.bibliography.toUpperCase()} · ${settings.language === 'pt' ? 'Português' : 'Inglês'}`,
      ),
      el(
        'p',
        'muted',
        `Atuação profissional: ${settings.professional ? `a partir de ${settings.professional}` : 'todo o período'}. Produção: ${settings.production ? `a partir de ${settings.production}` : 'todo o período'}.`,
      ),
    ),
  );
  if (!result) {
    const generate = button(
      'Gerar PDF',
      () => {
        invalidate();
        void run(
          () => engine.request<Result>('generate', settings),
          (value) => {
            result = value;
            outdated = false;
          },
          'Preparando o currículo…',
        );
      },
      'primary',
    );
    generate.disabled = busy || !ready;
    if (outdated)
      section.append(
        el(
          'p',
          'notice',
          'As escolhas mudaram. Gere novamente para atualizar o PDF.',
        ),
      );
    section.append(generate);
  } else {
    const href = url(result.pdf, 'application/pdf');
    section.append(
      el(
        'div',
        'result-actions',
        download('Baixar PDF', href, 'curriculo.pdf', 'primary'),
        button('Visualizar PDF', () => {
          const preview = createPreview(result!.pdf);
          showDialog('Prévia do PDF', preview.element, preview.dispose);
        }),
      ),
    );
    const warnings = result.report.issues.filter(
      (issue) => issue.level === 'WARNING',
    );
    if (warnings.length)
      section.append(
        el(
          'p',
          'notice',
          `PDF gerado com ${warnings.length} aviso(s). Consulte o relatório em Outros arquivos para conhecer dados ausentes ou não utilizados.`,
        ),
      );
    const others = el(
      'details',
      'subtle',
      el('summary', '', 'Outros arquivos'),
    );
    others.append(
      el(
        'p',
        'muted',
        'O YAML pode ser editado e recompilado no RenderCV. O relatório descreve o conteúdo exportado e as omissões.',
      ),
      el(
        'div',
        'inline-actions',
        download(
          'Baixar YAML',
          url(result.yaml, 'application/yaml'),
          'curriculo.yaml',
        ),
        download(
          'Baixar relatório',
          url(JSON.stringify(result.report, null, 2), 'application/json'),
          'curriculo.report.json',
        ),
      ),
    );
    section.append(others);
  }
  const save = button('Salvar configuração', saveProfile, 'text-button');
  save.disabled = busy || !ready;
  section.append(
    save,
    el(
      'div',
      'navigation',
      button('Voltar e ajustar', () => go(2)),
      button('Limpar tudo', clear),
    ),
  );
  return section;
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
  // Revoke all previous previews/downloads before replacing their DOM nodes.
  outputUrls.forEach(URL.revokeObjectURL);
  outputUrls = [];
  const logo = el('img');
  logo.src = engine.assetUrl('brand/logo.png');
  logo.alt = 'lattes2pdf';
  logo.width = 180;
  logo.height = 180;
  const header = el(
    'header',
    'header',
    el('div', 'brand-frame', logo),
    el(
      'p',
      'privacy-short',
      'Seu Lattes, em PDF.\nProcessado no seu navegador.',
    ),
  );
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
    'h1',
    '',
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
  const status = el(
    'p',
    `status ${ready ? 'ready' : ''}`,
    ready
      ? 'Recursos prontos · conversão disponível offline'
      : 'Preparando recursos para converter neste navegador…',
  );
  status.setAttribute('role', 'status');
  panel.append(status);
  if (error) {
    const alert = el('p', 'error', error);
    alert.setAttribute('role', 'alert');
    panel.append(alert);
  }
  if (busy || message) {
    const progress = el('p', 'notice', message);
    progress.id = 'operation-status';
    progress.setAttribute('role', 'status');
    panel.append(
      el(
        'div',
        'operation',
        progress,
        busy ? button('Cancelar', cancel) : undefined,
      ),
    );
  }
  if (busy) {
    const locked = el('fieldset', 'busy-content', content);
    locked.disabled = true;
    panel.append(locked);
  } else panel.append(content);
  const github = el('a', '', 'Código no GitHub');
  github.href = 'https://github.com/mpds/lattes2pdf';
  github.rel = 'noreferrer noopener';
  const footer = el(
    'footer',
    '',
    github,
    el('span', '', 'v0.2.0'),
    button(
      'Privacidade',
      () => showDialog('Privacidade', el('p', '', text.privacy)),
      'text-button',
    ),
    step !== 3 ? button('Limpar tudo', clear, 'text-button') : undefined,
  );
  root.replaceChildren(header, el('nav', '', steps), panel, footer);
  if (focus) heading.focus({ preventScroll: true });
  else restoreFocus?.()?.focus({ preventScroll: true });
}
window.addEventListener('pagehide', () => {
  operation++;
  engine.stop();
  discardDocument();
  settings = defaults();
  custom = undefined;
  customPending = false;
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
