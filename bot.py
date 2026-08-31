"""Bot de Telegram: pega un enlace o una idea, se guarda resumida en el vault."""
import logging
import os
from datetime import time as dt_time

from dotenv import load_dotenv
from telegram import Bot, Update
from telegram.ext import Application, ContextTypes, MessageHandler, CommandHandler, filters

from dispatch import dispatch_task, retry_pending, sync_dispatch_statuses
from notes import VAULT_DIR, read_dispatch, read_tags, save_note, write_dispatch
from review import evaluate_fit, load_notes, load_repos, review
from summarize import ALLOWED_TAGS, process_message, process_pdf

load_dotenv()

logging.basicConfig(level=logging.INFO)
# httpx loguea la URL completa de cada petición a INFO, y la API de Telegram
# lleva el token del bot embebido en la URL (/bot<TOKEN>/metodo) — sin esto,
# cada reinicio filtra el token en los logs del contenedor.
logging.getLogger("httpx").setLevel(logging.WARNING)
log = logging.getLogger(__name__)

ALLOWED_USERS = {int(u) for u in os.environ.get("TELEGRAM_ALLOWED_USERS", "").split(",") if u}


def _authorized(update: Update) -> bool:
    return not ALLOWED_USERS or update.effective_user.id in ALLOWED_USERS


async def _save_and_reply(update: Update, result: dict) -> None:
    path = save_note(result["title"], result["summary"], result["tags"], result["source_url"])
    reply = f"Guardado: {path.name}\n\n{result['summary']}"
    if result["tags"]:
        reply += "\n\n🏷️ " + ", ".join(result["tags"])
    try:
        repos = load_repos()
        fit = evaluate_fit(path.read_text(encoding="utf-8"), repos)
        if fit:
            reply += f"\n\n📌 {fit['telegram_note']}"
            try:
                task = dispatch_task(fit, repos[fit["project_slug"]])
                reply += (
                    f"\n🤖 Tarea encolada en agent-loops ({fit['project_slug']}). "
                    f"Estado: {task.get('status', 'triage')}. Usa /tareas para ver el progreso."
                )
                write_dispatch(path, "dispatched", fit, task)
            except Exception:
                log.exception("Error encolando tarea en agent-loops")
                reply += "\n⚠️ No se ha podido encolar ahora (¿PC apagado?). Se reintentará en el digest semanal."
                write_dispatch(path, "pending", fit)
        else:
            reply += "\n\n🔍 Sin encaje claro con tus proyectos activos."
    except Exception:
        log.exception("Error evaluando encaje con proyectos activos")
        reply += "\n\n⚠️ No se ha podido evaluar el encaje con proyectos activos."
    await update.message.reply_text(reply)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorized(update):
        return
    message = update.message.text
    await update.message.reply_text("Procesando...")
    try:
        result = process_message(message)
        await _save_and_reply(update, result)
    except Exception:
        log.exception("Error procesando mensaje")
        await update.message.reply_text("No he podido procesar esto. Revisa los logs.")


