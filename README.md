# 1. Instalar dependencias
pip install anthropic fastapi uvicorn

# 2. Poner los dos archivos en la misma carpeta
# 3. Arrancar
export ANTHROPIC_API_KEY="sk-ant-..."
python server.py

# 4. Abrir en el navegador
http://localhost:8000
```

---

### Qué hace la interfaz

La clave técnica es que usa **Server-Sent Events (SSE)** — el servidor va enviando eventos al navegador en tiempo real conforme pasan cosas:
```
[orquestador planifica]  →  aparecen las 3 tarjetas de subagentes
[subagente A termina]    →  su tarjeta se ilumina en verde
[subagente B termina]    →  idem (en paralelo, el orden varía)
[subagente C termina]    →  idem
[síntesis lista]         →  aparece el resultado final
