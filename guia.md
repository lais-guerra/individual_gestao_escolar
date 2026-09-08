# Guia de Execução e Backlog Técnico: Portal Escolar

Este documento detalha o passo a passo cronológico de concepção, desenvolvimento, refatoração e publicação do **Portal Escolar**. Ele foi estruturado para que qualquer desenvolvedor consiga reproduzir a arquitetura completa do zero.

---

## Sumário do Projeto
* **Stack Principal:** Python 3 (Flask), Jinja2, PostgreSQL (hospedado no Neon), SQLAlchemy.
* **Frontend:** HTML5 semântico, CSS3 orientado a variáveis (Design System WCAG 2.1 / e-MAG), JavaScript Vanilla para acessibilidade e consumo de APIs externas.
* **APIs de Terceiros:** BrasilAPI (feriados nacionais no calendário acadêmico) e ViaCEP (preenchimento automático de endereço).

---

## Etapa 1: Modelagem e Banco de Dados (PostgreSQL)

O banco foi projetado na 3ª Forma Normal (3FN), separando autenticação centralizada dos dados específicos de cada perfil de usuário.

### 1.1. Modelagem Relacional (DDL)
Criação do script `script-ddl.sql` contendo a hierarquia de tabelas e integridade referencial:
* `usuarios`: Entidade pai para login unificado (`email`, `senha` com hash Bcrypt, `perfil`).
* `niveis`: Tabela de domínio pedagógico (`BASICO`, `INTERMEDIARIO`, `AVANCADO`).
* Perfis específicos vinculados por chave estrangeira (1:1 com `usuarios`):
  * `administradores`: Secretaria e direção.
  * `professores`: Corpo docente.
  * `alunos`: Estudantes, já estruturados com campos de endereço normalizados para consumo de CEP (`logradouro`, `bairro`, `cidade`, `uf`, etc.).
* `temas`: Catálogo pedagógico curricular vinculado a um nível.
* `aulas`: Grade de agendamento de 1 hora, contendo `id_professor`, `id_aluno`, `id_tema`, links de videochamada (`Google Meet` / `Teams`), caminhos de anexos e status (`AGENDADA`, `CONCLUIDA`, `CANCELADA`).
* `controle_academico`: Rastreabilidade pedagógica com check de chamada do docente, confirmação de aula assistida pelo estudante, notas e autoavaliação.
* `eventos_agenda`: Mural de avisos escolares e integração de feriados.

> **Decisão Arquitetural:** O módulo de `mensalidades` foi totalmente expurgado do banco e do código para manter o sistema estritamente pedagógico e acadêmico.

### 1.2. Carga de Dados Inicial (Seed)
Criação do script `script-seed.sql` com:
* Inserção de credenciais de teste para os 3 perfis com senha padrão criptografada em Bcrypt (`123456`).
* Ajuste de ponteiros das sequences (`setval`) para evitar conflitos de IDs ao inserir novos registros via sistema.
* Dados de teste de alunos reais/fictícios com endereços válidos no padrão ViaCEP.
* Temas curriculares e aulas previamente cadastradas com status distintos para testes de interface.

---

## Etapa 2: Provisionamento em Nuvem (Neon Tech)

Em vez de manter o banco restrito ao `localhost`, a camada de persistência foi transferida para um PostgreSQL Serverless gerenciado.

1. **Criação do Projeto no Neon:**
   * Projeto provisionado com PostgreSQL 16+.
   * Obtenção da `Connection String` segura contendo usuário, senha, host com terminação `.neon.tech` e o parâmetro obrigatório `?sslmode=require`.
2. **Execução dos Scripts no Neon:**
   * Abertura do **SQL Editor** no console do Neon.
   * Execução sequencial do `script-ddl.sql` (criação das tabelas).
   * Execução do `script-seed.sql` (inserção da massa de dados inicial).

---

## Etapa 3: Configuração do Backend e Integração (`app.py`)

A conexão entre a aplicação Flask e o banco de dados foi construída com foco em segurança e tolerância a falhas de rede.

### 3.1. Isolamento de Credenciais (`.env`)
Para permitir que o repositório se tornasse público sem vazamento de dados:
* Instalação do gerenciador de ambiente:
  ```bash
  pip install python-dotenv

```

* Criação do arquivo local `.env` (ignorado pelo Git):
```ini
SECRET_KEY=sua-chave-criptografica-forte
DATABASE_URL=postgresql://usuario:senha@ep-exemplo.region.aws.neon.tech/neondb?sslmode=require

```


