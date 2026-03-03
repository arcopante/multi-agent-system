"""
Orquestador + Subagentes Paralelos con GitHub Models (Copilot Pro / GPT-4o)
============================================================================
Usa la API de GitHub Models, que es compatible con el SDK de OpenAI.

Instalación:
    pip install openai fastapi uvicorn

Cómo obtener tu token:
    1. Ve a https://github.com/settings/tokens
    2. Genera un token con scope: models:read
    3. Expórtalo: export GITHUB_TOKEN="ghp_..."

Uso:
    export GITHUB_TOKEN="ghp_..."
    python server_copilot.py
    → Abre http://localhost:8000
"""

import asyncio
import json
import os
from openai import AsyncOpenAI
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# ── Configuración ────────────────────────────────────────────────
app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

client = AsyncOpenAI(
    base_url="https://models.inference.ai.azure.com",
    api_key=os.environ["GITHUB_TOKEN"],
)

MODEL = "gpt-4o"  # Modelos disponibles: gpt-4o, gpt-4o-mini, o1, o1-mini


# ── Tipos ────────────────────────────────────────────────────────
class PreguntaRequest(BaseModel):
    pregunta: str


# ── Llamada al LLM (ahora async nativa con AsyncOpenAI) ──────────
async def llamar_llm(system: str, user: str, max_tokens: int = 500) -> str:
    response = await client.chat.completions.create(
        model=MODEL,
        max_tokens=max_tokens,
        messages=[
            {"role": "system", "content": system},
            {"role": "user",   "content": user},
        ]
    )
    return response.choices[0].message.content


# ── Subagente ────────────────────────────────────────────────────
async def ejecutar_subagente(id: str, rol: str, instruccion: str, contexto: str) -> dict:
    contenido = await llamar_llm(
        system=f"Eres un experto en {rol}. Sé conciso y directo. Responde en español.",
        user=f"Contexto general: {contexto}\n\nTu tarea específica: {instruccion}",
        max_tokens=500
    )
    return {"id": id, "rol": rol, "contenido": contenido}


# ── Endpoint SSE ─────────────────────────────────────────────────
@app.post("/orquestar")
async def orquestar(req: PreguntaRequest):
    async def stream():
        pregunta = req.pregunta

        def evento(tipo: str, data: dict):
            return f"data: {json.dumps({'tipo': tipo, **data}, ensure_ascii=False)}\n\n"

        # PASO 1: Planificación
        yield evento("estado", {"mensaje": "Orquestador analizando la tarea..."})

        plan_texto = await llamar_llm(
            system=(
                "Eres un orquestador de agentes de IA. Divide la pregunta en exactamente 3 "
                "subtareas independientes que puedan resolverse en paralelo. "
                'Responde SOLO con este JSON (sin markdown): '
                '{"subtareas": [{"id":"A","rol":"...","instruccion":"..."},'
                '{"id":"B","rol":"...","instruccion":"..."},'
                '{"id":"C","rol":"...","instruccion":"..."}]}'
            ),
            user=pregunta,
            max_tokens=600
        )

        plan = json.loads(plan_texto.strip())
        subtareas = plan["subtareas"]

        for s in subtareas:
            yield evento("subagente_creado", {"id": s["id"], "rol": s["rol"], "instruccion": s["instruccion"]})

        yield evento("estado", {"mensaje": "Lanzando subagentes en paralelo..."})

        # PASO 2: Subagentes en paralelo (async nativo, sin run_in_executor)
        tareas = [
            ejecutar_subagente(s["id"], s["rol"], s["instruccion"], pregunta)
            for s in subtareas
        ]

        resultados = []
        for coro in asyncio.as_completed(tareas):
            resultado = await coro
            resultados.append(resultado)
            yield evento("subagente_completado", resultado)

        # PASO 3: Síntesis
        yield evento("estado", {"mensaje": "Sintetizando resultados..."})

        contexto_resultados = "\n\n".join([
            f"--- Subagente {r['id']} ({r['rol']}) ---\n{r['contenido']}"
            for r in resultados
        ])

        sintesis = await llamar_llm(
            system="Eres un sintetizador experto. Crea una respuesta final cohesiva en español.",
            user=f"Pregunta: {pregunta}\n\nAnálisis:\n{contexto_resultados}\n\nSintetiza todo.",
            max_tokens=800
        )

        yield evento("sintesis", {"contenido": sintesis})
        yield evento("fin", {})

    return StreamingResponse(stream(), media_type="text/event-stream")


# ── Servir frontend ──────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
async def index():
    with open("index.html", "r", encoding="utf-8") as f:
        return f.read()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
