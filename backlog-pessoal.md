# Backlog Técnico & Diário de Bordo Arquitetural

Documento de registro individual das intervenções, decisões de modelagem relacional, segurança e implementação de lógica de negócios.

---

## FASE 1: BACKEND, ENGENHARIA DE DADOS & REGRAS DE NEGÓCIO

### 1. Ambiente, Versionamento e Dependências
* **Isolamento de Ambiente e Gestão de Pacotes:**
  * Criação de branch dedicada para mapeamento de dependências e ambiente virtual (`venv`).
  * Instalação e fixação das bibliotecas fundamentais: `Flask`, `psycopg2-binary`, `flask-bcrypt` e `requests`.
  * Exportação formal da árvore de pacotes para controle do repositório:
    ```powershell
    pip freeze > requirements.txt
    ```

### 2. Modelagem Relacional & Normalização (PostgreSQL)
* **Centralização de Autenticação e Herança Lógica:**
  * Criação da entidade unificada `usuarios` (`id`, `email`, `senha`, `perfil`) para resolver a dispersão anterior de credenciais.
  * Extensão para as tabelas filhas `administradores`, `professores` e `alunos` via Foreign Keys com integridade referencial e exclusão propagada (`ON DELETE CASCADE`).
* **3ª Forma Normal (3FN) para Domínio Pedagógico:**
  * Criação da tabela `niveis` (`id_nivel`, `sigla`, `nome`) com restrição estrita (`ON DELETE RESTRICT`) em `alunos` e `temas`, eliminando campos de texto livre suscetíveis a inconsistências.
* **Modelo de Agendamento Individual (Slots de 1 Hora):**
  * Tabela `aulas` associando diretamente `id_professor` e `id_aluno`.
  * Bloqueio preventivo contra choque de horários na camada de dados via constraint exclusiva:
    ```sql
    CONSTRAINT uk_professor_agenda UNIQUE (id_professor, data_aula, horario_inicio)
    ```
  * Flexibilidade curricular (RN04): coluna `id_tema` configurada como anulável (`NULL`), permitindo reservar o horário previamente à escolha do tópico.
* **Módulo de Acompanhamento e Avaliação:**
  * Criação da tabela `controle_academico` (`UNIQUE (id_aluno, id_aula)`) separando o registro oficial de presença do docente (`presenca BOOLEAN`) do visto do estudante (`aula_assistida BOOLEAN`, `nota_autoav` e `anotacoes_aluno`).
* **Módulo Financeiro Institucional:**
  * Implementação da tabela `mensalidades` (`id_aluno`, `mes_referencia`, `valor`, `data_vencimento`, `status`, `data_pagamento`), permitindo controle de caixa e quitação sem gateway externo.

### 3. Implementação das Rotas do Servidor & Lógica de Negócios (`app.py`)
* **Camada de Autenticação e Controle de Acesso Baseado em Papéis (RBAC):**
  * Substituição de verificações em texto plano pela validação com salt dinâmico via `bcrypt.check_password_hash`.
  * Gestão de sessão por crachás criptografados (`session['id_usuario']`, `session['email_logado']`, `session['perfil_logado']`, `session['id_perfil']`), eliminando a necessidade de seletores de perfil no login e despachando automaticamente para os painéis correspondentes.
* **Transações Atômicas no Cadastro:**
  * Encadeamento de inserções em `usuarios` e `alunos`/`professores` protegidas por blocos `try/except` com `conexao.rollback()` em casos de violação de unicidade (`psycopg2.IntegrityError`).
  * Automação financeira gerando a primeira mensalidade no ato da matrícula do aluno.
* **Gerenciamento Seguro de Arquivos Físicos:**
  * Configuração da pasta física `static/uploads/` com higienização de arquivos via `werkzeug.utils.secure_filename` e prefixo temporal para evitar colisões. Armazenamento no banco restrito aos caminhos relativos (`VARCHAR(255)`).
* **Integração Externa Resiliente (BrasilAPI):**
  * Consumo no servidor via biblioteca `requests` dos feriados nacionais com trava de tempo (`timeout=3`), unificando os dados ao mural escolar (`eventos_agenda`) sem interrupção do sistema em caso de instabilidade externa.

### 4. Testes, Homologação e Carga Inicial (`seed.sql`)
* **Diagnóstico de Validação de Hash:**
  * Identificação de falha de login com dados estáticos do seed provocada por divergência entre o hash pré-computado e a biblioteca local do ambiente.
  * Resolução do erro de parsing `ERROR: relation "usuarios " does not exist` causado por caractere de espaço residual no comando SQL.
  * Padronização do hash gerado localmente pelo interpretador Python ativo (`$2b$12$nBNAEDbQcavva2IxaJIRSebpCiuwVvqC4HIYzvgVBKbfAQyK0JdNW`) para a senha padrão `123456`, aplicável aos usuários `admin@escola.com`, `professor.carlos@escola.com`, `maria.silva@email.com` e `joao.santos@email.com`.
  * Sincronização explícita de sequences (`SELECT setval(...)`) em todas as chaves primárias seriais para prevenir erros de chave duplicada após inserções manuais.