* Criação do arquivo `.env.example` (versionado no Git como gabarito):
```ini
SECRET_KEY=chave_de_exemplo_para_desenvolvimento
DATABASE_URL=postgresql://usuario:senha@ep-exemplo.neon.tech/neondb?sslmode=require

```



### 3.2. Conexão Resiliente com SQLAlchemy

Como o plano gratuito do Neon suspende a máquina após inatividade (*auto-suspend*), a conexão do SQLAlchemy foi configurada com pooling ativo para evitar o erro `SSL connection has been closed unexpectedly`:

```python
import os
from dotenv import load_dotenv
from flask import Flask
from flask_sqlalchemy import SQLAlchemy

load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY')

# Compatibilidade de prefixo postgres:// para postgresql://
db_url = os.getenv('DATABASE_URL')
if db_url and db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)

app.config['SQLALCHEMY_DATABASE_URI'] = db_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Resiliência contra o auto-suspend do Neon
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    "pool_pre_ping": True,
    "pool_recycle": 300,
}

db = SQLAlchemy(app)

```

### 3.3. Integrações de APIs Externas no Backend

* **ViaCEP:** Endpoint frontend consumindo a API aberta (`https://viacep.com.br/ws/{cep}/json/`) para autofill de logradouro, bairro, cidade e estado no cadastro/edição de alunos e docentes.
* **BrasilAPI:** Requisição na rota de calendário acadêmico (`https://brasilapi.com.br/api/feriados/v1/{ano}`) mesclando feriados nacionais aos avisos do mural (`eventos_agenda`).

---

## Etapa 4: Arquitetura de Frontend e Componentização Jinja2

O frontend original sofria de redundância massiva (código duplicado de `<head>`, imports de CSS, e navbars clonadas em mais de 10 arquivos). Implementou-se o padrão de Herança de Templates.

### 4.1. Criação do `base.html`

Definido como casca estrutural única do sistema contendo:

* Cabeçalho universal com tags `meta` de responsividade.
* Importação centralizada de `static/style.css` e do script `static/acessibilidade.js`.
* Sistema de exibição automática de mensagens flash (`get_flashed_messages()`).
* Blocos semânticos de substituição:
* `{% block titulo %}`: Define o título na aba do navegador.
* `{% block navbar %}`: Controla a exibição da navegação.
* `{% block conteudo %}`: Recebe a interface específica de cada página.
* `{% block extra_js %}`: Isola scripts JS específicos por tela.



### 4.2. Desacoplamento da Navbar (`navbar.html`)

A barra superior foi extraída para `templates/navbar.html` e chamada no `base.html` via:

```html
{% block navbar %}
    {% include 'navbar.html' %}
{% endblock %}

```

* **Controle por Perfil:** Exibição condicional de links usando Jinja de acordo com a sessão:
* `ADMIN`: Acesso ao painel administrativo, catálogo, grade geral, alunos e professores.
* `PROFESSOR`: Painel docente, catálogo pedagógico, grade e alunos.
* `ALUNO`: Painel do estudante com histórico e aulas.


* **Unificação de Ações:** Botões da direita padronizados sob a classe base `.btn-nav`:
* `◐ Contraste`: Alternância dinâmica de tema WCAG.
* `Meu Perfil`: Redirecionamento unificado com o mesmo estilo visual de pílula.
* `Sair`: Logout seguro do sistema.



### 4.3. Telas com Navbar Restrita

Nas telas de acesso inicial (`login.html` e `primeiro_acesso.html`), o bloco da navbar foi sobrescrito para ocultar os links protegidos, mantendo apenas a marca e o botão de contraste:

```html
{% block navbar %}
<nav class="navbar">
    <div class="navbar-esquerda"><span class="marca-sistema">Portal Escolar</span></div>
    <div class="navbar-direita">
        <button type="button" class="btn-nav btn-contraste" onclick="alternarContraste()">◐ Contraste</button>
    </div>
</nav>
{% endblock %}

```

---

## Etapa 5: Migração e Refatoração dos Templates Filhos

Todos os templates do sistema foram limpos: eliminação de tags de documento completas (`<!DOCTYPE>`, `<html>`, `<body>`, `<main>`) e adoção de `{% extends 'base.html' %}`.

### Telas Refatoradas:

1. **`login.html` & `primeiro_acesso.html`:**
* Centralização absoluta na viewport com `.login-wrapper` e `.cartao-centralizado`.
* Campos de redefinição obrigatória de senha inicial.


