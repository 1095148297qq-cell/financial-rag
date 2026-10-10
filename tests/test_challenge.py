"""Prevent confounded experiments and accidental paid fallback; no inference."""
import unittest
from unittest.mock import patch
from financial_rag import llm
from financial_rag.challenge_evaluate import filters


class ChallengeSafetyTests(unittest.TestCase):
    def test_model_change_blocks_before_network_or_ledger(self):
        with patch.object(llm,'configuration',return_value=('chatgpt_oauth','https://example.invalid','sentinel','other')):
            with patch.object(llm.requests,'post') as post, patch.object(llm.Path,'open') as opened:
                with self.assertRaisesRegex(RuntimeError,'模型'):
                    llm.answer('question',[],required_model='frozen')
                post.assert_not_called()
                opened.assert_not_called()

    def test_paid_auth_blocks_even_when_model_matches(self):
        with patch.object(llm,'configuration',return_value=('api_key','https://example.invalid','sentinel','frozen')):
            with patch.object(llm.requests,'post') as post:
                with self.assertRaisesRegex(RuntimeError,'授权'):
                    llm.answer('question',[],required_model='frozen',required_auth_mode='chatgpt_oauth')
                post.assert_not_called()

    def test_distractor_filter_is_not_answer_key_company(self):
        companies,years=filters('山西汾酒与古井贡酒仅为背景，请只回答贵州茅台2025年情况')
        self.assertEqual(set(companies),{'山西汾酒','古井贡酒','贵州茅台'})
        self.assertEqual(years,[2025])


if __name__=='__main__':
    unittest.main()
