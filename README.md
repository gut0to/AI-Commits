# AI-Commit

🚀 Automatize suas mensagens de commit com **Gemini AI**.  
Este projeto gera mensagens claras e padronizadas no estilo **Conventional Commits**, direto a partir do `git diff`.

---

##  Funcionalidades
- Geração automática de mensagens de commit no padrão [Conventional Commits](https://www.conventionalcommits.org/).
- Suporte a múltiplos tipos (`feat`, `fix`, `chore`, `docs`, `refactor`, `test`, `perf`, etc.).
- Idioma configurável (`pt-BR` ou `en`).
- Evita expor segredos (`.env`, `API_KEY`, etc.).
- Integração direta com o fluxo Git (`git add` → `ai_commit.py` → `git push`).
- Configurável via `.env`.

---

##  Instalação e Configuração

Clone este repositório e crie um ambiente virtual:

```bash
git clone https://github.com/SEU_USUARIO/ai-commit-gen.git
cd ai-commit-gen

# Criar ambiente virtual
python -m venv .venv

# Ativar no Windows
.\.venv\Scripts\Activate.ps1

# Ativar no Linux/macOS
source .venv/bin/activate

# Instalar dependências
pip install -r requirements.txt

# Criar o arquivo .env baseado em .env.example
echo "GOOGLE_API_KEY=sua_chave_do_gemini_aqui" > .env
echo "GEMINI_MODEL=gemini-1.5-flash" >> .env
echo "AICOMMIT_MAX_DIFF_CHARS=40000" >> .env