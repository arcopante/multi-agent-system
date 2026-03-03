# 1. Instalar dependencias
pip install anthropic fastapi uvicorn

# 2. Poner los dos archivos en la misma carpeta

# 3. Arrancar
export ANTHROPIC_API_KEY="sk-ant-..."  
python server.py  


# 4. Abrir en el navegador
http://localhost:8000  
  
  
# Explicaciones técnicas  
  

### Qué hace la interfaz

La clave técnica es que usa **Server-Sent Events (SSE)**  
  
el servidor va enviando eventos al navegador en tiempo real conforme pasan cosas:  
[orquestador planifica]  →  aparecen las 3 tarjetas de subagent  
[subagente A termina]    →  su tarjeta se ilumina en verde  
[subagente B termina]    →  idem (en paralelo, el orden varia)  
[subagente C termina]    →  idem  
[síntesis lista]         →  aparece el resultado final  
  
  
### Cómo está estructurado  

Pregunta del usuario  
       ↓  
[Orquestador] → define 3 subtareas via LLM (JSON)  
       ↓  
[Subagente A] ──┐  
[Subagente B] ──┼── asyncio.gather() → corren al mismo tiempo  
[Subagente C] ──┘  
       ↓  
[Sintetizador] → une los 3 resultados en respuesta final  
  

