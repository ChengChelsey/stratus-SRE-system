from abc import abstractmethod

from pydantic import BaseModel, Field
from pydantic.dataclasses import dataclass


@dataclass
class OracleResult:
    success: bool
    message: dict


# Assume that all oracles are sound because we cannot come up with a complete oracle at least for now.
class OracleBase(BaseModel):
    passable: bool = Field(default=False)

    @abstractmethod
    def validate(self) -> OracleResult:
        pass
