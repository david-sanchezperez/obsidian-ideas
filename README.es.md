[🇬🇧 English](README.md) · [🇪🇸 Castellano](README.es.md)

---

# 🗒️ obsidian-ideas

Un bot de Telegram que convierte enlaces e ideas sueltas en notas de Obsidian buscables — y, cuando una idea encaja de forma concreta con algo que uno de tus propios proyectos puede hacer, despacha una tarea autónoma para ello.

## Qué hace

1. **Captura** — pega un enlace o una idea en el bot. La resume (vía LLM) y la guarda como nota Markdown en tu vault de Obsidian, etiquetada.
2. **Búsqueda** — `/buscar <término>` busca en tus notas guardadas.
3. **Encaje** — cada nota se compara contra la lista de tus proyectos activos (construida a partir de su `README.md`, más un bloque opcional de capacidades en `AGENTS.md` — ver más abajo). Si hay un encaje concreto, recibes una explicación de una línea en Telegram.
4. **Despacho** — si el proyecto declara una capacidad que encaja, el bot abre una tarea autónoma contra una API de orquestador (con la forma de [agent-loops](https://github.com/danifernandezs/agent-loops), pero no atada a él). Si el orquestador no responde (p. ej. tu equipo está apagado), la nota se encola y se reintenta en un digest semanal.

## Inicio rápido

```bash
cp .env.example .env
# rellena TELEGRAM_TOKEN, DEEPSEEK_API_KEY, VAULT_HOST_PATH, ...
docker compose up -d
```

## Tags

Cada nota recibe entre 1 y 3 tags de un vocabulario cerrado (`ALLOWED_TAGS` en
`summarize.py`) — el LLM elige de esa lista, nunca inventa tags nuevos. Edita esa
lista para ajustarla a tus propios temas.

También puedes forzar un tag tú mismo poniendo un `#hashtag` en el mensaje que le
mandas al bot (debe coincidir con uno de la lista, p. ej. `#learning`, `#todo`) — se
añade a los que haya elegido el LLM, y se muestra en la respuesta del bot.

## Declarar qué puede hacer un proyecto

Añade un `AGENTS.md` en cualquiera de tus repos con un bloque `capabilities`:

```yaml
capabilities:
  - id: evaluate-llm-candidate
    when: "una nota menciona un modelo LLM nuevo de pesos abiertos que cabe en tu hardware"
    action: "abrir una tarea que lo compare contra tu configuración actual"
    constraints:
      - "nunca promocionar automáticamente — solo producir un veredicto para que lo revise un humano"
```

Ejecuta `python3 generate_projects.py` (lee cada repo bajo un directorio de código configurado) para reconstruir `projects.md`/`repos.json` — el resumen que usa el clasificador. Un encaje con una capacidad declarada es una señal mucho más fuerte que "el tema suena relacionado", y el clasificador está instruido para priorizarlo.

## Contrato de la API del orquestador

El bot espera, en `AGENT_LOOPS_URL`:

| Endpoint | Propósito |
|---|---|
| `GET /api/boards` | listar tableros (uno por slug de proyecto) |
| `POST /api/boards` | crear un tablero si falta |
| `POST /api/tasks` | crear una tarea (`title`, `body`, `repo_url`, `repo_branch`, `board`, `tenant` opcional) |

Es opcional — sin `AGENT_LOOPS_URL` configurada, el bot sigue capturando y buscando notas, simplemente nunca despacha nada.

## Requisitos

- Un token de bot de Telegram (vía [@BotFather](https://t.me/BotFather))
- Una API key de DeepSeek (resumen + encaje)
- Un vault de Obsidian (o cualquier carpeta de ficheros Markdown) accesible desde el host que corre Docker

## Seguridad

- Lista blanca de IDs de usuario de Telegram (`TELEGRAM_ALLOWED_USERS`)
- `.env` excluido vía `.gitignore` — nunca commitear secretos
- El bot solo abre tareas en una rama (`task/<id>`), nunca toca `main` directamente