2. **`painel_admin.html`:**
* Dashboard da secretaria com visualização de comunicados institucionais e feriados via BrasilAPI.


3. **`painel_professor.html`:**
* Gestão de aulas do dia, controle de presença, diário de classe e calendário docente.


4. **`painel_aluno.html`:**
* Listagem de aulas agendadas com link direto para sala virtual, download de slides/PDFs e autoavaliação.


5. **`gerenciar_aulas.html`:**
* Tabela ampla com filtros combinados (busca textual por aluno, filtro por tema didático e status).
* Eliminação da barra de rolagem horizontal indevida via expansão da largura útil e remoção de colunas redundantes.
* Sistema de edição inline rápida via JavaScript acoplado ao `{% block extra_js %}`.


6. **`gerenciar_alunos.html` & `gerenciar_professores.html`:**
* Listagens em tabela e formulários com autopreenchimento de endereço integrado ao ViaCEP.


7. **`meu_perfil.html`:**
* Edição de dados pessoais, redefinição de senha e atualização de endereço.



---

## Etapa 6: Design System e Otimização do CSS (`style.css`)

A folha de estilo original possuía mais de 440 linhas, múltiplos seletores com `!important` e fragmentos obsoletos do módulo financeiro legado.

### 6.1. Redução e Arquitetura de Variáveis

O arquivo foi condensado para cerca de 150 linhas sem perda funcional. Criou-se um núcleo de variáveis CSS no `:root`:

* `--bg`, `--card`, `--txt`, `--borda`: Estrutura de superfícies e textos neutros.
* `--primaria`, `--primaria-hover`: Cores de ação (botões e links).
* `--nav-bg`, `--nav-txt`, `--nav-muted`: Identidade escura da barra superior.
* `--ok-bg`, `--alert-bg`, `--danger-bg`: Sinalizadores visuais para status acadêmicos.

### 6.2. Acessibilidade WCAG 2.1 e e-MAG (Modo Alto Contraste)

A classe `body.alto-contraste` (ativada via JavaScript) redefine apenas os valores das variáveis sem necessidade de reescrever dezenas de regras CSS:

* Fundo vira branco puro ou preto absoluto conforme o elemento.
* Borda preta universal de alta espessura.
* Navbar em preto absoluto (`#000000`) com destaques em amarelo puro (`#ffff00`).
* Taxa de contraste superior a 7:1 em todos os elementos de texto e foco.

### 6.3. Padronização de Componentes

* **Tabelas:** Alinhamento centralizado, zebra neutra, linhas com hover suave e botões de ação estilizados como links textuais inline (evitando botões pesados em cada célula).
* **Formulários:** Larguras responsivas, `box-sizing: border-box` universal e realce no `:focus`.
* **Badges:** Identificadores padronizados para níveis pedagógicos (`BASICO`, `INTERMEDIARIO`, `AVANCADO`) e status de aula.

---

## Etapa 7: Controle de Versão e Publicação no GitHub

Para disponibilizar o projeto publicamente com segurança:

### 7.1. Ordem Correta de Configuração do Git

1. **Configuração do `.gitignore` ANTES de qualquer commit:**
```text
.env
*.env.local
venv/
.venv/
__pycache__/
*.pyc
instance/
.vscode/

```


2. **Congelamento das Dependências:**
```bash
pip freeze > requirements.txt

```


3. **Auditoria de Arquivos Locais:**
```bash
git status

```


*Checagem visual obrigatória para garantir que o `.env` não está listado para envio.*
4. **Criação do Repositório Remoto:**
* Repositório criado no GitHub como **Public** sem inicializar arquivos padrão (README ou licença).


5. **Commit Inicial e Envio:**
```bash
git init
git add .
git commit -m "feat: arquitetura modular flask com base.html, design system e persistencia neon"
git branch -M main
git remote add origin [https://github.com/SEU_USUARIO/portal-escolar.git](https://github.com/SEU_USUARIO/portal-escolar.git)
git push -u origin main

```



### 7.2. Fluxo de Trabalho em Branch de Refinamento

Para realizar melhorias contínuas sem comprometer a estabilidade da branch `main`:

```bash
# Cria e acessa a branch de trabalho
git checkout -b feature/refinamento-arquivos

# Realização das alterações e commits atômicos
git add .
git commit -m "docs: atualiza scripts ddl/seed e documentacao tecnica"

# Publicação da branch
git push -u origin feature/refinamento-arquivos

```

```

```
