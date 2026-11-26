import unittest
import importlib.util
from types import SimpleNamespace
from unittest.mock import patch

if importlib.util.find_spec('torch') is None:
    raise unittest.SkipTest('PhoBERT requires the optional requirements_phobert.txt environment')

import torch
from torch import nn

from train_phobert_multitask import ABSA, targets


class FakeEncoder(nn.Module):
    def __init__(self):
        super().__init__()
        self.config = SimpleNamespace(hidden_size=8)
        self.embedding = nn.Embedding(32, 8)

    def forward(self, input_ids, **kwargs):
        return SimpleNamespace(last_hidden_state=self.embedding(input_ids))


class PhoBERTArchitectureTests(unittest.TestCase):
    def test_two_heads_and_masked_aspect_targets(self):
        rows = [{'labels': ['food:POSITIVE', 'service:NEGATIVE']}, {'labels': []}]
        acd, spc = targets(rows)
        self.assertEqual(acd.shape, (2, 5))
        self.assertEqual(spc.shape, (2, 5, 3))
        self.assertEqual(acd[0].sum(), 2)
        self.assertEqual(acd[1].sum(), 0)
        with patch('train_phobert_multitask.AutoModel.from_pretrained', return_value=FakeEncoder()):
            model = ABSA('fake')
        aspect_logits, sentiment_logits = model(input_ids=torch.ones((2, 4), dtype=torch.long))
        self.assertEqual(tuple(aspect_logits.shape), (2, 5))
        self.assertEqual(tuple(sentiment_logits.shape), (2, 5, 3))
        loss = nn.BCEWithLogitsLoss()(aspect_logits, torch.tensor(acd))
        mask = torch.tensor(acd).unsqueeze(-1).expand_as(sentiment_logits)
        loss += (nn.BCEWithLogitsLoss(reduction='none')(
            sentiment_logits, torch.tensor(spc)) * mask).sum() / mask.sum().clamp(min=1)
        loss.backward()
        self.assertTrue(torch.isfinite(model.acd.weight.grad).all())
        self.assertTrue(torch.isfinite(model.spc.weight.grad).all())


if __name__ == '__main__':
    unittest.main()