### 5. Refatorações Arquiteturais & Otimizações de Backend
* **Correção de Mapeamento de Dados (`RealDictCursor`):**
  * Identificação do problema em que dropdowns renderizavam vazios `()` decorrente da transição de tuplas para dicionários, ajustando as consultas para chaves nominais.
* **Sinalização Visual de Adimplência (Finance Badges):**
  * Otimização da rota `/gerenciar-alunos` adicionando subconsulta relacional:
    ```sql
    CASE WHEN EXISTS (
        SELECT 1 FROM mensalidades m WHERE m.id_aluno = a.id_aluno AND m.status = 'PENDENTE'
    ) THEN 'PENDENTE' ELSE 'EM DIA' END AS status_financeiro
    ```
* **Desacoplamento do Catálogo Didático:**
  * Migração do banco de dados na tabela `temas` para acomodar materiais perenes:
    ```sql
    ALTER TABLE temas 
        ADD COLUMN IF NOT EXISTS url_pdf VARCHAR(255),
        ADD COLUMN IF NOT EXISTS url_slides VARCHAR(255);
    ```
  * Criação do módulo dedicado `catalogo_aulas.html` e das rotas `/catalogo-aulas`, `/catalogo-aulas/cadastrar` e `/catalogo-aulas/excluir`, isolando a ementa curricular perpétua da grade operacional de aulas.
* **Edição Inline Server-Side (Abordagem SSR Pura):**
  * Substituição de modais client-side (`<dialog>` / JS) por formulários adaptáveis no rodapé com parâmetros de consulta (`?edit_id=` e `?aluno_edit_id=`).
  * Tratamento de parâmetro opcional na rota `/gerenciar-alunos` com proteção `if aluno_edit_id and session.get('perfil_logado') == 'ADMIN'` e `cursor.fetchone()`, prevenindo exceções de busca com valor nulo.
  * Criação das rotas processadoras `POST /catalogo-aulas/editar` e `POST /admin/editar_aluno`.

---

## FASE 2: FRONTEND, DESIGN DE INTERFACE & EXPERIÊNCIA DO USUÁRIO (UI/UX)
*(Fase iniciada: estruturação visual, folhas de estilo CSS, responsividade, padronização tipográfica e usabilidade dos 9 templates consolidados)*


### 1. Sistema de Design, Tokens Visuais e Identidade Semântica (`static/style.css`)
* **Arquitetura CSS Centralizada com Design Tokens:**
  * Criação de folha de estilo única via variáveis CSS (`:root`) eliminando frameworks externos e garantindo consistência visual em todos os 9 templates.
  * Padronização de tipografia semântica, espaçamentos, tabelas de dados, áreas de toque (*touch targets*) e componentes de formulário.
* **Acessibilidade Institucional Univesp / e-MAG / WCAG 2.1 (Alto Contraste Claro):**
  * Implementação de modo de Alto Contraste Claro (*High-Contrast Light Mode*), preservando o fundo limpo enquanto reforça contrastes extremos (texto preto absoluto `#000000`, bordas sólidas de 2px e realces em amarelo canário `#ffe600` e azul marinho `#002244`).
  * Criação do script global `static/acessibilidade.js` com persistência de estado via `localStorage` e prevenção de cintilação de tela (*flash of unstyled content*).

### 2. Padronização Estrutural da Barra de Navegação Superior (Navbar)
* **Consolidação do Padrão ERP/SaaS:**
  * Substituição dos cabeçalhos dispersos por `<nav class="navbar">` unificada em todas as telas autenticadas e públicas.
  * Divisão funcional:
    * **Lado Esquerdo:** Identidade visual (`Portal Escolar`) e links de navegação contextual filtrados estritamente por papel (`ADMIN`, `PROFESSOR`, `ALUNO`).
    * **Lado Direito:** Botão de alternância de alto contraste (`◐ Contraste`), crachá do perfil ativo (`badge-perfil`) com o e-mail do operador e botão semântico de encerramento de sessão (`/logout`).
* **Tratamento de Visitante:**
  * Navbar adaptada em `cadastro_aluno.html` e `login.html` com suporte a estados não autenticados, exibindo atalhos para login/matrícula sem renderizar dados nulos de sessão.

