"""A tiny router so the sample needs no web framework."""


class Router:
    def __init__(self):
        self.routes = {}

    def _register(self, verb, path):
        def decorator(fn):
            self.routes[(verb, path)] = fn
            return fn
        return decorator

    def get(self, path):
        return self._register("GET", path)

    def post(self, path):
        return self._register("POST", path)


router = Router()
