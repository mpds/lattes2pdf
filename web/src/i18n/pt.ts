export const text = {
  stages: ['Modelo', 'Arquivo', 'Tema e preferências', 'PDF'],
  models: [
    [
      'resumido',
      'Resumido',
      'Formação, atuação profissional e principais produções.',
    ],
    [
      'ampliado',
      'Ampliado',
      'Acrescenta endereço, idiomas, prêmios e áreas de atuação.',
    ],
    ['completo', 'Completo', 'Todas as 33 categorias de conteúdo disponíveis.'],
    [
      'personalizado',
      'Personalizado',
      'Escolha as categorias que deseja apresentar.',
    ],
  ],
  themes: {
    classic: 'Classic',
    ember: 'Ember',
    engineeringclassic: 'Engineering Classic',
    engineeringresumes: 'Engineering Resumes',
    harvard: 'Harvard',
    ink: 'Ink',
    moderncv: 'ModernCV',
    opal: 'Opal',
    sb2nov: 'Sb2nov',
  } as Record<string, string>,
  privacy:
    'Seu currículo é processado neste navegador. Nenhum arquivo ou dado do currículo é enviado ou salvo pelo aplicativo. Os arquivos que você baixar ficam no seu dispositivo. Os recursos públicos da página podem ficar no cache normal do navegador. Após a preparação, todas as conversões desta sessão funcionam offline. Reabrir a página pode exigir conexão. Limpar tudo descarta os documentos e resultados desta sessão; isso não apaga arquivos que você já baixou. O servidor recebe os acessos normais à página e aos seus recursos, sem nomes de arquivos ou dados do currículo. Não utilizamos análise de uso, cookies, contas ou recuperação de sessões.',
};
