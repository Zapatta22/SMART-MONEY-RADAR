"""Configuração local do SMR e proteção explícita para acesso à rede."""

from dataclasses import dataclass, field
import os
from pathlib import Path
from urllib.parse import urlencode

from dotenv import load_dotenv


class SettingsError(ValueError):
    """Configuração ausente ou inválida para uma operação remota."""


@dataclass(frozen=True)
class HeliusSettings:
    api_key: str = field(repr=False)
    cluster: str = "mainnet"
    database_path: Path = Path("data/smr_history.sqlite3")
    request_timeout_seconds: float = 20.0

    def __post_init__(self) -> None:
        if not self.api_key.strip():
            raise SettingsError("HELIUS_API_KEY não pode estar vazia.")
        if self.cluster not in {"mainnet", "devnet"}:
            raise SettingsError("SOLANA_CLUSTER deve ser 'mainnet' ou 'devnet'.")
        if self.request_timeout_seconds <= 0:
            raise SettingsError("O timeout RPC deve ser positivo.")

    @property
    def http_url(self) -> str:
        return self._endpoint("https")

    @property
    def websocket_url(self) -> str:
        return self._endpoint("wss")

    def _endpoint(self, scheme: str) -> str:
        host = f"{self.cluster}.helius-rpc.com"
        return f"{scheme}://{host}/?{urlencode({'api-key': self.api_key})}"

    @classmethod
    def from_environment(cls) -> "HeliusSettings":
        """Carrega .env/ambiente e exige autorização para qualquer acesso remoto."""
        project_root = Path(__file__).resolve().parents[2]
        load_dotenv(project_root / ".env", override=False)

        allow_network = os.getenv("SMR_ALLOW_NETWORK", "").strip().lower()
        if allow_network not in {"1", "true", "yes"}:
            raise SettingsError(
                "Acesso à rede desativado. Revise os limites do Helius e defina "
                "SMR_ALLOW_NETWORK=true para autorizar chamadas remotas."
            )

        api_key = os.getenv("HELIUS_API_KEY", "").strip()
        if not api_key or api_key == "replace_with_your_helius_api_key":
            raise SettingsError(
                "Configure HELIUS_API_KEY no ambiente ou no arquivo .env."
            )

        cluster = os.getenv("SOLANA_CLUSTER", "mainnet").strip().lower()
        if cluster not in {"mainnet", "devnet"}:
            raise SettingsError("SOLANA_CLUSTER deve ser 'mainnet' ou 'devnet'.")

        database_path = Path(
            os.getenv("SMR_DB_PATH", str(project_root / "data" / "smr_history.sqlite3"))
        ).expanduser()
        return cls(api_key=api_key, cluster=cluster, database_path=database_path)