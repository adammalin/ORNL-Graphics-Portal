import copy
import unittest
from scripts.compare_smartsheet_exports import compare,html_report


def export(rows,extra=()):
    return {'sheets':[{'name':'Jobs','rows':[['Graphics Req #','Description','Status','DEV Test Record',*extra],*rows]}]}


class SheetComparisonTests(unittest.TestCase):
    def test_test_job_number_collision_is_never_merged_with_a_live_job(self):
        live=export([['G_1','Actual client','New',False],['G_2','New live job','New',False]])
        dev=export([['G_1','[DEV PORTAL] Fictional','Accepted',True],['DEV_3','Fictional only','New',True]])
        original=copy.deepcopy(dev);r=compare(live,dev)
        self.assertEqual([x['job'] for x in r['jobNumberCollisions']],['G_1'])
        self.assertEqual([x['job'] for x in r['missingRows']],['G_2'])
        self.assertEqual([x['job'] for x in r['devOnlyRows']],['DEV_3'])
        self.assertEqual(r['matchedJobs'],[]);self.assertEqual(original,dev)

    def test_nonempty_differences_and_live_blanks_require_review(self):
        live=export([['G_1','A','Accepted',False,0,5]],['Estimate','Days Until Due'])
        dev=export([['G_1','A','New',False,None,3]],['Estimate','Days Until Due'])
        r=compare(live,dev)
        self.assertEqual([x['field'] for x in r['conflicts']],['Status'])
        self.assertEqual(r['fillCandidates'][0]['live'],0)
        self.assertEqual(r['calculatedDifferences'][0]['field'],'Days Until Due')
        r=compare(export([['G_1','A',None,False]]),export([['G_1','A','New',False]]))
        self.assertIn('Live is blank',r['conflicts'][0]['reason'])

    def test_duplicate_keys_are_ambiguous_and_dev_only_columns_are_preserved(self):
        r=compare(export([['G_1','A','New',False],['G_1','B','New',False]]),
                  export([['G_1','A','New',False,'Keep link']],['Portal link']))
        self.assertEqual(len(r['ambiguousKeys']),1);self.assertEqual(r['matchedJobs'],[])
        self.assertEqual(r['schema']['devOnlyColumns'],['Portal link'])

    def test_html_escapes_untrusted_request_text_and_unkeyed_rows_are_visible(self):
        r=compare(export([['G_1','<script>bad()</script>','New',False],['','Unkeyed','New',False]]),
                  export([['G_1','Original','New',False]]))
        text=html_report(r)
        self.assertNotIn('<script>',text);self.assertIn('&lt;script&gt;',text)
        self.assertEqual(r['unkeyedRows']['live'],[3])
