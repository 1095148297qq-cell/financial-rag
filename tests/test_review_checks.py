import unittest
from financial_rag.review_checks import percentage_match,citation_coverage


class ReviewChecksTests(unittest.TestCase):
    def test_rounded_percentage_without_accepting_wrong_calculation(self):
        self.assertTrue(percentage_match('65.77','前者约占65.8%',1))
        self.assertFalse(percentage_match('50.09','金额正确，但占比50.18%',2))
        self.assertFalse(percentage_match('65.77','金额65.8万元',1))

    def test_recalled_page_does_not_count_as_cited_evidence(self):
        record={'answer':'合同负债见[1]','chunks':[{'company':'公司','year':2025,'page':17},
                                                     {'company':'公司','year':2025,'page':102}]}
        alternatives=[[{'company':'公司','year':2025,'page':58},{'company':'公司','year':2025,'page':102}]]
        self.assertFalse(citation_coverage(record,alternatives)['page_coverage_pass'])
        record['answer']='合同负债见[2]'
        self.assertTrue(citation_coverage(record,alternatives)['page_coverage_pass'])

    def test_invalid_citation_cannot_pass(self):
        self.assertFalse(citation_coverage({'answer':'见[99]','chunks':[]},[])['page_coverage_pass'])