### 3. Sistema de Badges e Sinalizadores Visuais de Dados
* **Sinalização Visual de Status Financeiro e Pedagógico:**
  * Substituição de marcações textuais simples por badges estruturadas:
    * `.badge-em-dia`: Quitações financeiras, presenças confirmadas, visto de aula assistida e materiais disponíveis para download.
    * `.badge-pendente`: Mensalidades em aberto, pendências de autoavaliação e ausência de materiais de apoio.
    * `.badge-agendada`, `.badge-concluida`, `.badge-cancelada`, `.badge-ferias`: Status de ciclo de vida das aulas.
    * `.tag-horario`: Destaque tipográfico e cromático para slots de aula de 1 hora.
    * `.badge-perfil-admin`, `.badge-perfil-professor`, `.badge-perfil-aluno`: Categorização curricular de níveis pedagógicos e eventos do mural.

### 4. Centralização e Refinamento do Portal de Acesso (`login.html`)
* **Design de Entrada Responsivo:**
  * Estruturação de layout flexível centralizado vertical e horizontalmente (`.login-wrapper` e `.login-card`).
  * Botão de login com largura total (área de clique expandida conforme WCAG 2.1 Critério 2.5.5).
  * Integração de mensagens flash do Flask em caixas de aviso com badges de alerta.

### 5. Estabilização e Migração Completa para Dicionários (`RealDictCursor`)
* **Correção de Incompatibilidade de Tipos (`tuple` vs `dict`):**
  * Diagnóstico e resolução das exceções `jinja2.exceptions.UndefinedError: 'tuple object' has no attribute 'valor'` e `'tuple object' has no attribute 'status'` disparadas pela transição das views Jinja2 para chaves nominais.
  * Refatoração no backend (`app.py`) das rotas `/painel/admin` e `/painel/professor` com injeção explícita de `cursor_factory=RealDictCursor` em todas as consultas SQL.
  * Padronização de aliases relacionais nas queries (`a.nome AS nome_aluno`, `al.nome AS nome_aluno`, `t.titulo_tema`, `n.sigla AS sigla_nivel`), eliminando o uso de tuplas indexadas numericamente em toda a malha de visualização.

### 6. Homologação da Malha dos 9 Templates Padronizados
* `login.html`: Layout em card centralizado, feedback com badges e acesso rápido à matrícula.
* `cadastro_aluno.html`: Formulário de matrícula com preenchimento assistido via ViaCEP e badges de retorno assíncrono.
* `painel_admin.html`: Gestão de mensalidades com badges financeiras, cadastro interno de docentes e publicação de avisos institucionais.
* `painel_professor.html`: Grade docente filtrada por `id_professor`, slots de 1h destacados, dropdowns nominais e agendamento com upload de arquivos.
* `painel_aluno.html`: Resumo financeiro, próximas aulas, histórico com dupla devolutiva e calendário unificado com a BrasilAPI.
* `aula_detalhe.html`: Repositório de arquivos, badges de autoavaliação discente e diário de classe do professor.
* `gerenciar_aulas.html`: Tabela global multi-filtro (Aluno, Tema, Status), tags de horários e ações rápidas de cancelamento/férias.
* `gerenciar_alunos.html`: Catálogo com divisão de privilégios (pedagógico vs administrativo/financeiro) e edição inline no rodapé sem modais.
* `catalogo_aulas.html`: Gestão curricular de planos de aula-modelo com upload multipart e indicadores de materiais anexados.

### 7. Módulo de Calendário Interativo & Visualização Mensal (CSS Grid + SSR)

* **Arquitetura de Navegação Temporal Server-Side:**
  * Implementação de controle de datas via query string (`?ano=YYYY&mes=MM`) nas rotas `/painel/aluno` e `/painel/professor`.
  * Cálculo dinâmico no backend dos meses adjacentes (`ano_anterior`, `mes_anterior`, `ano_proximo`, `mes_proximo`) com tratamento de virada de ano civil (janeiro/dezembro).
  * Substituição de URLs absolutas por chamadas semânticas do Flask (`url_for('painel_aluno', ...)` e `url_for('painel_professor', ...)`), eliminando riscos de roteamento quebrado (erros HTTP 404).

* **Motor de Montagem de Grade Mensal (`calendar` nativo):**
  * Utilização da biblioteca padrão `calendar.Calendar(firstweekday=calendar.SUNDAY)` para geração da matriz de semanas e dias do mês selecionado.
  * Otimização da busca de eventos no template Jinja2 através da pré-computação do dicionário `eventos_por_dia` ($O(1)$ por dia).
  * Destaque visual automático do dia corrente (`dia_hoje`) condicionado ao mês e ano vigentes.

