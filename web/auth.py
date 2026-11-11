"""
Senha única compartilhada (HTTP Basic Auth) protegendo TODAS as rotas
deste serviço -- chat, feed em tempo real e os arquivos estáticos.

Por quê um middleware ASGI puro, e não `Depends(HTTPBasic())` do FastAPI:
`Depends` só se aplica a rotas de verdade, não ao `app.mount(StaticFiles)`
(é uma sub-aplicação ASGI separada) nem ao handshake do WebSocket da
mesma forma. Um middleware no nível do ASGI intercepta os três tipos de
requisição antes de qualquer um deles rodar.

Sobre o WebSocket: o navegador não deixa JavaScript anexar um header
`Authorization` na conexão WebSocket. Funciona mesmo assim porque, depois
que o navegador autentica via o diálogo nativo do Basic Auth (disparado
ao abrir a página HTML, que é a primeira requisição), ele guarda essa
credencial em cache *por origem* e já manda ela de novo automaticamente
em qualquer requisição seguinte pra mesma origem -- inclusive o handshake
do WebSocket, que tecnicamente é um GET com upgrade.

Sem SITE_PASSWORD definida no ambiente, o middleware não bloqueia nada
(conveniência pra desenvolvimento local).
"""

import base64
import os
import secrets

SITE_PASSWORD = os.environ.get("SITE_PASSWORD")
_REALM = 'Basic realm="olist-rag"'


def _password_ok(auth_header: str) -> bool:
    if not auth_header.startswith("Basic "):
        return False
    try:
        decoded = base64.b64decode(auth_header[6:]).decode("utf-8")
    except Exception:
        return False
    _, _, password = decoded.partition(":")
    return secrets.compare_digest(password, SITE_PASSWORD)


class BasicAuthMiddleware:
    """Middleware ASGI de baixo nível (não `BaseHTTPMiddleware` -- esse
    não intercepta conexões WebSocket, só requisições HTTP comuns)."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] not in ("http", "websocket") or not SITE_PASSWORD:
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers") or [])
        auth_header = headers.get(b"authorization", b"").decode("utf-8", "ignore")

        if _password_ok(auth_header):
            await self.app(scope, receive, send)
            return

        if scope["type"] == "http":
            await send({
                "type": "http.response.start",
                "status": 401,
                "headers": [
                    (b"www-authenticate", _REALM.encode()),
                    (b"content-type", b"text/plain; charset=utf-8"),
                ],
            })
            await send({"type": "http.response.body", "body": b"Senha necessaria."})
        else:  # websocket
            await receive()  # consome o "websocket.connect" antes de responder
            await send({"type": "websocket.close", "code": 1008})  # policy violation
