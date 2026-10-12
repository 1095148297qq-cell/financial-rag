"""Meaningful public-auth and request-isolation checks; no paid model calls."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch,MagicMock
from fastapi.testclient import TestClient
from financial_rag import server
from financial_rag.extract import table_header

class PublicBackendTests(unittest.TestCase):
    def setUp(self):
        self.client=TestClient(server.app)
        self.temp=tempfile.TemporaryDirectory()
        self.index=Path(self.temp.name)
        (self.index/'version.json').write_text(json.dumps({'fingerprint':'test'}))
        self.patches=[patch.object(server,'INDEX',self.index),patch.object(server,'LOCAL',False)]
        for p in self.patches:p.start()

    def tearDown(self):
        for p in reversed(self.patches):p.stop()
        self.temp.cleanup()

    def test_public_rejects_local_even_from_loopback(self):
        with patch.object(server,'answer') as model:
            response=self.client.post('/api/query',json={'question':'营业收入多少','generate':True,'auth':'local'},headers={'Origin':'http://127.0.0.1:3000'})
            self.assertEqual(response.status_code,403);model.assert_not_called()

    def test_public_never_falls_back_when_key_missing(self):
        with patch.object(server,'answer') as model:
            self.assertEqual(self.client.post('/api/query',json={'question':'营业收入多少','generate':True}).status_code,400)
            model.assert_not_called()

    def test_validation_does_not_echo_secret(self):
        response=self.client.post('/api/query',json={'question':'x','api_key':'SECRET_SENTINEL'})
        self.assertEqual(response.status_code,422);self.assertNotIn('SECRET_SENTINEL',response.text)

    def test_keys_are_request_scoped_and_absent_in_result(self):
        r=MagicMock();r.automatic.return_value=[{'company':'五粮液','id':'test','text':'证据'}]
        with patch.object(server,'retriever',return_value=r),patch.object(server,'answer',return_value={'answer':'测试'}) as model:
            for key in ['FIRST_SENTINEL','SECOND_SENTINEL']:
                response=self.client.post('/api/query',json={'question':'五粮液营业收入','generate':True,'api_key':key})
                self.assertEqual(response.status_code,200)
                self.assertEqual(model.call_args.kwargs['credentials'][2],key)
                self.assertEqual(model.call_args.kwargs['credentials'][1],'https://api.openai.com/v1')
                self.assertNotIn(key,response.text)

    def test_retrieval_only_never_calls_model(self):
        r=MagicMock();r.search.return_value=[]
        with patch.object(server,'retriever',return_value=r),patch.object(server,'answer') as model:
            response=self.client.post('/api/query',json={'question':'五粮液营业收入','mode':'bm25'})
            self.assertEqual(response.status_code,200);model.assert_not_called()

    def test_history_path_cannot_escape(self):
        self.assertEqual(self.client.get('/api/examples/secrets').status_code,404)

    def test_saved_examples_default_to_reviewed_v4_and_keep_v3_distinct(self):
        # Use temporary fixtures; real assignment attachments are local only.
        fixture={'answer':'测试约数','manual_review':{'correct':True},'checks':{'preliminary_pass':False}}
        for folder in ['evaluation_v4','evaluation']:
            target=self.index/folder
            target.mkdir()
            (target/'Q03_hybrid_expanded.json').write_text(json.dumps(fixture),encoding='utf-8')
        with patch.object(server,'OUTPUT',self.index):
            current=self.client.get('/api/examples/Q03').json()
            historical=self.client.get('/api/examples/Q03?version=v3').json()
            self.assertEqual(self.client.get('/api/examples/Q01').status_code,404)
        self.assertEqual(current['index_version'],'v4')
        self.assertEqual(current['record_kind'],'evaluation')
        self.assertTrue(current['manual_review']['correct'])
        self.assertFalse(current['checks']['preliminary_pass'])
        self.assertTrue(historical['historical'])
        self.assertEqual(historical['index_version'],'v3')
        self.assertEqual(self.client.get('/api/examples/Q03?version=../../').status_code,422)

class TableHeaderTests(unittest.TestCase):
    def test_continuation_preserves_first_amount_row(self):
        rows=[['处置固定资产收到的现金','115,575.89','10,363,496.03'],['投资活动现金流入小计','9,234.00','8,000.00']]
        columns,depth,source=table_header(rows,{'columns':['项目','2025 年度','2024 年度']})
        self.assertEqual(depth,0);self.assertEqual(columns,['项目','2025 年度','2024 年度']);self.assertEqual(source,'previous_page')

    def test_unknown_header_is_explicit_not_numeric(self):
        columns,depth,source=table_header([['营业收入','123,456.78','100,000.00']])
        self.assertEqual(depth,0);self.assertEqual(source,'unresolved');self.assertTrue(all('未识别' in c for c in columns))

    def test_multilevel_header_keeps_leaf_and_parent(self):
        columns,depth,source=table_header([['项目','2025 年度','2024 年度'],['','金额','金额'],['营业收入','123.45','100.00']])
        self.assertEqual(depth,2);self.assertEqual(columns[1],'2025 年度 / 金额')

if __name__=='__main__':unittest.main()
