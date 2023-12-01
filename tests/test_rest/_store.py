from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Car:
    id: int
    name: str
