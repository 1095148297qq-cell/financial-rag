import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
from financial_rag import server
from financial_rag.query_plan import plan_question
from financial_rag.retrieval import Retriever

class NaturalQuestionTests(unittest.TestCase):
    def test_alias_colloquial_metric_and_relative_year(self):
        p=plan_question('茅台去年营收怎么样？',date(2026,10,12))
        self.assertEqual(p['companies'],['贵州茅台'])
        self.assertEqual(p['years'],[2025])
        self.assertIn('营业收入',p['search_question'])

    def test_final_instruction_overrides_background(self):
        p=plan_question('之前看了汾酒、古井、今世缘，只想核对茅台2025年的直销比例')
        self.assertEqual(p['companies'],['贵州茅台'])
        self.assertFalse(p['panoramic'])

    def test_open_question_does_not_require_a_template(self):
        p=plan_question('存货堆积会带来哪些经营风险？')
        self.assertEqual(len(p['companies']),12)
        self.assertFalse(p['panoramic'])

    def test_cross_company_and_unavailable_year(self):
        self.assertTrue(plan_question('2025年哪家公司的营收最高？')['panoramic'])
        p=plan_question('茅台今年营收如何',date(2026,10,12))
        self.assertEqual(p['years'],[])
        self.assertEqual(p['unavailable_years'],[2026])
        self.assertEqual(plan_question('汾酒25年营收')['years'],[2025])
        self.assertIn('营业收入',plan_question('汾酒25年收入增长了多少？')['search_question'])

    def test_narrative_seed_recovers_tables_on_same_page(self):
        r=Retriever.__new__(Retriever)
        base={'company':'贵州茅台','year':2025,'report_id':'report','page':17}
        narrative={**base,'id':'n','kind':'text','text':'直销渠道'}
        row={**base,'id':'t','kind':'table_row','table':1,'text':'直销金额'}
        unrelated={**row,'id':'other','page':127}
        r.chunks=[narrative,row,unrelated]
        r.search=MagicMock(return_value=[narrative])
        chunks=r.automatic(plan_question('茅台2025年直销比例'))
        self.assertEqual({c['id'] for c in chunks},{'n','t'})

    def test_statement_scope_includes_both_cashflow_rows(self):
        r=Retriever.__new__(Retriever);r.search=MagicMock(return_value=[])
        base={'company':'泸州老窖','year':2025,'report_id':'report','kind':'table_row',
              'table':1,'rows':[{'values':['经营活动产生的现金流量净额','123']}], 'text':'原文'}
        r.chunks=[{**base,'id':'parent','page':83,'statement':'母公司现金流量表'},
                  {**base,'id':'group','page':82,'statement':'合并现金流量表'}]
        chunks=r.automatic(plan_question('老窖2025年母公司和合并现金流有什么不同？'))
        self.assertEqual({c['id'] for c in chunks},{'parent','group'})

class NaturalRequestTests(unittest.TestCase):
    def test_unused_hidden_model_is_ignored_in_both_modes(self):
        with tempfile.TemporaryDirectory() as td:
            index=Path(td);(index/'version.json').write_text(json.dumps({'fingerprint':'test'}))
            r=MagicMock();r.automatic.return_value=[{'id':'x','company':'贵州茅台','text':'证据'}]
            with patch.object(server,'INDEX',index),patch.object(server,'LOCAL',True),patch.object(server,'retriever',return_value=r),patch.object(server,'answer',return_value={'answer':'测试'}) as model:
                client=TestClient(server.app)
                for generate in [False,True]:
                    response=client.post('/api/query',json={'question':'茅台去年赚了多少钱？','generate':generate,'auth':'local',
                        'provider':'旧显示名称','model':'默认模型（自动）','api_key':'SECRET_SENTINEL'},headers={'Origin':'http://127.0.0.1:3000'})
                    self.assertEqual(response.status_code,200,response.text)
                    self.assertNotIn('SECRET_SENTINEL',response.text)
                self.assertEqual(model.call_count,1)
                self.assertIsNone(model.call_args.kwargs['credentials'])

    def test_invalid_own_key_model_reports_field_without_echo(self):
        response=TestClient(server.app).post('/api/query',json={'question':'收入多少','generate':True,
            'model':'默认模型（自动）','api_key':'SECRET_SENTINEL'})
        self.assertEqual(response.status_code,422)
        self.assertIn('模型名称',response.json()['detail'])
        self.assertEqual(response.json()['error_code'],'request_validation')
        self.assertNotIn('SECRET_SENTINEL',response.text)

    def test_whitespace_question_is_rejected(self):
        response=TestClient(server.app).post('/api/query',json={'question':'   '})
        self.assertEqual(response.status_code,422)
        self.assertIn('问题',response.json()['detail'])
