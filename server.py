"""
Servidor FastAPI para el Orquestador de Subagentes
===================================================
Instalación:
    pip install anthropic fastapi uvicorn

Uso:
    export ANTHROPIC_API_KEY="sk-ant-..."
    python server.py
    → Abre http://localhost:8000
"""

import asyncio
import json
import anthropic
from dataclasses import dataclass
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# ── Configuración ────────────────────────────────────────────────
app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
client = anthropic.Anthropic()
MODEL = "claude-sonnet-4-20250514"


# ── Tipos ────────────────────────────────────────────────────────
@dataclass
class Subtarea:
    id: str
    rol: str
    instruccion: str

class PreguntaRequest(BaseModel):
    pregunta: str


# ── Lógica de agentes ────────────────────────────────────────────
async def ejecutar_subagente(subtarea: Subtarea, contexto: str) -> dict:
    loop = asyncio.get_event_loop()
    response = await loop.run_in_executor(
        None,
        lambda: client.messages.create(
            model=MODEL,
            max_tokens=500,
            system=f"Eres un experto en {subtarea.rol}. Sé conciso y directo. Responde en español.",
            messages=[{
                "role": "user",
                "content": f"Contexto general: {contexto}\n\nTu tarea específica: {subtarea.instruccion}"
            }]
        )
    )
    return {"id": subtarea.id, "rol": subtarea.rol, "contenido": response.content[0].text}


# ── Endpoint SSE (Server-Sent Events para tiempo real) ───────────
@app.post("/orquestar")
async def orquestar(req: PreguntaRequest):
    async def stream():
        pregunta = req.pregunta

        def evento(tipo: str, data: dict):
            return f"data: {json.dumps({'tipo': tipo, **data}, ensure_ascii=False)}\n\n"

        # PASO 1: Planificación
        yield evento("estado", {"mensaje": "Orquestador analizando la tarea..."})

        loop = asyncio.get_event_loop()
        plan_response = await loop.run_in_executor(
            None,
            lambda: client.messages.create(
                model=MODEL,
                max_tokens=600,
                system=(
                    "Eres un orquestador de agentes de IA. Divide la pregunta en exactamente 3 "
                    "subtareas independientes que puedan resolverse en paralelo. "
                    'Responde SOLO con este JSON (sin markdown): '
                    '{"subtareas": [{"id":"A","rol":"...","instruccion":"..."},'
                    '{"id":"B","rol":"...","instruccion":"..."},'
                    '{"id":"C","rol":"...","instruccion":"..."}]}'
                ),
                messages=[{"role": "user", "content": pregunta}]
            )
        )

        plan = json.loads(plan_response.content[0].text.strip())
        subtareas = [Subtarea(**s) for s in plan["subtareas"]]

        # Enviar plan al frontend
        for s in subtareas:
            yield evento("subagente_creado", {"id": s.id, "rol": s.rol, "instruccion": s.instruccion})

        yield evento("estado", {"mensaje": "Lanzando subagentes en paralelo..."})

        # PASO 2: Subagentes en paralelo
        tareas = [ejecutar_subagente(s, pregunta) for s in subtareas]

        # Lanzar en paralelo y emitir cada resultado conforme llega
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

        sintesis_response = await loop.run_in_executor(
            None,
            lambda: client.messages.create(
                model=MODEL,
                max_tokens=800,
                system="Eres un sintetizador experto. Crea una respuesta final cohesiva en español.",
                messages=[{
                    "role": "user",
                    "content": f"Pregunta: {pregunta}\n\nAnálisis:\n{contexto_resultados}\n\nSintetiza todo."
                }]
            )
        )

        yield evento("sintesis", {"contenido": sintesis_response.content[0].text})
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