* **Integração de Aulas Individuais ao Calendário Acadêmico:**
  * Inclusão das sessões de mentoria agendadas diretamente nas células do calendário:
    * **Visão do Aluno:** Itens renderizados com horário de início e título da aula, linkados para `aula_detalhe.html`.
    * **Visão do Professor:** Itens renderizados com horário de início e nome do estudante (`HH:MM - Aluno`), permitindo acesso direto ao diário de classe.
  * Isolamento estrito de dados (RN02): filtragem SQL no calendário docente restrita a `a.id_professor = %s` e no discente a `a.id_aluno = %s`.

* **Consistência de Ciclo de Vida e Badges Pedagógicas:**
  * Correção de discrepância de status na área do aluno via junção relacional:
    ```sql
    COALESCE(ca.aula_assistida, FALSE) AS aula_assistida
    ```
  * Aplicação condicional da badge `.badge-em-dia` (`ASSISTIDA [✓]`) quando o estudante registra sua autoavaliação, preservando o status administrativo oficial gerenciado pelo professor (`AGENDADA` / `CONCLUIDA`).
  * Criação dos sinalizadores específicos `.badge-aula-agendada` e `.badge-aula-assistida` com regras de contraste claro e alto contraste no `static/style.css`.

* **Acessibilidade Universal e Conformidade e-MAG / WCAG 2.1:**
  * Implementação de container semântico `<details>` / `<summary>` abaixo do grid mensal, oferecendo uma visão tabular alternativa completa para navegadores em modo texto ou softwares leitores de tela (NVDA, Orca, JAWS).
  * Estilização de alto contraste claro (`body.alto-contraste`) com bordas pretas reforçadas (2px) e marcação do dia atual em amarelo canário (`#ffe600`).

  ## FASE 3: INFRAESTRUTURA CLOUD & MIGRAÇÃO PARA NEON SERVERLESS POSTGRES

### 1. Isolamento de Credenciais e Segurança de Ambiente (`.env`)
* **Gerenciamento Seguro de Variáveis com `python-dotenv`:**
  * Remoção de credenciais sensíveis codificadas diretamente no repositório (`hardcoded`).
  * Criação do arquivo de configuração `.env` na raiz do projeto para armazenamento da string de conexão de produção (`DATABASE_URL`) e da chave de criptografia de sessão (`SECRET_KEY`).
  * Atualização do `.gitignore` para impedir a exposição acidental de chaves criptográficas e dados do banco no GitHub.
* **Resolução de Ordem de Inicialização no Flask:**
  * Correção do ciclo de instanciação no `app.py`: carregamento prioritário de `load_dotenv()` antes da declaração de `app = Flask(__name__)` e definição de `app.secret_key`, eliminando o erro de variável indefinida do analisador estático (Pylance).

### 2. Camada de Conexão Resiliente e Híbrida (`obter_conexao`)
* **Suporte Nativo a Connection Pooling e SSL:**
  * Configuração da Connection String do Neon apontando para o endpoint gerenciado com pooler (`ep-royal-forest-axp91i6d-pooler`), otimizado para o ciclo de vida stateless das requisições web no Flask.
  * Inclusão explícita dos parâmetros de segurança exigidos pela AWS/Neon: `sslmode=require` e `channel_binding=require`.
* **Fallback Automático para Desenvolvimento Local:**
  * Refatoração da função `obter_conexao()` no `app.py` com arquitetura híbrida:
    * Se `DATABASE_URL` existir no ambiente, conecta diretamente à nuvem (Neon).
    * Caso contrário, recorre automaticamente às variáveis locais (`DB_HOST`, `DB_NAME`, `DB_USER`, `DB_PASS`, `DB_PORT`), garantindo portabilidade entre ambientes de desenvolvimento e produção.

### 3. Extração, Tratamento e Carga de Dados (ETL Local → Cloud)
* **Extração de Dados Locais via Backup Relacional:**
  * Execução e exportação da base de dados local (`individual_gestao_escolar`) via ferramenta administrativa (pgAdmin 4 / `pg_dump`), preservando chaves primárias, integridade referencial, sequências e dados de testes acadêmicos.
* **Sanitização de Sintaxe SQL para Ambiente Cloud:**
  * Remoção de diretivas proprietárias de linha de comando (`\restrict`, `\unrestrict`) incompatíveis com editores web SQL.
  * Supressão de comandos de superusuário (`ALTER TABLE ... OWNER TO postgres;`), incompatíveis com a política de privilégios gerenciados do Neon (`neondb_owner`).
  * Conversão de blocos legados `COPY FROM stdin` para comandos canônicos `INSERT INTO`, assegurando a codificação correta dos caracteres acentuados em UTF-8.
* **Resolução de Conflitos de Integridade (`SQLSTATE 42P10`):**
  * Eliminação de cláusulas `ON CONFLICT` que falhavam por falta de identificação imediata de restrições de unicidade pelo interpretador durante a carga em lote.
  * Inserção linear respeitando a hierarquia de dependência das chaves estrangeiras:
    1. `usuarios` e `niveis` (tabelas-base)
    2. `administradores`, `professores` e `alunos` (perfis vinculados)
    3. `temas` (catálogo pedagógico)
    4. `aulas` (agendamentos e vínculos docentes/discentes)
    5. `controle_academico` (presença, vistos de aula assistida e notas)
    6. `eventos_agenda` (mural escolar)
    7. `mensalidades` (registros financeiros)
