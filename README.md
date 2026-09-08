# 🎓 Portal Escolar - Sistema de Gestão Acadêmica

![Python](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python&logoColor=white)
![Flask](https://img.shields.io/badge/Flask-Framework-black?logo=flask&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-Neon%20Serverless-4169E1?logo=postgresql&logoColor=white)
![Acessibilidade](https://img.shields.io/badge/Acessibilidade-WCAG%202.1%20%7C%20e--MAG-brightgreen)
![Status](https://img.shields.io/badge/Status-Em%20Produção-success)

Sistema web completo para gestão escolar e pedagógica, desenvolvido em **Python (Flask)** com persistência gerenciada no **PostgreSQL (Neon Tech)**. O projeto adota uma arquitetura modular com herança de templates Jinja2, APIs externas abertas e um **Design System acessível** em conformidade com as diretrizes do WCAG 2.1 e e-MAG.

---

## 📌 Principais Funcionalidades

O sistema conta com controle de acesso baseado em três perfis de usuário (`ADMIN`, `PROFESSOR` e `ALUNO`):

### 🏢 Administração e Secretaria (`ADMIN`)
* **Gestão Cadastral Completa:** Cadastro e atualização de estudantes e professores com preenchimento automático de endereço via **ViaCEP**.
* **Grade Geral de Aulas:** Visualização global de todas as sessões pedagógicas com filtros combinados (busca por aluno, tema e status).
* **Mural Escolar Integrado:** Publicação de comunicados institucionais mesclados dinamicamente com os feriados nacionais fornecidos pela **BrasilAPI**.

### 👨‍🏫 Painel do Docente (`PROFESSOR`)
* **Diário de Classe & Presença:** Lista das aulas agendadas do dia com controle de chamada em tempo real.
* **Agendamento de Mentorias:** Criação de novos encontros individuais com slots padronizados de 1 hora, links de salas virtuais (Google Meet/Teams) e materiais didáticos.
* **Calendário Pedagógico:** Visualização mensal em formato de grid contendo todas as suas sessões e feriados.

### 🎒 Área do Estudante (`ALUNO`)
* **Próximas Sessões:** Acesso rápido ao link da videochamada da aula, materiais em anexo e orientações do professor.
* **Histórico & Autoavaliação:** Confirmação de aula assistida e lançamento de autoavaliação com notas e anotações pessoais.
* **Acompanhamento por Nível:** Visualização de progresso acadêmico vinculado aos níveis pedagógicos (`Básico`, `Intermediário` e `Avançado`).

---

## ♿ Acessibilidade (WCAG 2.1 / e-MAG)

A interface foi projetada com foco total em acessibilidade digital:
* **Modo Alto Contraste Nativo:** Alternância em tempo real para contraste extremo (preto `#000000`, amarelo `#ffff00` e branco `#ffffff`), garantindo legibilidade para usuários com baixa visão ou fotofobia.
* **Design System Orientado a Variáveis CSS:** Layout enxuto, sem regras redundantes de CSS, com escala visual unificada para botões e componentes interativos.
* **Semântica Estruturada:** Tabelas com cabeçalhos acessíveis, formulários com rótulos (`<label>`) explícitos e botões de ação descritivos.

---

## 🛠️ Tecnologias Utilizadas

* **Backend:** Python 3, Flask, SQLAlchemy, Werkzeug / Bcrypt (criptografia de senhas), `python-dotenv`.
* **Banco de Dados:** PostgreSQL 16+ gerenciado no [Neon Tech](https://neon.tech/) (arquitetura Serverless com SSL e pooling de conexões ativo).
* **Frontend:** Jinja2 Templates (arquitetura desacoplada via `base.html` e `navbar.html`), HTML5 semântico, CSS3 Moderno (`:root` vars) e JavaScript Vanilla.
* **APIs Externas Integradas:**
  * [ViaCEP](https://viacep.com.br/) — Autocompletar de endereços nos cadastros.
  * [BrasilAPI](https://brasilapi.com.br/) — Feriados nacionais dinâmicos no calendário escolar.

---

## 📂 Estrutura de Pastas

```text
portal-escolar/
├── static/
│   ├── acessibilidade.js    # Controle de modo alto contraste (localStorage)
│   ├── style.css            # Folha de estilo única com Design System enxuto
│   └── uploads/             # Diretório para PDFs e anexos de aula
├── templates/
│   ├── base.html            # Casca universal da aplicação
│   ├── navbar.html          # Componente de navegação condicional por perfil
│   ├── login.html           # Tela de credenciamento centralizada
│   ├── painel_admin.html    # Painel da secretaria
│   ├── painel_professor.html# Painel do docente com calendário
│   ├── painel_aluno.html    # Painel do estudante
│   ├── gerenciar_aulas.html # Grade geral com filtros e edição rápida
│   └── ...
├── .env.example             # Modelo das variáveis de ambiente necessárias
├── .gitignore               # Proteção de credenciais e arquivos temporários
├── app.py                   # Inicialização do Flask, rotas e regras de negócio
├── requirements.txt         # Lista congelada de dependências Python
├── script-ddl.sql           # Estrutura do banco de dados (DDL)
└── script-seed.sql          # Carga de dados inicial para testes
