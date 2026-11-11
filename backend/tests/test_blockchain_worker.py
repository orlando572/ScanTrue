"""Confirmación del registro al terminar el envío a Anvil."""

import unittest
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from backend.blockchain.worker import BlockchainWorker


class FakeRepository:
    def __init__(self):
        self.analysis_id = uuid4()
        self.record = SimpleNamespace(id=self.analysis_id, hash_transaccion=None)
        self.saved = []

    def claim_blockchain_analysis(self):
        return self.analysis_id

    def get_blockchain_analysis(self, analysis_id):
        assert analysis_id == self.analysis_id
        return self.record

    def set_blockchain_state(self, analysis_id, **values):
        assert analysis_id == self.analysis_id
        self.saved.append(values)


class FakeClient:
    def __init__(self, verifications):
        self.verifications = iter(verifications)

    def check_ready(self):
        pass

    def find_registration(self, _analysis_id):
        return None

    def send(self, _record):
        return '0x' + 'a' * 64

    def verify(self, _record, transaction_hash):
        assert transaction_hash == '0x' + 'a' * 64
        return next(self.verifications)


class BlockchainWorkerTests(unittest.TestCase):
    def test_confirms_when_receipt_is_available_after_send(self):
        repository = FakeRepository()
        with patch('backend.blockchain.worker.time.sleep') as sleep:
            self.assertTrue(BlockchainWorker(repository, FakeClient([None, True])).process_one())
        self.assertEqual(repository.saved[0]['state'], 'confirmado')
        self.assertEqual(repository.saved[0]['transaction_hash'], '0x' + 'a' * 64)
        sleep.assert_called_once_with(1)

    def test_keeps_hash_pending_when_receipt_is_not_ready(self):
        repository = FakeRepository()
        with patch('backend.blockchain.worker.time.sleep'):
            self.assertTrue(BlockchainWorker(repository, FakeClient([None] * 6)).process_one())
        self.assertEqual(repository.saved[0]['state'], 'pendiente')
        self.assertEqual(repository.saved[0]['transaction_hash'], '0x' + 'a' * 64)


if __name__ == '__main__':
    unittest.main()
