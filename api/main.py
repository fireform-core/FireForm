from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from api.routes import templates, forms

app = FastAPI(title="FireForm API")

@app.get("/", response_class=HTMLResponse)
def root():
    return """
    <html>
        <head>
            <title>FireForm API</title>
            <style>
                body { font-family: sans-serif; display: flex; flex-direction: column; align-items: center; justify-content: center; height: 100vh; background-color: #f0f2f5; }
                .container { background: white; padding: 2rem; border-radius: 8px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); text-align: center; }
                h1 { color: #ff4b2b; }
                a { color: #007bff; text-decoration: none; font-weight: bold; }
            </style>
        </head>
        <body>
            <div class="container">
                <h1>🔥 FireForm API</h1>
                <p>Digital Public Good for First Responders</p>
                <p>Visit the <a href="/docs">Interactive API Documentation</a> to test endpoints.</p>
            </div>
        </body>
    </html>
    """

app.include_router(templates.router)
app.include_router(forms.router)