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
    'Seu currículo é processado apenas neste navegador, sem enviar seus dados a um servidor. Não salvamos documentos ou histórico. “Limpar tudo” descarta os dados desta sessão; os arquivos já baixados continuam no seu dispositivo.',
};
