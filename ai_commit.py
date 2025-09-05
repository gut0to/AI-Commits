#!/usr/bin/env python3
import os, sys, subprocess, tempfile, argparse
from pathlib import Path
from dotenv import load_dotenv
load_dotenv()

DEFAULT_MODEL = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
MAX_DIFF_CHARS = int(os.getenv("AICOMMIT_MAX_DIFF_CHARS", "40000"))

PROMPT_TEMPLATE = """Você é um assistente que escreve mensagens de commit curtas e claras no padrão Conventional Commits.
Responda APENAS com a linha de assunto (sem corpo), no idioma: {lang}.
Preferências:
- Tipo: {commit_type} (feat, fix, chore, refactor, docs, test, perf, build, ci, style)
- Máximo ~72 caracteres.
- Descreva a mudança, não o arquivo; verbo no imperativo (ex.: "add", "fix", "update").
- Inclua escopo quando fizer sentido (ex.: feat(user): ...).
- NÃO inclua ponto final.

Se a mudança for mista, escolha o tipo predominante; se incerto, use "chore".

A seguir está o git diff (unificado, sem cores). Gere UMA linha:

<diff>
{diff}
</diff>
"""

def run(cmd, cwd=None, check=True):
    env = os.environ.copy()
    env.setdefault("GIT_PAGER", "cat")
    env.setdefault("LANG", "C.UTF-8")
    env.setdefault("LC_ALL", "C.UTF-8")
    return subprocess.run(
        cmd, cwd=cwd, check=check, text=True, capture_output=True,
        encoding="utf-8", errors="replace", env=env
    )

def get_repo_root() -> Path:
    try:
        out = run(["git", "rev-parse", "--show-toplevel"])
        return Path((out.stdout or "").strip())
    except subprocess.CalledProcessError:
        print(" Não é um repositório git.", file=sys.stderr)
        sys.exit(1)

def get_diff(staged=True) -> str:
    args = ["git", "diff", "--no-color", "--unified=0", "--no-ext-diff", "--text"]
    if staged: args.insert(2, "--staged")
    try:
        out = run(args)
        return out.stdout or ""
    except subprocess.CalledProcessError as e:
        print(e.stderr, file=sys.stderr); sys.exit(1)

def strip_sensitive_lines(diff: str) -> str:
    filtered = []
    for line in diff.splitlines():
        low = line.lower()
        if ("api_key" in low or "apikey" in low or "secret" in low or "token" in low) and line.startswith("+"):
            continue
        if (".env" in low) and (line.startswith("+++") or line.startswith("---")):
            continue
        filtered.append(line)
    return "\n".join(filtered)

def editor_edit(initial_text: str) -> str:
    editor = os.getenv("EDITOR") or os.getenv("VISUAL")
    if not editor: return initial_text
    with tempfile.NamedTemporaryFile("w+", suffix=".tmp", delete=False, encoding="utf-8") as tf:
        tf.write(initial_text); tf.flush(); path = tf.name
    try:
        subprocess.run([*editor.split(), path], check=False)
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return (f.read() or "").strip()
    finally:
        try: os.remove(path)
        except OSError: pass

def ensure_gemini_key():
    if not os.getenv("GOOGLE_API_KEY"):
        print(" Defina GOOGLE_API_KEY no .env ou no ambiente.", file=sys.stderr)
        sys.exit(1)

def call_gemini(model_name: str, prompt: str) -> str:
    import google.generativeai as genai
    genai.configure(api_key=os.environ["GOOGLE_API_KEY"])
    model = genai.GenerativeModel(model_name)
    resp = model.generate_content(prompt)
    if not hasattr(resp, "candidates") or not resp.candidates:
        fb = getattr(resp, "prompt_feedback", None)
        reason = getattr(fb, "block_reason", "unknown") if fb else "unknown"
        raise RuntimeError(f"Resposta bloqueada pelo modelo (razão: {reason}). Ajuste o diff/prompt.")
    text = getattr(resp, "text", None)
    if not text:
        parts = []
        for cand in resp.candidates:
            content = getattr(cand, "content", {}) or {}
            for part in content.get("parts", []):
                if isinstance(part, dict) and "text" in part:
                    parts.append(part["text"])
        text = "\n".join(parts).strip()
    if not text: raise RuntimeError("Resposta do Gemini vazia.")
    return text.strip()

def main():
    parser = argparse.ArgumentParser(description="Gera mensagem de commit com Gemini a partir do git diff.")
    parser.add_argument("--unstaged", action="store_true", help="Usar diff não-staged (por padrão usa --staged).")
    parser.add_argument("--type", dest="ctype", default="chore",
                        help="Tipo Conventional Commit (feat, fix, chore, refactor, docs, test, perf, build, ci, style).")
    parser.add_argument("--lang", default="pt-BR", help="Idioma da mensagem (ex.: pt-BR ou en).")
    parser.add_argument("--no-edit", action="store_true", help="Não abrir editor; commitar direto se possível.")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Modelo Gemini (padrão via env GEMINI_MODEL).")
    parser.add_argument("--print-only", action="store_true", help="Apenas imprimir a mensagem, não executar git commit.")
    args = parser.parse_args()

    repo = get_repo_root(); os.chdir(repo)

    if not args.unstaged:
        staged = run(["git", "diff", "--name-only", "--staged"])
        if not (staged.stdout or "").strip():
            print("Nenhum arquivo staged. Dica: git add -A  (ou use --unstaged).")

    diff = get_diff(staged=not args.unstaged)
    if not diff.strip():
        print(" Diff vazio. Nada para descrever.", file=sys.stderr); sys.exit(1)

    diff = strip_sensitive_lines(diff)
    truncated = False
    if len(diff) > MAX_DIFF_CHARS:
        diff = diff[:MAX_DIFF_CHARS]; truncated = True

    prompt = PROMPT_TEMPLATE.format(lang=args.lang, commit_type=args.ctype, diff=diff)

    ensure_gemini_key()
    try:
        message = call_gemini(args.model, prompt)
    except Exception as e:
        print(f" Erro chamando Gemini: {e}", file=sys.stderr); sys.exit(1)

    if truncated: message = f"{message} (truncated diff)"
    message = " ".join(message.splitlines()).strip().strip('"').strip("'")

    print("\n--- Mensagem sugerida ---"); print(message); print("-------------------------\n")

    final_msg = message if args.no_edit else editor_edit(message)
    final_msg = " ".join((final_msg or "").splitlines()).strip()
    if not final_msg:
        print(" Mensagem vazia após edição.", file=sys.stderr); sys.exit(1)

    if args.print_only:
        print(final_msg); return

    try:
        run(["git", "commit", "-m", final_msg], check=True)
        print(f" Commit feito: {final_msg}")
    except subprocess.CalledProcessError as e:
        print("Falha ao commitar. Faça git add.", file=sys.stderr)
        print(e.stderr, file=sys.stderr); sys.exit(1)

if __name__ == "__main__":
    os.environ.setdefault("PYTHONIOENCODING","utf-8")
    os.environ.setdefault("PYTHONUTF8","1")
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception: pass
    main()