async def handle_pdf(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorized(update):
        return
    doc = update.message.document
    await update.message.reply_text("Procesando PDF...")
    try:
        file = await doc.get_file()
        data = bytes(await file.download_as_bytearray())
        result = process_pdf(data, doc.file_name or "documento.pdf")
        await _save_and_reply(update, result)
    except Exception:
        log.exception("Error procesando PDF")
        await update.message.reply_text("No he podido procesar este PDF. Revisa los logs.")


async def buscar(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorized(update):
        return
    query = " ".join(context.args)
    if not query:
        await update.message.reply_text("Uso: /buscar <término>")
        return
    from pathlib import Path

    vault = Path(__file__).parent / "vault"
    matches = []
    for note in vault.glob("*.md"):
        content = note.read_text(encoding="utf-8")
        if query.lower() in content.lower():
            matches.append(note.name)
    if matches:
        await update.message.reply_text("Notas encontradas:\n" + "\n".join(matches[:20]))
    else:
        await update.message.reply_text("Sin resultados.")


async def tag(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorized(update):
        return
    query = " ".join(context.args)
    if not query:
        await update.message.reply_text("Uso: /tag <nombre>\nTags disponibles: " + ", ".join(ALLOWED_TAGS))
        return
    if query not in ALLOWED_TAGS:
        await update.message.reply_text(f"Tag desconocido. Disponibles: {', '.join(ALLOWED_TAGS)}")
        return
    matches = [note.name for note in VAULT_DIR.glob("*.md") if query in read_tags(note)]
    if matches:
        await update.message.reply_text(f"Notas con #{query}:\n" + "\n".join(sorted(matches)[:20]))
    else:
        await update.message.reply_text(f"Sin notas con #{query}.")


async def _send_review(bot: Bot, chat_id: int) -> None:
    notes = load_notes(VAULT_DIR)
    if not notes:
        return
    result = review(notes)
    for i in range(0, len(result), 4000):
        await bot.send_message(chat_id=chat_id, text=result[i : i + 4000])


async def revisar(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorized(update):
        return
    if not load_notes(VAULT_DIR):
        await update.message.reply_text("No hay notas guardadas todavía.")
        return
    await update.message.reply_text("Revisando notas...")
    try:
        await _send_review(context.bot, update.effective_chat.id)
    except Exception:
        log.exception("Error revisando notas")
        await update.message.reply_text("No he podido revisar las notas. Revisa los logs.")


STATUS_LABELS = {
    "triage": "🕒 en cola (aún sin decidir cómo trocearla)",
    "todo": "🕒 en cola",
    "ready": "🕒 lista para que un agente la coja",
    "running": "⚙️ trabajándose ahora mismo",
    "blocked": "🚧 bloqueada, necesita revisión",
    "done": "✅ terminada",
    "archived": "✅ terminada (archivada)",
    "gave_up": "❌ abandonada tras varios intentos",
}


async def tareas(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorized(update):
        return
    dispatched = []
    for note in VAULT_DIR.glob("*.md"):
        fit = read_dispatch(note)
        if fit and fit.get("status") == "dispatched" and fit.get("task_id"):
            dispatched.append(fit)
    if not dispatched:
        await update.message.reply_text("No hay ninguna idea trabajándose ahora mismo.")
        return
    await update.message.reply_text("Consultando agent-loops...")
    try:
        sync_dispatch_statuses(VAULT_DIR)  # refresca antes de listar
    except Exception:
        log.exception("Error sincronizando estado de tareas para /tareas")
    lines = []
    for note in VAULT_DIR.glob("*.md"):
        fit = read_dispatch(note)
        if not fit or fit.get("status") != "dispatched" or not fit.get("task_id"):
            continue
        label = STATUS_LABELS.get(fit.get("agent_loops_status"), fit.get("agent_loops_status", "?"))
        lines.append(f"• {fit['task_title']} ({fit['project_slug']}) — {label}")
    await update.message.reply_text("\n".join(lines) if lines else "No hay ninguna idea trabajándose ahora mismo.")


async def sync_tasks(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Job periódico: si alguna tarea despachada llegó a un estado terminal
    (done/archived/blocked/gave_up), avisa por Telegram — es el único punto
    en que te enteras sin tener que preguntar tú con /tareas."""
    try:
        changed = sync_dispatch_statuses(VAULT_DIR)
    except Exception:
        log.exception("Error en el sync periódico de tareas")
        return
    if not changed:
        return
    for item in changed:
        label = STATUS_LABELS.get(item["status"], item["status"])
        text = f"{label}\n{item['task_title']} ({item['project_slug']})"
        for user_id in ALLOWED_USERS:
            try:
                await context.bot.send_message(chat_id=user_id, text=text)
            except Exception:
                log.exception("Error notificando cambio de estado a %s", user_id)


async def digest_semanal(context: ContextTypes.DEFAULT_TYPE) -> None:
    attempted = ok = 0
    try:
        attempted, ok = retry_pending(VAULT_DIR, load_repos())
    except Exception:
        log.exception("Error reintentando tareas pendientes")
    for user_id in ALLOWED_USERS:
        try:
            if ok:
                await context.bot.send_message(
                    chat_id=user_id,
                    text=f"🤖 Encoladas {ok}/{attempted} tareas pendientes que no se pudieron lanzar antes.",
                )
            await _send_review(context.bot, user_id)
        except Exception:
            log.exception("Error en el digest semanal para %s", user_id)


def main() -> None:
    token = os.environ["TELEGRAM_TOKEN"]
    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("buscar", buscar))
    app.add_handler(CommandHandler("tag", tag))
    app.add_handler(CommandHandler("revisar", revisar))
    app.add_handler(CommandHandler("tareas", tareas))
    app.add_handler(MessageHandler(filters.Document.PDF, handle_pdf))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    if ALLOWED_USERS:
        # Lunes 08:00 UTC (~09:00-10:00 hora de España según horario de verano)
        app.job_queue.run_daily(digest_semanal, time=dt_time(hour=8, minute=0), days=(0,))
        # Cada 20 min: la única forma de enterarte de un done/blocked sin preguntar tú
        app.job_queue.run_repeating(sync_tasks, interval=20 * 60, first=60)
    else:
        log.warning("TELEGRAM_ALLOWED_USERS vacío: el digest semanal no tiene a quién enviarse")
    app.run_polling()


if __name__ == "__main__":
    main()
