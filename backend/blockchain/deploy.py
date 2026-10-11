"""Despliega el contrato compilado en Anvil y guarda solo metadatos locales."""

import json
import os
from pathlib import Path

from dotenv import load_dotenv
from web3 import Web3

from backend.core.config import ENV_FILE


BACKEND = Path(__file__).resolve().parents[1]
ARTIFACT = BACKEND / "blockchain/out/ScanTrueRegistry.sol/ScanTrueRegistry.json"
DEPLOYMENT = BACKEND / ".local/contract.json"


def main() -> None:
    load_dotenv(ENV_FILE, override=False)
    private_key = os.getenv("BLOCKCHAIN_PRIVATE_KEY", "").strip()
    if not private_key:
        raise SystemExit("Configura BLOCKCHAIN_PRIVATE_KEY en backend/.env.")
    if not ARTIFACT.is_file():
        raise SystemExit("Compila primero el contrato con Forge.")

    rpc_url = os.getenv("BLOCKCHAIN_RPC_URL", "http://127.0.0.1:8545").strip()
    chain_id = int(os.getenv("BLOCKCHAIN_CHAIN_ID", "31337"))
    web3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={"timeout": 5}))
    if web3.eth.chain_id != chain_id:
        raise SystemExit("El chain ID de Anvil no coincide con BLOCKCHAIN_CHAIN_ID.")
    if DEPLOYMENT.exists():
        prior = json.loads(DEPLOYMENT.read_text(encoding="utf-8"))
        if prior["chain_id"] == chain_id and web3.eth.get_code(prior["address"]):
            actual_block_hash = Web3.to_hex(
                web3.eth.get_block(prior["deployment_block"])["hash"]
            )
            if "deployment_block_hash" in prior and prior["deployment_block_hash"] != actual_block_hash:
                raise SystemExit("El estado de Anvil no coincide con el despliegue guardado.")
            if "deployment_block_hash" not in prior:
                prior["deployment_block_hash"] = actual_block_hash
                DEPLOYMENT.write_text(
                    json.dumps(prior, ensure_ascii=False, indent=2), encoding="utf-8"
                )
            print(f"Contrato ya desplegado: {prior['address']}")
            return
        raise SystemExit(
            "Hay un despliegue anterior sin contrato en esta cadena. "
            "Revisa el estado de Anvil antes de desplegar de nuevo."
        )

    artifact = json.loads(ARTIFACT.read_text(encoding="utf-8"))
    account = web3.eth.account.from_key(private_key)
    contract = web3.eth.contract(
        abi=artifact["abi"], bytecode=artifact["bytecode"]["object"]
    )
    transaction = contract.constructor().build_transaction(
        {
            "from": account.address,
            "nonce": web3.eth.get_transaction_count(account.address, "pending"),
            "chainId": chain_id,
            "gas": 1_500_000,
            "gasPrice": web3.eth.gas_price,
        }
    )
    signed = account.sign_transaction(transaction)
    transaction_hash = web3.eth.send_raw_transaction(signed.raw_transaction)
    receipt = web3.eth.wait_for_transaction_receipt(transaction_hash, timeout=30)
    if receipt["status"] != 1 or not receipt["contractAddress"]:
        raise SystemExit("Falló el despliegue del contrato.")

    DEPLOYMENT.parent.mkdir(parents=True, exist_ok=True)
    DEPLOYMENT.write_text(
        json.dumps(
            {
                "chain_id": chain_id,
                "address": receipt["contractAddress"],
                "abi": artifact["abi"],
                "deployment_block": receipt["blockNumber"],
                "deployment_block_hash": Web3.to_hex(receipt["blockHash"]),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"Contrato desplegado: {receipt['contractAddress']}")


if __name__ == "__main__":
    main()
