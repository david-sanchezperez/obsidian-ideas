# Infraestructura desplegada (no son repos propios — solo contexto)

Mantenido a mano. No son destino de tareas de agent-loops (no hay repo propio al
que abrir PR), pero ayudan a la evaluación de encaje a entender qué hay ya montado.
No asumas a qué proyecto "pertenece" cada pieza — decide eso caso por caso a partir
de la nota y la descripción de cada proyecto, no de una asociación fija aquí.

- **memanto** — RAG / memoria persistente on-prem (pipx, sin fork propio), puerto :8000.
  Usado por `agent-loops` como backend de memoria de los agentes.
- **LiteLLM proxy** — puerto :4000, enruta a llama.cpp local y modelos remotos.
  Usado por `agent-loops`. Ver [[ref_local_llm_stack]].
- **agent-loops** — orquestador de tareas autónomas multi-agente (de un compañero,
  no es tuyo, uso propio vía la API/queue).
