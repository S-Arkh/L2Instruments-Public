import copy
import os
from pathlib import Path
import sys
import threading
import unittest
from unittest.mock import patch
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'python'))
from resource_compare import compare_resources,differences,MAX_DIFFERENCES
import test_resource_gui as navigation
import app


class ComparisonCore:
    def __init__(self):
        self.inventory=dict(candidates=[
            dict(id=1,path='Picture',**{'class':'Engine.Texture'},flags=7,outer='None',serial_bytes=32)],
            excluded_script_exports=2,version=133,licensee=40)
        self.candidate=copy.deepcopy(self.inventory);self.candidate['candidates'][0]['id']=9
        self.left=dict(value_bits=0x80000000,native_offset=100,
                       references=[dict(id=2,path='Palette',**{'class':'Palette'})])
        self.right=copy.deepcopy(self.left);self.right['native_offset']=800
        self.right['references'][0]['id']=99
        self.calls=[]
    def request(self, **kw):
        self.calls.append(kw)
        if kw['operation']=='resource_inventory':
            return {'result':self.inventory if kw['path']=='original' else self.candidate}
        return {'result':self.left if kw['path']=='original' else self.right}


class Comparison(unittest.TestCase):
    def test_relocated_references_and_exact_words(self):
        core=ComparisonCore();report=compare_resources(core,'original','candidate')
        self.assertTrue(report['equal'])
        self.assertEqual([x['object_id'] for x in core.calls if 'object_id' in x],[1,9])
        core.right['value_bits']=0
        report=compare_resources(core,'original','candidate')
        self.assertFalse(report['equal'])
        self.assertIn('/value_bits',report['rows'][0]['details'][0])
        core.right=copy.deepcopy(core.left)
        core.right['references'][0]['path']='Other'
        self.assertFalse(compare_resources(core,'original','candidate')['equal'])

    def test_missing_metadata_ambiguity_and_empty(self):
        core=ComparisonCore();core.candidate['candidates'][0]['flags']=8
        self.assertEqual(compare_resources(core,'original','candidate')['rows'][0]['status'],'different')
        core.candidate['candidates']=[]
        self.assertFalse(compare_resources(core,'original','candidate')['equal'])
        core.inventory['candidates']*=2
        with self.assertRaises(ValueError):compare_resources(core,'original','candidate')
        core.inventory['candidates']=[]
        self.assertFalse(compare_resources(core,'original','candidate')['equal'])

    def test_limits_unsupported_and_cancellation(self):
        core=ComparisonCore();core.candidate['candidates'][0]['serial_bytes']=9*1024*1024
        report=compare_resources(core,'original','candidate')
        self.assertEqual(report['rows'][0]['status'],'unverified')
        self.assertFalse(report['equal'])
        report=compare_resources(core,'original','candidate',cancelled=lambda:True)
        self.assertFalse(report['complete']);self.assertTrue(report['cancelled'])
        core=ComparisonCore();request=core.request
        def failing(**kw):
            if kw['operation']=='texture':raise RuntimeError('Unsupported profile')
            return request(**kw)
        core.request=failing
        self.assertEqual(compare_resources(core,'original','candidate')['rows'][0]['details'],['Unsupported profile'])

    def test_diff_bounds_and_reference_id_not_arbitrary_id(self):
        result=differences(list(range(1000)),list(range(1000,2000)))
        self.assertEqual(len(result),MAX_DIFFERENCES)
        self.assertTrue(differences(dict(id=1),dict(id=2)))
        self.assertTrue(differences(dict(v=True),dict(v=1)))
        self.assertTrue(differences([dict(v=True)],[dict(v=1)]))
        self.assertLess(len(differences('a'*100000,'b'*100000)[0]),250)

    def test_saved_blocking_volume_is_not_full_reconstruction_comparison(self):
        core=ComparisonCore()
        for inventory in (core.inventory,core.candidate):
            inventory['candidates'][0]['class']='Engine.BlockingVolume'
        report=compare_resources(core,'original','candidate')
        self.assertEqual(report['rows'][0]['status'],'unverified')
        self.assertFalse(report['equal'])
        self.assertIn('не является полной реконструкцией',report['rows'][0]['details'][0])
        self.assertTrue(all(call['operation']=='resource_inventory' for call in core.calls))

    def test_model_requires_two_complete_decoded_results(self):
        core=ComparisonCore()
        for inventory in (core.inventory,core.candidate):
            inventory['candidates'][0]['class']='Engine.Model'
        decoded=dict(status='decoded',points=[[1,2,3]],remaining_bytes=0)
        cases=(
            dict(status='unverified',points=[[1,2,3]]),
            dict(status='unverified',interpretation='opaque',raw_preview_hex='0102'),
            dict(status='partial',points=[[1,2,3]],remaining_bytes=5),
            dict(points=[[1,2,3]]),  # Missing or future status fails closed.
            dict(status='future',points=[[1,2,3]]),
            dict(status='decoded',interpretation='opaque',raw_preview_hex='0102'),
            dict(status='decoded',points=[[1,2,3]]),
            dict(status='decoded',points=[[1,2,3]],remaining_bytes=1),
        )
        for value in cases:
            for left,right in ((value,value),(value,decoded),(decoded,value)):
                with self.subTest(left=left,right=right):
                    core.left=copy.deepcopy(left);core.right=copy.deepcopy(right)
                    report=compare_resources(core,'original','candidate')
                    self.assertFalse(report['equal'])
                    self.assertEqual(report['rows'][0]['status'],'unverified')
                    self.assertIn('совпадение полной структуры не установлено',
                                  report['rows'][0]['details'][0])
        core.left=copy.deepcopy(decoded);core.right=copy.deepcopy(decoded)
        report=compare_resources(core,'original','candidate')
        self.assertTrue(report['equal'])
        self.assertEqual(report['rows'][0]['status'],'equal')
        core.right['points'][0][0]=9
        self.assertEqual(compare_resources(core,'original','candidate')['rows'][0]['status'],'different')
        core.right=copy.deepcopy(decoded);core.candidate['candidates'][0]['flags']=8
        self.assertEqual(compare_resources(core,'original','candidate')['rows'][0]['status'],'different')


