from channels.middleware import BaseMiddleware


class COOPMiddleware(BaseMiddleware):
    def __call__(self, scope, receive, send):
        async def wrapped_send(message):
            if message["type"] == "http.response.start":
                message["headers"].append((b"Cross-Origin-Opener-Policy", b"same-origin-allow-popups"))
            await send(message)

        return self.inner(scope, receive, wrapped_send)