* **Sincronização dos Ponteiros de Sequência (`SERIAL`):**
  * Execução de rotina corretiva com `SELECT setval(...)` utilizando `MAX(id)` em todas as tabelas, evitando erros de colisão de chaves primárias duplicadas (`UniqueViolation`) nos próximos cadastros realizados via aplicação.

  ### 4. Padronização de Nomenclatura e Integridade Relacional
* **Harmonização da Chave Primária de Autenticação (`id_usuario`):**
  * Renomeação da coluna identificadora da tabela `usuarios` de `id` para `id_usuario`, eliminando a ambiguidade com as chaves estrangeiras (`administradores.id_usuario`, `professores.id_usuario`, `alunos.id_usuario`).
  * Atualização dos comandos de manipulação (`RETURNING id_usuario`, `JOIN`s diretos e remoção em cascata por `id_usuario`).
* **Saneamento Estrutural do Schema e Eliminação de Coluna Órfã:**
  * Purga e recriação em cascata (`DROP CASCADE`) da base de dados no Neon Serverless, sanando a criação indevida da coluna residual `nivei` e estabelecendo a integridade estrita de `id_nivel` como Foreign Key vinculada à tabela de domínio `niveis`.

### 5. Camada de Apresentação e Interação com Banco (Backend & Templates)
* **Serialização de Objetos em Rotas de Consulta com `RealDictCursor`:**
  * Injeção do cursor especializado do `psycopg2` nas rotas de matrícula e cadastros dinâmicos, convertendo registros tabulares em dicionários e sanando falhas de renderização no Jinja2 (como dropdowns exibindo rótulos vazios `()`).
* **Tratamento Defensivo de Casting e Fallback Numérico:**
  * Implementação de sanitização e conversão explícita para valores inteiros em campos numéricos (`id_nivel`), prevenindo exceções de sintaxe de entrada inválida (`integer: ""`).
* **Correção de Redirecionamento e Manutenção de Estado Administrativo:**
  * Refatoração do fluxo pós-cadastro: preservação da sessão ativa do perfil `ADMIN` com despacho direto para a gestão de alunos (`/gerenciar-alunos`), restringindo o redirecionamento para a tela de login exclusivamente a acessos externos/não autenticados.




Aqui está a consolidação completa de todo o trabalho realizado e o planejamento técnico dos próximos passos em formato de **Backlog do Projeto**.

---

# 📋 Backlog de Desenvolvimento & Refatoração do Sistema Escolar

## 1. Status Geral do Sistema (Sprints Concluídas)

### 🚀 Sprint 1: Correção de Quebras Críticas & Estabilidade Jinja2

* [x] **Eliminação de `UndefinedError: 'str' is undefined`:** Substituição de chamadas globais Python `str(obj)` pelo filtro nativo Jinja2 `(obj | string)[:5]` em todas as tabelas (`gerenciar_aulas.html`, `painel_professor.html`, `painel_aluno.html`).
* [x] **Tratamento de rotas 404 e templates ausentes:** Implementação e registro da rota `/admin/professores` no backend `app.py` e criação do arquivo `gerenciar_professores.html`.
* [x] **Consistência de Queries (`RealDictCursor`):** Atualização do `SELECT` na rota `/gerenciar-aulas` com `JOIN niveis` para disponibilizar o campo `sigla_nivel` e os atributos `a.id_tema`, `a.link_aula` e `a.observacoes`.

---

### 🎨 Sprint 2: Design System, Padronização Visual & CSS Global

* [x] **Centralização Universal:** Criação das regras globais em `static/style.css` sob o container `.container-central` (limite de 960px, alinhamento central de cabeçalhos e formulários restritos a 500px).
* [x] **Padronização Universal de Tabelas:**
* Borda externa reforçada (`2px solid var(--borda)`).
* Divisórias internas sólidas (`1px solid var(--borda)`).
* Padding uniforme em células (`12px 14px`).
* Alinhamento centralizado horizontal e vertical (`text-align: center; vertical-align: middle;`).
* Zebrado sutil em linhas pares e efeito hover suave.