class CompareGui(navigation.ResourceGuiTests):
    def test_close_cancels_and_waits_for_worker(self):
        w=self.window;release=threading.Event()
        try:
            w.show()
            w.task(lambda worker:release.wait(5),lambda result:None)
            worker=w.worker
            w.close()
            self.assertTrue(w.closing)
            self.assertTrue(worker.cancel.is_set())
            self.assertTrue(w.isVisible())
            w.pending_preview=True
            release.set();self.finish()
            self.assertFalse(w.isVisible())
            self.assertFalse(w.pending_preview)
        finally:release.set()

    def test_report_and_return(self):
        w=self.window;w.package='original';w.mode_tabs.setCurrentIndex(1)
        w.class_list.setCurrentRow(0);self.finish()
        core=ComparisonCore()
        with patch.object(w,'core',core):
            w.start_comparison('candidate')
            self.assertFalse(w.compare_button.isEnabled())
            self.assertFalse(w.compare_view.return_button.isEnabled())
            self.finish()
            view=w.compare_view
            self.assertTrue(view.report['equal'])
            self.assertIn('исключено экспортов кода/метаданных',view.info.text())
            self.assertEqual(view.rows.topLevelItemCount(),1)
            view.rows.setCurrentItem(view.rows.topLevelItem(0))
            self.assertIn('совпадают',view.details.toPlainText())
            self.assertTrue(view.details.isReadOnly())
        view.return_button.click();self.finish()
        self.assertIs(w.viewer.currentWidget(),w.resource_text)
        self.assertIsNone(view.report)

    def test_error_clears_prior_report(self):
        w=self.window;w.package='original';w.mode_tabs.setCurrentIndex(1)
        core=ComparisonCore()
        with patch.object(w,'core',core):
            w.start_comparison('candidate');self.finish()
            core.candidate['candidates']*=2
            w.start_comparison('candidate');self.finish()
        self.assertIsNone(w.compare_view.report)
        self.assertIn('Ambiguous',w.compare_view.info.text())


if __name__=='__main__':unittest.main()
