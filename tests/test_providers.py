"""Protocol, incomplete-response and key-destination tests; no real API calls."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock,patch
from fastapi.testclient import TestClient
from financial_rag import llm,server
from financial_rag.providers import PROVIDERS

CHUNKS=[{'company':'五粮液','year':2025,'page':7,'chapter':'主要指标','id':'test','text':'营业收入（元）=123.45'}]


class ProviderProtocolTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.output=patch.object(llm,'OUTPUT',Path(self.temp.name));self.output.start()

    def tearDown(self):
        self.output.stop();self.temp.cleanup()

    def credentials(self,provider):
        p=PROVIDERS[provider]
        return ('api_key',p['base_url'],'SECRET_SENTINEL',p['default_model'])

    def response(self,finish='stop',content='收入123.45元。[1]'):
        r=MagicMock(status_code=200)
        r.json.return_value={'choices':[{'message':{'content':content,'reasoning_content':'PRIVATE_REASONING'},'finish_reason':finish}],
                             'usage':{'prompt_tokens':50,'completion_tokens':12,'total_tokens':62}}
        return r

    def test_each_chat_provider_uses_official_endpoint_and_normalizes_usage(self):
        for provider in ['deepseek','qwen','siliconflow']:
            with self.subTest(provider=provider),patch.object(llm.requests,'post',return_value=self.response()) as post:
                result=llm.answer('收入多少？',CHUNKS,credentials=self.credentials(provider),provider=provider)
                self.assertEqual(post.call_args.args[0],PROVIDERS[provider]['base_url']+'/chat/completions')
                body=post.call_args.kwargs['json']
                self.assertEqual(body['max_tokens'],3500);self.assertFalse(body['stream'])
                self.assertNotIn('input',body);self.assertIn('PDF页=7',body['messages'][0]['content'])
                self.assertFalse(post.call_args.kwargs['allow_redirects'])
                self.assertEqual(result['provider'],provider)
                self.assertEqual(result['usage'],{'input_tokens':50,'output_tokens':12,'total_tokens':62})
                self.assertNotIn('SECRET_SENTINEL',json.dumps(result));self.assertNotIn('PRIVATE_REASONING',json.dumps(result))
                post.return_value.close.assert_called_once()

    def test_truncated_filtered_and_empty_answers_are_not_success(self):
        for finish,content in [('length','partial'),('content_filter','blocked'),('stop',''),('stop',None)]:
            with self.subTest(finish=finish,content=content),patch.object(llm.requests,'post',return_value=self.response(finish,content)) as post:
                with self.assertRaises(llm.ModelRequestError):
                    llm.answer('收入多少？',CHUNKS,credentials=self.credentials('deepseek'),provider='deepseek')
                post.assert_called_once();post.return_value.close.assert_called_once()

    def test_error_body_never_exposed_and_redirect_not_followed(self):
        for code in [401,429,302,500]:
            r=MagicMock(status_code=code,text='SECRET_SENTINEL account details')
            with self.subTest(code=code),patch.object(llm.requests,'post',return_value=r) as post:
                with self.assertRaises(llm.ModelRequestError) as caught:
                    llm.answer('收入多少？',CHUNKS,credentials=self.credentials('qwen'),provider='qwen')
                self.assertNotIn('SECRET_SENTINEL',str(caught.exception));self.assertIn(str(code),str(caught.exception))
                post.assert_called_once();r.close.assert_called_once()

    def test_wrong_destination_is_blocked_before_network(self):
        credentials=('api_key','https://untrusted.invalid','SECRET_SENTINEL','qwen-plus')
        with patch.object(llm.requests,'post') as post:
            with self.assertRaises(llm.ModelRequestError):
                llm.answer('收入多少？',CHUNKS,credentials=credentials,provider='qwen')
            post.assert_not_called()

    def test_local_oauth_keeps_responses_and_never_uses_other_provider(self):
        r=MagicMock(status_code=200)
        events=[{'type':'response.output_text.delta','delta':'收入123.45元。[1]'},
                {'type':'response.completed','response':{'usage':{'input_tokens':50,'output_tokens':12}}}]
        r.iter_lines.return_value=[b'data: '+json.dumps(e).encode() for e in events]
        with patch.object(llm,'configuration',return_value=('chatgpt_oauth',PROVIDERS['openai']['base_url'],'SECRET_SENTINEL','gpt-test')):
            with patch.object(llm.requests,'post',return_value=r) as post:
                result=llm.answer('收入多少？',CHUNKS,provider='qwen')
                self.assertEqual(result['provider'],'openai');self.assertEqual(result['auth_mode'],'chatgpt_oauth')
                self.assertTrue(post.call_args.args[0].endswith('/responses'))
                self.assertFalse(post.call_args.kwargs['json']['store'])
                self.assertNotIn('max_output_tokens',post.call_args.kwargs['json'])
                r.close.assert_called_once()

    def test_openai_key_keeps_responses_output_limit(self):
        r=MagicMock(status_code=200)
        r.iter_lines.return_value=[b'data: '+json.dumps(e).encode() for e in [
            {'type':'response.output_text.delta','delta':'收入123.45元。[1]'},
            {'type':'response.completed','response':{'usage':{'input_tokens':50,'output_tokens':12}}}]]
        with patch.object(llm.requests,'post',return_value=r) as post:
            result=llm.answer('收入多少？',CHUNKS,credentials=self.credentials('openai'),provider='openai')
            self.assertEqual(post.call_args.kwargs['json']['max_output_tokens'],3500)
            self.assertEqual(result['auth_mode'],'api_key');self.assertEqual(result['provider'],'openai')

    def test_local_third_party_config_never_borrows_openai_key(self):
        with patch.dict(os.environ,{'AUTH_MODE':'api_key','API_PROVIDER':'deepseek','DEEPSEEK_API_KEY':'','OPENAI_API_KEY':'SECRET_SENTINEL'}):
            with self.assertRaisesRegex(RuntimeError,'DEEPSEEK_API_KEY') as caught:
                llm.configuration()
            self.assertNotIn('SECRET_SENTINEL',str(caught.exception))


class ProviderBackendTests(unittest.TestCase):
    def setUp(self):
        self.client=TestClient(server.app)
        self.temp=tempfile.TemporaryDirectory();self.directory=Path(self.temp.name)
        (self.directory/'version.json').write_text(json.dumps({'fingerprint':'test'}))
        self.patches=[patch.object(server,'INDEX',self.directory),patch.object(server,'LOCAL',False)]
        for p in self.patches:p.start()

    def tearDown(self):
        for p in reversed(self.patches):p.stop()
        self.temp.cleanup()

    def test_provider_defaults_and_keys_remain_request_scoped(self):
        retriever=MagicMock();retriever.expanded.return_value=CHUNKS
        with patch.object(server,'retriever',return_value=retriever),patch.object(server,'answer',return_value={'answer':'收入123.45元。[1]'}) as answer:
            for provider in PROVIDERS:
                key='SENTINEL_'+provider
                response=self.client.post('/api/query',json={'question':'五粮液收入多少？','generate':True,'provider':provider,'api_key':key})
                self.assertEqual(response.status_code,200)
                self.assertEqual(answer.call_args.kwargs['credentials'],('api_key',PROVIDERS[provider]['base_url'],key,PROVIDERS[provider]['default_model']))
                self.assertEqual(answer.call_args.kwargs['provider'],provider)
                self.assertNotIn(key,response.text)

    def test_unknown_provider_and_client_base_url_cannot_redirect_key(self):
        for extra in [{'provider':'unknown'},{'provider':'qwen','base_url':'https://untrusted.invalid'}]:
            with patch.object(server,'answer') as answer:
                response=self.client.post('/api/query',json={'question':'收入多少？','generate':True,'api_key':'SECRET_SENTINEL',**extra})
                self.assertEqual(response.status_code,422);self.assertNotIn('SECRET_SENTINEL',response.text);answer.assert_not_called()

    def test_third_party_missing_key_does_not_use_owner_auth(self):
        with patch.object(server,'answer') as answer:
            response=self.client.post('/api/query',json={'question':'收入多少？','generate':True,'provider':'deepseek'})
            self.assertEqual(response.status_code,400);answer.assert_not_called()

    def test_platform_model_names_with_slashes_are_accepted(self):
        retriever=MagicMock();retriever.expanded.return_value=CHUNKS
        with patch.object(server,'retriever',return_value=retriever),patch.object(server,'answer',return_value={'answer':'测试'}) as answer:
            response=self.client.post('/api/query',json={'question':'收入多少？','generate':True,'provider':'siliconflow','model':'deepseek-ai/DeepSeek-V4-Flash','api_key':'SECRET_SENTINEL'})
            self.assertEqual(response.status_code,200)
            self.assertEqual(answer.call_args.kwargs['credentials'][3],'deepseek-ai/DeepSeek-V4-Flash')

    def test_generic_failures_do_not_leak_provider_payload(self):
        retriever=MagicMock();retriever.expanded.return_value=CHUNKS
        with patch.object(server,'retriever',return_value=retriever),patch.object(server,'answer',side_effect=RuntimeError('SECRET_SENTINEL')):
            response=self.client.post('/api/query',json={'question':'收入多少？','generate':True,'provider':'deepseek','api_key':'SECRET_SENTINEL'})
            self.assertIn('error',response.json());self.assertNotIn('SECRET_SENTINEL',response.text)
