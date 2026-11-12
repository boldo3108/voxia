"""Fila de cosas por decir (preguntas a la IA, frases directas). Se puede ver y editar desde la app."""
import asyncio
import itertools
from dataclasses import dataclass, field


@dataclass
class Item:
    tipo: str                 # "ia" (pregunta), "comentario" (espontáneo) o "decir" (frase directa)
    usuario: str = ""
    texto: str = ""
    msg: object = None        # Mensaje original (si viene del chat)
    al_chat: bool = True      # para "decir": también escribirlo en el chat
    id: int = field(default_factory=itertools.count(1).__next__)


class Fila:
    def __init__(self, maximo: int = 10, al_cambiar=None):
        self.maximo = maximo
        self.items: list[Item] = []
        self._hay = asyncio.Event()
        self.al_cambiar = al_cambiar or (lambda: None)

    def __len__(self):
        return len(self.items)

    def agregar(self, item: Item, prioridad: bool = False) -> bool:
        if len(self.items) >= self.maximo and not prioridad:
            return False
        self.items.insert(0, item) if prioridad else self.items.append(item)
        self._hay.set()
        self.al_cambiar()
        return True

    async def sacar(self) -> Item:
        while not self.items:
            self._hay.clear()
            await self._hay.wait()
        item = self.items.pop(0)
        self.al_cambiar()
        return item

    def quitar(self, item_id: int) -> Item | None:
        for i, it in enumerate(self.items):
            if it.id == item_id:
                self.items.pop(i)
                self.al_cambiar()
                return it
        return None

    def vaciar(self) -> list[Item]:
        quitados, self.items = self.items, []
        self.al_cambiar()
        return quitados