* [x] **Neutralização dos Botões de Ação em Tabelas:** Eliminação de botões azuis largos (`button[type="submit"]` e `button[type="button"]`) herdando tamanho de formulário. Transformação em links textuais discretos (`display: inline; text-decoration: underline; background: none`).
* [x] **Grid do Calendário:** Reestruturação da malha CSS Grid de 7 colunas (`.calendario-grid`) para os painéis docente e discente, corrigindo a quebra de alinhamento vertical.
* [x] **Acessibilidade & Alto Contraste (e-MAG / WCAG 2.1):**
* Padronização de classes no modo `.alto-contraste` com bordas sólidas em preto (#000) e amarelo (#ffff00).
* Correção do caminho do script de acessibilidade para `/static/acessibilidade.js` em todos os templates.



---

### 🧹 Sprint 3: Limpeza de Módulos & Higienização UI/UX

* [x] **Remoção de Módulos Não Utilizados:**
* Descontinuação de uploads de apresentações `.pptx` no catálogo (`catalogo_aulas.html`) devido ao limite de payload, mantendo suporte restrito e padronizado a `.pdf`.
* Remoção de colunas e botões soltos de cobrança/status financeiro em `gerenciar_alunos.html`.


* [x] **Formatação de Datas:** Conversão de strings de data `AAAA-MM-DD` para o formato brasileiro `DD-MM-AAAA` (`split('-')`) com `white-space: nowrap;` para evitar quebras de linha em células estreitas.
* [x] **Integração BrasilAPI:** Limpeza de badges poluídas no calendário e isolamento dos feriados nacionais sob componente `<details>` retrátil no painel do professor.

---

## 2. Itens Pendentes / Próximas Sprints

### 📌 Épico: Segurança, Vínculos Pedagógicos & Limpeza de Banco

| ID | Prioridade | Item / Tarefa | Descrição Técnica |
| --- | --- | --- | --- |
| **BK-01** | **Alta** | **Exclusão Definitiva do Módulo Financeiro** | Dropar tabelas `mensalidades` / `contas_a_receber` do banco PostgreSQL, remover as rotas `/admin/baixar_mensalidade`, `/admin/gerar_mensalidade` do `app.py` e limpar o bloco financeiro do `painel_admin.html` e `painel_aluno.html`. |
| **BK-02** | **Alta** | **Vínculo Fixo Aluno-Professor** | Se o modelo de negócio exigir que cada professor atenda apenas a sua carteira de alunos, criar a migration para adicionar `id_professor INT REFERENCES professores(id_professor)` na tabela `alunos`. Atualizar o formulário de cadastro de aluno e o `SELECT` de agendamento em `painel_professor`. |
| **BK-03** | **Média** | **Refatoração de Datas no Backend** | Em vez de manipular `split('-')` repetidamente dentro dos templates Jinja2, criar um filtro customizado no Flask (ex: `@app.template_filter('formata_data')`) ou já retornar formatado do PostgreSQL via `TO_CHAR(data, 'DD-MM-YYYY')`. |
| **BK-04** | **Média** | **Validação de Uploads PDF** | Implementar checagem rigorosa de tamanho de arquivo (`MAX_CONTENT_LENGTH`) e sanitização de nomes com `werkzeug.utils.secure_filename` nas rotas de upload de materiais didáticos. |
| **BK-05** | **Baixa** | **Paginação / Lazy Loading** | Adicionar paginação `LIMIT` e `OFFSET` com navegação simples em `gerenciar_aulas.html` e `gerenciar_alunos.html` para manter o desempenho conforme o volume de registros aumentar. |

  Aqui está o **Backlog do Projeto** atualizado, incluindo a conclusão do módulo **Meu Perfil** e a padronização dos botões da Navbar.

---

# 📋 Backlog de Desenvolvimento & Refatoração do Sistema Escolar

## 1. Status Geral do Sistema (Sprints Concluídas)

### 🚀 Sprint 1: Correção de Quebras Críticas & Estabilidade Jinja2

* [x] **Eliminação de `UndefinedError: 'str' is undefined`:** Substituição de chamadas globais Python `str(obj)` pelo filtro nativo Jinja2 `(obj | string)[:5]` em todas as tabelas (`gerenciar_aulas.html`, `painel_professor.html`, `painel_aluno.html`).
* [x] **Tratamento de rotas 404 e templates ausentes:** Implementação e registro da rota `/admin/professores` no backend `app.py` e criação do arquivo `gerenciar_professores.html`.
* [x] **Consistência de Queries (`RealDictCursor`):** Atualização do `SELECT` na rota `/gerenciar-aulas` com `JOIN niveis` para disponibilizar o campo `sigla_nivel` e os atributos `a.id_tema`, `a.link_aula` e `a.observacoes`.

---

### 🎨 Sprint 2: Design System, Padronização Visual & CSS Global

* [x] **Centralização Universal:** Criação das regras globais em `static/style.css` sob o container `.container-central` (limite de 960px, alinhamento central de cabeçalhos e formulários restritos a 500px).
* [x] **Padronização Universal de Tabelas:**
* Borda externa reforçada (`2px solid var(--borda)`).
* Divisórias internas sólidas (`1px solid var(--borda)`).
* Padding uniforme em células (`12px 14px`).
* Alinhamento centralizado horizontal e vertical (`text-align: center; vertical-align: middle;`).
* Zebrado sutil em linhas pares e efeito hover suave.


* [x] **Neutralização dos Botões de Ação em Tabelas:** Eliminação de botões azuis largos (`button[type="submit"]` e `button[type="button"]`) herdando tamanho de formulário. Transformação em links textuais discretos (`display: inline; text-decoration: underline; background: none`).
* [x] **Grid do Calendário:** Reestruturação da malha CSS Grid de 7 colunas (`.calendario-grid`) para os painéis docente e discente, corrigindo a quebra de alinhamento vertical.
* [x] **Acessibilidade & Alto Contraste (e-MAG / WCAG 2.1):**
* Padronização de classes no modo `.alto-contraste` com bordas sólidas em preto (#000) e amarelo (#ffff00).
* Correção do caminho do script de acessibilidade para `/static/acessibilidade.js` em todos os templates.



---

### 🧹 Sprint 3: Limpeza de Módulos & Higienização UI/UX

* [x] **Remoção de Módulos Não Utilizados:**
* Descontinuação de uploads de apresentações `.pptx` no catálogo (`catalogo_aulas.html`) devido ao limite de payload, mantendo suporte restrito e padronizado a `.pdf`.
* Remoção de colunas e botões soltos de cobrança/status financeiro em `gerenciar_alunos.html`.


* [x] **Formatação de Datas:** Conversão de strings de data `AAAA-MM-DD` para o formato brasileiro `DD-MM-AAAA` (`split('-')`) com `white-space: nowrap;` para evitar quebras de linha em células estreitas.
* [x] **Integração BrasilAPI:** Limpeza de badges poluídas no calendário e isolamento dos feriados nacionais sob componente `<details>` retrátil no painel do professor.

---

### 👤 Sprint 4: Autonomia do Usuário & Ações da Navbar

* [x] **Módulo Unificado de Perfil (`/meu-perfil`):**
* Criação da rota centralizada para `ADMIN`, `PROFESSOR` e `ALUNO` editarem informações cadastrais e dados de contato.
* Validação segura de redefinição de credenciais via `check_password_hash` e geração de nova chave com `generate_password_hash` (permitindo aos novos usuários substituir a senha provisória).
* Integração de consulta automática de endereço via CEP com ViaCEP diretamente na tela de perfil.
* Criação do template `meu_perfil.html` mantendo o padrão de design system.


* [x] **Padronização de Botões de Ação da Navbar (`.btn-perfil` / `.btn-nav-acao`):**
* Criação de classe CSS específica para botões da barra de navegação superior, harmonizando dimensões, padding (`6px 14px`), tipografia (negrito) e alinhamento com o botão nativo `.btn-sair`.
* Inclusão de suporte nativo ao modo alto contraste com borda e inversão em amarelo (#ffff00).



---

## 2. Itens Pendentes / Próximas Sprints

| ID | Prioridade | Item / Tarefa | Descrição Técnica |
| --- | --- | --- | --- |
| **BK-01** | **Alta** | **Exclusão Definitiva do Módulo Financeiro** | Dropar tabelas `mensalidades` / `contas_a_receber` do banco PostgreSQL, remover as rotas `/admin/baixar_mensalidade`, `/admin/gerar_mensalidade` do `app.py` e limpar o bloco financeiro do `painel_admin.html` e `painel_aluno.html`. |
| **BK-02** | **Alta** | **Vínculo Fixo Aluno-Professor** | Se o modelo de negócio exigir que cada professor atenda apenas a sua carteira de alunos, criar a migration para adicionar `id_professor INT REFERENCES professores(id_professor)` na tabela `alunos`. Atualizar o formulário de cadastro de aluno e o `SELECT` de agendamento em `painel_professor`. |
| **BK-03** | **Média** | **Refatoração de Datas no Backend** | Em vez de manipular `split('-')` repetidamente dentro dos templates Jinja2, criar um filtro customizado no Flask (ex: `@app.template_filter('formata_data')`) ou já retornar formatado do PostgreSQL via `TO_CHAR(data, 'DD-MM-YYYY')`. |
| **BK-04** | **Média** | **Validação de Uploads PDF** | Implementar checagem rigorosa de tamanho de arquivo (`MAX_CONTENT_LENGTH`) e sanitização de nomes com `werkzeug.utils.secure_filename` nas rotas de upload de materiais didáticos. |
| **BK-05** | **Baixa** | **Paginação / Lazy Loading** | Adicionar paginação `LIMIT` e `OFFSET` com navegação simples em `gerenciar_aulas.html` e `gerenciar_alunos.html` para manter o desempenho conforme o volume de registros aumentar. |




# Backlog de Refatoração: Frontend & Arquitetura de Templates (Portal Escolar)

---

## 1. Itens Entregues (Sprint Concluída)

### Arquitetura de Templates & Componentização

* **Centralização com `base.html`:**
* Implementação da casca mestra contendo `<head>`, meta tags responsivas, link global para `static/style.css`, container `<main class="container-central">` e injeção do script global de acessibilidade.
* Estruturação de blocos Jinja2 modulares: `{% block titulo %}`, `{% block navbar %}`, `{% block conteudo %}`, `{% block extra_css %}` e `{% block extra_js %}`.


* **Desacoplamento da Navbar (`navbar.html`):**
* Extração da barra superior para `templates/navbar.html`, incluída dinamicamente via `{% include 'navbar.html' %}` dentro do bloco `{% block navbar %}`.
* Resolução de conflitos em telas de credenciamento (`login.html` e `primeiro_acesso.html`), permitindo navbar enxuta/restrita sem links protegidos.
* Unificação dos botões de controle à direita (`.btn-nav`) com classes específicas para `btn-contraste`, `btn-perfil` e `btn-sair`.



---

### Migração de Templates para Herança

Todos os templates foram higienizados (remoção de tags repetidas `<html>`, `<head>`, `<nav>`, `<main>` e chamadas manuais de mensagens flash):

* `painel_admin.html` (comunicação de mural e tabela de feriados nacionais via BrasilAPI).
* `painel_professor.html` (sessões agendadas, diário, agendamento de mentorias e calendário docente).
* `painel_aluno.html` (próximas aulas, histórico pedagógico com download de anexos e calendário do estudante).
* `gerenciar_aulas.html` (grade completa com filtros compostos, modal/seção de edição inline sem scroll horizontal indesejado).
* `gerenciar_alunos.html` (listagem, filtros de busca por nome/nível e integração inline com ViaCEP).
* `gerenciar_professores.html` (tabela de docentes com ações diretas e cadastro/edição com ViaCEP).
* `login.html` & `primeiro_acesso.html` (layouts centralizados e com navbar neutra).
* `meu_perfil.html` (gestão unificada de dados cadastrais, redefinição de senha e endereço).

---

### Limpeza e Otimização do CSS (`static/style.css`)

* **Redução Drástica de Linhas:** Redução do arquivo legado (mais de 440 linhas) para cerca de 150 linhas sem qualquer perda visual ou funcional.
* **Sistema Orientado a Variáveis CSS (`:root` e `.alto-contraste`):**
* Eliminação de regras redundantes com `!important` espalhadas.
* Alternância de tema gerenciada alterando exclusivamente as variáveis de cor (preto absoluto, amarelo institucional, azul WCAG e fundos adaptativos).


* **Remoção de Código Morto:**
* Expurgo completo de classes residuais do módulo financeiro legado (`.badge-pago`, `.badge-a-vencer`, etc.).


* **Padronização Universal:**
* Formulários com largura balanceada e centralização automática.
* Tabelas com visual limpo, bordas consistentes e ações inline no estilo de link textual (`button` limpo para formulários `POST`).



---

## 2. Dívidas Técnicas Solucionadas (Issues Resolvidas)

* **Conflito de renderização de navbar:** Resolvido isolando o componente em `navbar.html` e dando override de bloco nas rotas de login/primeiro acesso.
* **Quebra de alinhamento em `gerenciar_aulas.html`:** Tabela corrigida com remoção de colunas redundantes e eliminação do `overflow-x` forçado, garantindo centralização visual perfeita em telas largas e médias.
* **Duplicação de scripts assíncronos:** Funções de preenchimento inline e chamadas à API ViaCEP transferidas para o bloco isolado `{% block extra_js %}`.

---

## 3. Próximos Passos Sugeridos (Backlog Futuro)

| Prioridade | Item | Descrição |
| --- | --- | --- |
| **Média** | **Toast Notifications** | Substituir o bloco estático de mensagens flash por toasts discretos flutuantes ou alertas que desaparecem automaticamente após 5 segundos. |
| **Média** | **Validação de Formulários via JS** | Adicionar máscaras de digitação para CEP (`00000-000`) e campos de horário diretamente no frontend para prevenir requisições inválidas. |
| **Baixa** | **Cache-Busting Dinâmico** | Implementar um filtro Jinja ou query string com timestamp/versão automática (`style.css?v={{ config.VERSION }}`) para evitar cache de arquivos estáticos no navegador em novas atualizações. |
| **Baixa** | **Responsividade Mobile (Menu Hambúrguer)** | Em telas menores que 768px, recolher os links da navbar em um menu retrátil simples compatível com leitor de tela e alto contraste. |