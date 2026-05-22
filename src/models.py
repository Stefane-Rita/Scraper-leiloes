from dataclasses import dataclass
from typing import Optional


@dataclass
class AuctionLot:
    fonte: str
    modelo_veiculo: str
    lance_atual: Optional[float]
    preco_avaliado: Optional[float]
    diferenca_rs: Optional[float]
    diferenca_pct: Optional[float]
    data_leilao: str
    data_finalizacao: str
    oportunidade: str
    condicao_veiculo: str
    condicao_leilao: str
    local_leilao: str
    id_externo: str
    lot_brand: Optional[str] = None
    lot_year: Optional[int] = None
    lot_model: Optional[str] = None

    def to_row(self) -> list:
        return [
            self.fonte,
            self.modelo_veiculo,
            self._fmt_money(self.lance_atual),
            self._fmt_money(self.preco_avaliado),
            self._fmt_money(self.diferenca_rs),
            self._fmt_pct(self.diferenca_pct),
            self.data_leilao,
            self.data_finalizacao,
            self.oportunidade,
            self.condicao_veiculo,
            self.condicao_leilao,
            self.local_leilao,
        ]

    @staticmethod
    def _fmt_money(value: Optional[float]) -> str:
        if value is None:
            return ""
        return f"R$ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

    @staticmethod
    def _fmt_pct(value: Optional[float]) -> str:
        if value is None:
            return ""
        return f"{value:.2f}%".replace(".", ",")


HEADERS = [
    "Fonte",
    "Modelo do Veículo",
    "Lance Atual",
    "Preço Avaliado",
    "Diferença em R$ (Lance vs Avaliação)",
    "Diferença em % (Lance vs Avaliação)",
    "Data do Leilão",
    "Data de Finalização do Leilão",
    "Oportunidade (lance ≤ 45% do avaliado)",
    "Condição do Veículo",
    "Condição do Leilão",
    "Local do Leilão",
]
